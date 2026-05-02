"""GODSKILL Nav v11 — Tier 2: Indoor Positioning Engine."""
from __future__ import annotations
import math, time
from dataclasses import dataclass, field
from typing import Optional
from .types import Confidence, Estimate, Position, Pose, Velocity

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
    ax: float; ay: float; az: float
    gx: float; gy: float; gz: float
    timestamp: float = field(default_factory=time.time)

@dataclass
class MagSample:
    bx: float; by: float; bz: float
    x_m: Optional[float] = None
    y_m: Optional[float] = None

def _trilaterate(anchors_xyz, ranges):
    """Simple 2-D trilateration from 3+ anchors.
    Returns (x, y) or None if insufficient anchors."""
    if len(anchors_xyz) < 3:
        return None
    # Use first 3 anchors with least-squares
    x1,y1,r1 = anchors_xyz[0][0], anchors_xyz[0][1], ranges[0]
    x2,y2,r2 = anchors_xyz[1][0], anchors_xyz[1][1], ranges[1]
    x3,y3,r3 = anchors_xyz[2][0], anchors_xyz[2][1], ranges[2]
    A = 2*(x2-x1); B = 2*(y2-y1)
    C = r1**2 - r2**2 - x1**2 + x2**2 - y1**2 + y2**2
    D = 2*(x3-x2); E = 2*(y3-y2)
    F = r2**2 - r3**2 - x2**2 + x3**2 - y2**2 + y3**2
    denom = A*E - B*D
    if abs(denom) < 1e-9:
        return None
    x = (C*E - F*B) / denom
    y = (A*F - D*C) / denom
    return (x, y)

def _rssi_to_dist(rssi: float, tx_power: float = -59.0) -> float:
    """Log-distance path loss model. Returns metres."""
    n = 2.0  # path loss exponent (free space)
    return 10 ** ((tx_power - rssi) / (10 * n))

class IndoorEngine:
    """Multi-technology indoor fusion engine."""

    def __init__(self):
        self._anchors: dict[str, UWBAnchor] = {}
        self._x = 0.0; self._y = 0.0; self._z = 0.0
        self._h_acc = float("inf")
        self._step_count = 0
        self._heading = 0.0
        self._step_len = 0.7  # metres
        self._prev_acc_mag = 9.81
        self._mag_map: list[MagSample] = []

    def add_uwb_anchor(self, anchor: UWBAnchor) -> None:
        self._anchors[anchor.anchor_id] = anchor

    def update_uwb(self, measurements: list) -> Optional[Estimate]:
        valid = [m for m in measurements if m.anchor_id in self._anchors]
        if len(valid) < 3:
            return None
        xyzr = [(self._anchors[m.anchor_id].x_m,
                 self._anchors[m.anchor_id].y_m,
                 self._anchors[m.anchor_id].z_m,
                 m.range_m) for m in valid]
        result = _trilaterate([(a,b,c) for a,b,c,_ in xyzr], [r for _,_,_,r in xyzr])
        if result is None:
            return None
        self._x, self._y = result
        avg_std = sum(m.std_m for m in valid) / len(valid)
        self._h_acc = avg_std * 2
        return self._make_estimate("indoor-uwb", self._h_acc)

    def update_wifi(self, scans: list, ap_map: dict) -> Optional[Estimate]:
        matched = [(scans[i], ap_map[scans[i].bssid])
                   for i in range(len(scans)) if scans[i].bssid in ap_map]
        if not matched:
            return None
        points_ranges = []
        for scan, ap in matched:
            if scan.rtt_ns is not None:
                dist = scan.rtt_ns * 1e-9 * 3e8 / 2  # speed of light
            else:
                dist = _rssi_to_dist(scan.rssi_dbm, ap.tx_power_dbm)
            points_ranges.append(((ap.x_m, ap.y_m, ap.z_m), dist))
        if len(points_ranges) >= 3:
            result = _trilaterate([p[0] for p in points_ranges],
                                   [p[1] for p in points_ranges])
            if result:
                self._x, self._y = result
                self._h_acc = 3.0
                return self._make_estimate("indoor-wifi-rtt", self._h_acc)
        # Fallback: nearest AP by RSSI
        best = min(matched, key=lambda t: abs(t[0].rssi_dbm - t[1].tx_power_dbm))
        self._x, self._y = best[1].x_m, best[1].y_m
        self._h_acc = 10.0
        return self._make_estimate("indoor-wifi-rssi", self._h_acc)

    def update_ble(self, beacons: list, beacon_map: dict) -> Optional[Estimate]:
        matched = [(b, beacon_map[b.uuid]) for b in beacons if b.uuid in beacon_map]
        if not matched:
            return None
        if len(matched) >= 3:
            points = [(xy[0], xy[1], 0.0) for _, xy in matched]
            ranges = [_rssi_to_dist(b.rssi_dbm, b.measured_power) for b, _ in matched]
            result = _trilaterate(points, ranges)
            if result:
                self._x, self._y = result
                self._h_acc = 2.0
                return self._make_estimate("indoor-ble", self._h_acc)
        best_b, best_xy = min(matched, key=lambda t: -t[0].rssi_dbm)
        self._x, self._y = best_xy[0], best_xy[1]
        self._h_acc = 5.0
        return self._make_estimate("indoor-ble-nearest", self._h_acc)

    def update_imu(self, sample: IMUSample) -> Optional[Estimate]:
        """Pedestrian Dead Reckoning step detection."""
        acc_mag = math.sqrt(sample.ax**2 + sample.ay**2 + sample.az**2)
        step_detected = False
        if self._prev_acc_mag < 9.5 and acc_mag > 10.5:
            step_detected = True
            self._step_count += 1
            # Integrate gyro heading (simplified, assume gz = yaw rate rad/s)
            # dt ~ 0.1s assumption
            self._heading += sample.gz * 0.1
        self._prev_acc_mag = acc_mag
        if not step_detected:
            return None
        dx = self._step_len * math.sin(self._heading)
        dy = self._step_len * math.cos(self._heading)
        self._x += dx; self._y += dy
        self._h_acc = min(self._h_acc + 0.1, 5.0)  # drift
        return self._make_estimate("indoor-pdr", self._h_acc)

    def update_mag(self, sample: MagSample) -> None:
        self._mag_map.append(sample)

    def _make_estimate(self, src: str, h_acc: float) -> Estimate:
        return Estimate(
            pose=Pose(Position(self._x, self._y, self._z)),
            confidence=Confidence(horizontal_m=h_acc, vertical_m=1.0, valid=True, source=src),
            source="indoor",
            raw={"x_m":self._x,"y_m":self._y,"step_count":self._step_count},
        )

    def reset(self) -> None:
        self._x = self._y = self._z = 0.0
        self._h_acc = float("inf")
        self._step_count = 0

IndoorEstimator = IndoorEngine

__all__ = ["IndoorEngine","IndoorEstimator",
           "UWBAnchor","UWBMeasurement","WiFiAP","WiFiScan",
           "BLEBeacon","IMUSample","MagSample"]
