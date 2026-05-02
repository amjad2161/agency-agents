"""GODSKILL Nav v11 — Tier 2: Indoor Positioning Engine.

Orchestrates Visual SLAM, VIO, WiFi RTT, BLE, UWB, magnetic mapping
and pedestrian dead reckoning into a single fused indoor estimate.

Backwards-compatible with the previous lightweight IndoorEngine API
used by ``test_smoke.py`` and ``fusion.py``.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .indoor_inertial import MagneticMapper, PDREstimator, PDRPose
from .indoor_radio import BLEPositioner, UWBPositioner, WiFiRTT
from .indoor_slam import (
    DMatch,
    KeyPoint,
    Pose2D,
    Pose3D,
    VIOEstimator,
    VisualSLAM,
)
from .types import Confidence, Estimate, Pose, Position, Velocity


# ------------------------------------------------------------------
# Legacy data classes (kept for backwards compat)
# ------------------------------------------------------------------

@dataclass
class UWBAnchor:
    anchor_id: str
    x_m: float
    y_m: float
    z_m: float = 0.0


@dataclass
class UWBMeasurement:
    anchor_id: str
    range_m: float
    std_m: float = 0.10


@dataclass
class WiFiAP:
    bssid: str
    x_m: float
    y_m: float
    z_m: float = 0.0
    freq_mhz: float = 2412.0
    tx_power_dbm: float = 20.0


@dataclass
class WiFiScan:
    bssid: str
    rtt_ns: Optional[float] = None
    rssi_dbm: float = -80.0


@dataclass
class BLEBeacon:
    uuid: str
    major: int = 0
    minor: int = 0
    rssi_dbm: float = -70.0
    measured_power: float = -59.0


@dataclass
class IMUSample:
    ax: float
    ay: float
    az: float
    gx: float
    gy: float
    gz: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class MagSample:
    bx: float
    by: float
    bz: float
    x_m: Optional[float] = None
    y_m: Optional[float] = None


# ------------------------------------------------------------------
# Internal helpers (legacy API)
# ------------------------------------------------------------------

def _trilaterate(anchors_xyz, ranges):
    """Closed-form 2-D trilateration from the first 3 anchors."""
    if len(anchors_xyz) < 3:
        return None
    x1, y1 = anchors_xyz[0][0], anchors_xyz[0][1]
    x2, y2 = anchors_xyz[1][0], anchors_xyz[1][1]
    x3, y3 = anchors_xyz[2][0], anchors_xyz[2][1]
    r1, r2, r3 = ranges[0], ranges[1], ranges[2]
    A = 2.0 * (x2 - x1)
    B = 2.0 * (y2 - y1)
    C = r1 ** 2 - r2 ** 2 - x1 ** 2 + x2 ** 2 - y1 ** 2 + y2 ** 2
    D = 2.0 * (x3 - x2)
    E = 2.0 * (y3 - y2)
    F = r2 ** 2 - r3 ** 2 - x2 ** 2 + x3 ** 2 - y2 ** 2 + y3 ** 2
    denom = A * E - B * D
    if abs(denom) < 1e-9:
        return None
    x = (C * E - F * B) / denom
    y = (A * F - D * C) / denom
    return (x, y)


def _rssi_to_dist(rssi: float, tx_power: float = -59.0) -> float:
    """Log-distance path-loss model (free-space exponent)."""
    return 10 ** ((tx_power - rssi) / (10 * 2.0))


# ------------------------------------------------------------------
# Source quality table — used by fuse() to pick the best estimate.
# Lower horizontal_m => higher rank.
# ------------------------------------------------------------------
_SOURCE_RANK: dict[str, float] = {
    "indoor-uwb": 0.10,
    "indoor-uwb-tdoa": 0.15,
    "indoor-vio": 0.40,
    "indoor-vslam": 0.80,
    "indoor-ble": 2.0,
    "indoor-ble-nearest": 5.0,
    "indoor-wifi-rtt": 3.0,
    "indoor-wifi-fingerprint": 4.0,
    "indoor-wifi-rssi": 10.0,
    "indoor-pdr": 5.0,
    "indoor-magnetic": 3.0,
}


# ------------------------------------------------------------------
# Indoor engine
# ------------------------------------------------------------------

class IndoorEngine:
    """Multi-technology indoor positioning fusion engine."""

    def __init__(self):
        # Legacy state
        self._anchors: dict[str, UWBAnchor] = {}
        self._x = 0.0
        self._y = 0.0
        self._z = 0.0
        self._h_acc = float("inf")
        self._step_count = 0
        self._heading = 0.0
        self._step_len = 0.7
        self._prev_acc_mag = 9.81
        self._mag_map: list[MagSample] = []

        # Tier-2 estimators
        self.visual_slam = VisualSLAM()
        self.vio = VIOEstimator()
        self.wifi = WiFiRTT()
        self.ble = BLEPositioner()
        self.uwb = UWBPositioner()
        self.magnetic = MagneticMapper()
        self.pdr = PDREstimator()

        # Cache of latest estimate per source
        self._latest: dict[str, Estimate] = {}

    # -------- legacy: UWB --------

    def add_uwb_anchor(self, anchor: UWBAnchor) -> None:
        self._anchors[anchor.anchor_id] = anchor

    def update_uwb(self, measurements: list) -> Optional[Estimate]:
        valid = [m for m in measurements if m.anchor_id in self._anchors]
        if len(valid) < 3:
            return None
        xyzr = [
            (
                self._anchors[m.anchor_id].x_m,
                self._anchors[m.anchor_id].y_m,
                self._anchors[m.anchor_id].z_m,
                m.range_m,
            )
            for m in valid
        ]
        result = _trilaterate(
            [(a, b, c) for a, b, c, _ in xyzr],
            [r for _, _, _, r in xyzr],
        )
        if result is None:
            return None
        self._x, self._y = result
        avg_std = sum(m.std_m for m in valid) / len(valid)
        self._h_acc = avg_std * 2
        est = self._make_estimate("indoor-uwb", self._h_acc)
        self._latest["indoor-uwb"] = est
        return est

    # -------- legacy: WiFi --------

    def update_wifi(self, scans: list, ap_map: dict) -> Optional[Estimate]:
        matched = [
            (scans[i], ap_map[scans[i].bssid])
            for i in range(len(scans))
            if scans[i].bssid in ap_map
        ]
        if not matched:
            return None
        points_ranges = []
        for scan, ap in matched:
            if scan.rtt_ns is not None:
                dist = scan.rtt_ns * 1e-9 * 3e8 / 2.0
            else:
                dist = _rssi_to_dist(scan.rssi_dbm, ap.tx_power_dbm)
            points_ranges.append(((ap.x_m, ap.y_m, ap.z_m), dist))
        if len(points_ranges) >= 3:
            result = _trilaterate(
                [p[0] for p in points_ranges],
                [p[1] for p in points_ranges],
            )
            if result:
                self._x, self._y = result
                self._h_acc = 3.0
                est = self._make_estimate("indoor-wifi-rtt", self._h_acc)
                self._latest["indoor-wifi-rtt"] = est
                return est
        # Fallback: nearest AP by signal strength
        best = min(matched, key=lambda t: abs(t[0].rssi_dbm - t[1].tx_power_dbm))
        self._x, self._y = best[1].x_m, best[1].y_m
        self._h_acc = 10.0
        est = self._make_estimate("indoor-wifi-rssi", self._h_acc)
        self._latest["indoor-wifi-rssi"] = est
        return est

    # -------- legacy: BLE --------

    def update_ble(self, beacons: list, beacon_map: dict) -> Optional[Estimate]:
        matched = [(b, beacon_map[b.uuid]) for b in beacons if b.uuid in beacon_map]
        if not matched:
            return None
        if len(matched) >= 3:
            points = [(xy[0], xy[1], 0.0) for _, xy in matched]
            ranges = [
                _rssi_to_dist(b.rssi_dbm, b.measured_power) for b, _ in matched
            ]
            result = _trilaterate(points, ranges)
            if result:
                self._x, self._y = result
                self._h_acc = 2.0
                est = self._make_estimate("indoor-ble", self._h_acc)
                self._latest["indoor-ble"] = est
                return est
        best_b, best_xy = min(matched, key=lambda t: -t[0].rssi_dbm)
        self._x, self._y = best_xy[0], best_xy[1]
        self._h_acc = 5.0
        est = self._make_estimate("indoor-ble-nearest", self._h_acc)
        self._latest["indoor-ble-nearest"] = est
        return est

    # -------- legacy: IMU/PDR --------

    def update_imu(self, sample: IMUSample) -> Optional[Estimate]:
        """Pedestrian Dead Reckoning step detection."""
        acc_mag = math.sqrt(sample.ax ** 2 + sample.ay ** 2 + sample.az ** 2)
        step_detected = False
        if self._prev_acc_mag < 9.5 and acc_mag > 10.5:
            step_detected = True
            self._step_count += 1
            self._heading += sample.gz * 0.1
        self._prev_acc_mag = acc_mag
        if not step_detected:
            return None
        dx = self._step_len * math.sin(self._heading)
        dy = self._step_len * math.cos(self._heading)
        self._x += dx
        self._y += dy
        self._h_acc = min(self._h_acc + 0.1, 5.0)
        est = self._make_estimate("indoor-pdr", self._h_acc)
        self._latest["indoor-pdr"] = est
        return est

    def update_mag(self, sample: MagSample) -> None:
        self._mag_map.append(sample)

    # -------- new Tier-2 entry points --------

    def update_visual(
        self, image_gray: np.ndarray, timestamp: float = 0.0
    ) -> Estimate:
        """Run a Visual SLAM update and publish the resulting pose."""
        pose = self.visual_slam.update(image_gray, timestamp)
        self._x, self._y = pose.x, pose.y
        self._h_acc = 0.8
        est = self._make_estimate("indoor-vslam", self._h_acc)
        self._latest["indoor-vslam"] = est
        return est

    def update_vio(
        self,
        image_gray: Optional[np.ndarray],
        accel: np.ndarray,
        gyro: np.ndarray,
        dt: float,
    ) -> Estimate:
        """Run a Visual-Inertial update."""
        pose = self.vio.update(image_gray, accel, gyro, dt)
        self._x, self._y, self._z = pose.x, pose.y, pose.z
        self._h_acc = 0.4
        est = self._make_estimate("indoor-vio", self._h_acc)
        self._latest["indoor-vio"] = est
        return est

    def update_uwb_tdoa(
        self,
        anchors: np.ndarray,
        tdoa_seconds: np.ndarray,
    ) -> Estimate:
        """Solve UWB hyperbolic TDoA position."""
        pos = self.uwb.tdoa_position(anchors, tdoa_seconds)
        self._x, self._y, self._z = float(pos[0]), float(pos[1]), float(pos[2])
        self._h_acc = 0.15
        est = self._make_estimate("indoor-uwb-tdoa", self._h_acc)
        self._latest["indoor-uwb-tdoa"] = est
        return est

    def update_pdr(
        self,
        accel: np.ndarray,
        gyro: np.ndarray,
        mag: np.ndarray,
        dt: float = 0.02,
    ) -> Optional[Estimate]:
        """Run PDR step. Only emits an estimate when a step fires."""
        before = self.pdr.pose.step_count
        pose: PDRPose = self.pdr.update(accel, gyro, mag, dt)
        if pose.step_count == before:
            return None
        self._x, self._y = pose.x, pose.y
        self._heading = pose.heading
        self._step_count = pose.step_count
        self._h_acc = min(self._h_acc + 0.1, 5.0)
        est = self._make_estimate("indoor-pdr", self._h_acc)
        self._latest["indoor-pdr"] = est
        return est

    def update_magnetic(
        self,
        mag_reading: np.ndarray,
        record_position: Optional[tuple[float, float]] = None,
    ) -> Optional[Estimate]:
        """Either store a fingerprint or look up the current position."""
        if record_position is not None:
            self.magnetic.record(record_position, mag_reading)
            return None
        if len(self.magnetic) == 0:
            return None
        x, y = self.magnetic.lookup(mag_reading)
        self._x, self._y = x, y
        self._h_acc = 3.0
        est = self._make_estimate("indoor-magnetic", self._h_acc)
        self._latest["indoor-magnetic"] = est
        return est

    def update_wifi_fingerprint(
        self, scan: dict[str, int]
    ) -> Optional[Estimate]:
        """Look up a position from the WiFi RSSI fingerprint database."""
        try:
            x, y, z = self.wifi.fingerprint_lookup(scan)
        except ValueError:
            return None
        self._x, self._y, self._z = x, y, z
        self._h_acc = 4.0
        est = self._make_estimate("indoor-wifi-fingerprint", self._h_acc)
        self._latest["indoor-wifi-fingerprint"] = est
        return est

    # -------- fusion --------

    def fuse(self) -> Optional[Estimate]:
        """Pick the best available indoor source by expected accuracy.

        Strategy: choose the source whose declared horizontal accuracy is
        smallest, breaking ties by the static SOURCE_RANK table.
        """
        if not self._latest:
            return None
        ranked = sorted(
            self._latest.items(),
            key=lambda kv: (
                kv[1].confidence.horizontal_m,
                _SOURCE_RANK.get(kv[0], 99.0),
            ),
        )
        return ranked[0][1]

    # -------- output construction --------

    def _make_estimate(self, src: str, h_acc: float) -> Estimate:
        return Estimate(
            pose=Pose(Position(self._x, self._y, self._z)),
            confidence=Confidence(
                horizontal_m=h_acc,
                vertical_m=1.0,
                valid=True,
                source=src,
            ),
            source="indoor",
            raw={"x_m": self._x, "y_m": self._y, "step_count": self._step_count},
        )

    def reset(self) -> None:
        self._x = self._y = self._z = 0.0
        self._h_acc = float("inf")
        self._step_count = 0
        self._latest.clear()
        self.visual_slam.reset()
        self.vio.reset()
        self.pdr.reset()


IndoorEstimator = IndoorEngine


__all__ = [
    # Legacy + dataclasses
    "IndoorEngine", "IndoorEstimator",
    "UWBAnchor", "UWBMeasurement", "WiFiAP", "WiFiScan",
    "BLEBeacon", "IMUSample", "MagSample",
    # Tier-2 re-exports
    "VisualSLAM", "VIOEstimator", "KeyPoint", "DMatch",
    "Pose2D", "Pose3D",
    "WiFiRTT", "BLEPositioner", "UWBPositioner",
    "MagneticMapper", "PDREstimator", "PDRPose",
]
