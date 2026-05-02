"""GODSKILL Nav v11 — Tier 4: Underground / GNSS-Denied Navigation Engine."""
from __future__ import annotations
import math, time
from dataclasses import dataclass, field
from typing import Optional, List
from .types import Confidence, Estimate, Position, Pose, Velocity

@dataclass
class OdometrySample:
    left_ticks: int
    right_ticks: int
    wheel_radius_m: float = 0.15
    track_width_m: float = 0.50
    heading_rad: Optional[float] = None
    timestamp: float = field(default_factory=time.time)

@dataclass
class LiDARScan:
    angles_rad: List[float]
    ranges_m: List[float]
    max_range_m: float = 30.0

@dataclass
class RadioBeacon:
    beacon_id: str
    x_m: float
    y_m: float
    z_m: float = 0.0
    rssi_dbm: float = -70.0
    range_m: Optional[float] = None

@dataclass
class MagAnomalySample:
    total_field_nT: float
    gradient_nT_m: float
    x_m: Optional[float] = None
    y_m: Optional[float] = None

def _rssi_to_range(rssi: float, ref_dbm: float = -40.0, n: float = 2.5) -> float:
    return 10 ** ((ref_dbm - rssi) / (10 * n))

class UndergroundEngine:
    """Tunnel/mine/subway navigation without GNSS."""

    TICKS_PER_REV: float = 1024.0

    def __init__(self):
        self._x = 0.0; self._y = 0.0; self._heading = 0.0
        self._h_acc = float("inf")
        self._prev_ticks_l = 0; self._prev_ticks_r = 0
        self._beacons: dict[str, RadioBeacon] = {}
        self._mag_grid: List[MagAnomalySample] = []
        self._reference_scan: Optional[LiDARScan] = None

    def add_beacon(self, beacon: RadioBeacon) -> None:
        self._beacons[beacon.beacon_id] = beacon

    def update_odometry(self, sample: OdometrySample) -> Estimate:
        dl_ticks = sample.left_ticks - self._prev_ticks_l
        dr_ticks = sample.right_ticks - self._prev_ticks_r
        self._prev_ticks_l = sample.left_ticks
        self._prev_ticks_r = sample.right_ticks
        circ = 2 * math.pi * sample.wheel_radius_m
        dl = dl_ticks / self.TICKS_PER_REV * circ
        dr = dr_ticks / self.TICKS_PER_REV * circ
        dist = (dl + dr) / 2.0
        d_theta = (dr - dl) / sample.track_width_m
        if sample.heading_rad is not None:
            self._heading = sample.heading_rad
        else:
            self._heading += d_theta
        self._x += dist * math.cos(self._heading)
        self._y += dist * math.sin(self._heading)
        self._h_acc = min(self._h_acc + abs(dist) * 0.02, 30.0)
        return self._make_estimate("underground-odometry", self._h_acc)

    def update_lidar(self, scan: LiDARScan) -> Estimate:
        """ICP scan matching against reference scan (simplified)."""
        valid = [(a, r) for a, r in zip(scan.angles_rad, scan.ranges_m)
                 if r < scan.max_range_m]
        if not valid:
            return self._make_estimate("underground-lidar-no-valid", self._h_acc)
        if self._reference_scan is None:
            self._reference_scan = scan
            return self._make_estimate("underground-lidar-ref", self._h_acc)
        # Compute centroid shift as proxy for displacement
        ref_valid = [(a, r) for a, r in zip(self._reference_scan.angles_rad,
                                              self._reference_scan.ranges_m)
                     if r < self._reference_scan.max_range_m]
        if not ref_valid:
            self._reference_scan = scan
            return self._make_estimate("underground-lidar-reset", self._h_acc)
        cx_new = sum(r*math.cos(a) for a,r in valid) / len(valid)
        cy_new = sum(r*math.sin(a) for a,r in valid) / len(valid)
        cx_ref = sum(r*math.cos(a) for a,r in ref_valid) / len(ref_valid)
        cy_ref = sum(r*math.sin(a) for a,r in ref_valid) / len(ref_valid)
        dx = cx_new - cx_ref; dy = cy_new - cy_ref
        # Move in opposite direction (we moved, world shifted)
        self._x -= dx * math.cos(self._heading) - dy * math.sin(self._heading)
        self._y -= dx * math.sin(self._heading) + dy * math.cos(self._heading)
        self._h_acc = 2.0  # LiDAR-matched
        self._reference_scan = scan
        return self._make_estimate("underground-lidar-icp", self._h_acc)

    def update_radio_beacons(self, observations: List[RadioBeacon]) -> Optional[Estimate]:
        known = [(o, self._beacons[o.beacon_id]) for o in observations
                 if o.beacon_id in self._beacons]
        if len(known) < 3:
            return None
        pts = []; ranges = []
        for obs, ref in known:
            pts.append((ref.x_m, ref.y_m, ref.z_m))
            r = obs.range_m if obs.range_m is not None else _rssi_to_range(obs.rssi_dbm)
            ranges.append(r)
        from .indoor import _trilaterate  # reuse trilateration
        result = _trilaterate(pts, ranges)
        if result:
            self._x, self._y = result
            self._h_acc = 3.0
            return self._make_estimate("underground-radio", self._h_acc)
        return None

    def update_mag_anomaly(self, sample: MagAnomalySample) -> Optional[Estimate]:
        self._mag_grid.append(sample)
        if sample.x_m is not None and sample.y_m is not None:
            self._x = sample.x_m; self._y = sample.y_m
            self._h_acc = 5.0
            return self._make_estimate("underground-mag-anomaly", self._h_acc)
        return None

    def _make_estimate(self, src: str, h_acc: float) -> Estimate:
        return Estimate(
            pose=Pose(Position(self._x, self._y, 0.0)),
            confidence=Confidence(horizontal_m=h_acc, vertical_m=2.0, valid=True, source=src),
            source="underground",
            raw={"heading_deg":math.degrees(self._heading)},
        )

    def reset(self):
        self.__init__()

UndergroundEstimator = UndergroundEngine

__all__ = ["UndergroundEngine","UndergroundEstimator",
           "OdometrySample","LiDARScan","RadioBeacon","MagAnomalySample"]
