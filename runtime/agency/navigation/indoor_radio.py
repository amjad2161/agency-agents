"""GODSKILL Nav v11 — Radio-frequency indoor positioning.

WiFi RTT trilateration + RSSI fingerprint KNN, BLE trilateration,
UWB TDoA hyperbolic positioning. Pure numpy.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


SPEED_OF_LIGHT = 299_792_458.0  # m/s


# ------------------------------------------------------------------
# WiFi RTT + fingerprint
# ------------------------------------------------------------------

@dataclass
class _APMeasurement:
    bssid: str
    position: np.ndarray
    measured_range_m: float


@dataclass
class _Fingerprint:
    position: np.ndarray
    rssi_by_bssid: dict[str, float]


def _weighted_lstsq_trilateration(
    positions: np.ndarray,
    ranges: np.ndarray,
    weights: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Weighted least-squares trilateration in 3D.

    Returns the position vector (length 3) that best fits |x - p_i| = r_i.
    Uses linearisation around the first anchor.
    """
    if positions.shape[0] < 3:
        raise ValueError("trilateration needs ≥ 3 anchors")
    p0 = positions[0]
    r0 = ranges[0]
    A = 2.0 * (positions[1:] - p0)
    b = (
        ranges[0] ** 2 - ranges[1:] ** 2
        - np.sum(p0 ** 2) + np.sum(positions[1:] ** 2, axis=1)
    )
    if weights is not None:
        w = np.sqrt(weights[1:])
        A = A * w[:, None]
        b = b * w
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    # If only XY anchors given (z all equal), pad z
    if sol.shape[0] == 2:
        z = float(p0[2]) if positions.shape[1] == 3 else 0.0
        return np.array([sol[0], sol[1], z])
    return sol


class WiFiRTT:
    """WiFi RTT triangulation + RSSI fingerprint KNN."""

    def __init__(self, k: int = 3):
        self.k = max(1, int(k))
        self._aps: dict[str, _APMeasurement] = {}
        self._fingerprints: list[_Fingerprint] = []

    # -------- RTT trilateration --------

    def add_ap(
        self,
        bssid: str,
        position_xyz: tuple[float, float, float],
        measured_range_m: float,
    ) -> None:
        """Register a measured range to an access point."""
        self._aps[bssid] = _APMeasurement(
            bssid=bssid,
            position=np.asarray(position_xyz, dtype=np.float64),
            measured_range_m=float(measured_range_m),
        )

    def clear_aps(self) -> None:
        self._aps.clear()

    def trilaterate(self) -> tuple[float, float, float]:
        """Solve for the receiver position using all current AP ranges."""
        if len(self._aps) < 3:
            raise ValueError("need ≥ 3 APs for trilateration")
        positions = np.stack([ap.position for ap in self._aps.values()])
        ranges = np.array([ap.measured_range_m for ap in self._aps.values()])
        # Weight inversely proportional to range (closer = more accurate)
        weights = 1.0 / np.clip(ranges, 0.5, None)
        sol = _weighted_lstsq_trilateration(positions, ranges, weights)
        return float(sol[0]), float(sol[1]), float(sol[2])

    @staticmethod
    def rtt_to_range(round_trip_time_ns: float) -> float:
        """Convert WiFi RTT (round-trip nanoseconds) to one-way distance."""
        return float(round_trip_time_ns) * 1e-9 * SPEED_OF_LIGHT / 2.0

    # -------- RSSI fingerprinting --------

    def update_fingerprint(
        self,
        bssid: str,
        rssi: int,
        position: tuple[float, float, float],
    ) -> None:
        """Add a single (AP, RSSI, position) sample to the fingerprint DB."""
        pos = np.asarray(position, dtype=np.float64)
        for fp in self._fingerprints:
            if np.allclose(fp.position, pos):
                fp.rssi_by_bssid[bssid] = float(rssi)
                return
        self._fingerprints.append(
            _Fingerprint(position=pos, rssi_by_bssid={bssid: float(rssi)})
        )

    def fingerprint_lookup(
        self, scan: dict[str, int]
    ) -> tuple[float, float, float]:
        """KNN over RSSI signature space. Falls back to centroid if DB empty."""
        if not self._fingerprints:
            raise ValueError("fingerprint DB is empty")
        if not scan:
            raise ValueError("scan must contain ≥ 1 (bssid, rssi)")
        distances: list[tuple[float, np.ndarray]] = []
        for fp in self._fingerprints:
            shared = set(fp.rssi_by_bssid) & set(scan)
            if not shared:
                continue
            d = math.sqrt(sum(
                (fp.rssi_by_bssid[b] - scan[b]) ** 2 for b in shared
            ))
            distances.append((d, fp.position))
        if not distances:
            # No common APs — return mean of all stored fingerprints
            mean = np.mean([fp.position for fp in self._fingerprints], axis=0)
            return float(mean[0]), float(mean[1]), float(mean[2])
        distances.sort(key=lambda x: x[0])
        top = distances[: self.k]
        # Inverse-distance weighted average
        eps = 1e-6
        weights = np.array([1.0 / (d + eps) for d, _ in top])
        positions = np.stack([p for _, p in top])
        weighted = np.sum(positions * weights[:, None], axis=0) / np.sum(weights)
        return float(weighted[0]), float(weighted[1]), float(weighted[2])


# ------------------------------------------------------------------
# BLE positioning
# ------------------------------------------------------------------

class BLEPositioner:
    """BLE beacon-based positioning via log-distance + trilateration."""

    @staticmethod
    def rssi_to_distance(
        rssi: float, tx_power: float = -59.0, n: float = 2.0
    ) -> float:
        """Log-distance path-loss model. Returns metres."""
        if n <= 0:
            raise ValueError("path-loss exponent must be positive")
        return float(10 ** ((float(tx_power) - float(rssi)) / (10.0 * n)))

    def position_from_beacons(
        self, beacons: list[dict]
    ) -> tuple[float, float]:
        """Trilaterate from ≥ 3 beacons.

        Each beacon dict: {x, y, rssi, [tx_power], [n]}.
        """
        if len(beacons) < 3:
            raise ValueError("need ≥ 3 BLE beacons")
        positions = []
        ranges = []
        for b in beacons:
            x = float(b["x"])
            y = float(b["y"])
            z = float(b.get("z", 0.0))
            tx = float(b.get("tx_power", -59.0))
            n = float(b.get("n", 2.0))
            r = self.rssi_to_distance(b["rssi"], tx, n)
            positions.append([x, y, z])
            ranges.append(r)
        sol = _weighted_lstsq_trilateration(
            np.array(positions), np.array(ranges)
        )
        return float(sol[0]), float(sol[1])


# ------------------------------------------------------------------
# UWB TDoA positioning
# ------------------------------------------------------------------

class UWBPositioner:
    """Ultra-Wideband Time-Difference-of-Arrival positioning.

    Targets ±10 cm accuracy in line-of-sight conditions. Uses
    Newton-Raphson over hyperbolic constraints.
    """

    MAX_ITERS = 50
    CONVERGE_M = 1e-4

    def tdoa_position(
        self,
        anchors: np.ndarray,
        tdoa_measurements: np.ndarray,
        initial_guess: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Solve TDoA hyperbolic localisation by Newton-Raphson.

        anchors: (N, 3) array of anchor positions
        tdoa_measurements: (N-1,) array, t_i - t_0 in seconds
        """
        anchors = np.asarray(anchors, dtype=np.float64)
        tdoa = np.asarray(tdoa_measurements, dtype=np.float64)
        if anchors.shape[0] < 4:
            raise ValueError("UWB TDoA needs ≥ 4 anchors")
        if tdoa.shape[0] != anchors.shape[0] - 1:
            raise ValueError("len(tdoa) must equal len(anchors) - 1")
        # Range differences from anchor 0
        rd = tdoa * SPEED_OF_LIGHT
        x = (
            np.asarray(initial_guess, dtype=np.float64)
            if initial_guess is not None
            else np.mean(anchors, axis=0)
        )
        for _ in range(self.MAX_ITERS):
            r0 = float(np.linalg.norm(x - anchors[0]))
            if r0 < 1e-9:
                r0 = 1e-9
            residuals = []
            J_rows = []
            for i in range(1, anchors.shape[0]):
                ri = float(np.linalg.norm(x - anchors[i]))
                if ri < 1e-9:
                    ri = 1e-9
                residuals.append(ri - r0 - rd[i - 1])
                grad_i = (x - anchors[i]) / ri - (x - anchors[0]) / r0
                J_rows.append(grad_i)
            r = np.array(residuals)
            J = np.stack(J_rows)
            try:
                step, *_ = np.linalg.lstsq(J, -r, rcond=None)
            except np.linalg.LinAlgError:
                break
            x = x + step
            if float(np.linalg.norm(step)) < self.CONVERGE_M:
                break
        return x


__all__ = [
    "WiFiRTT", "BLEPositioner", "UWBPositioner",
    "SPEED_OF_LIGHT",
]
