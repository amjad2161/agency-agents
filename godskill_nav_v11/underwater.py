"""GODSKILL Nav v11 — Tier 3: Underwater Navigation Engine."""
from __future__ import annotations
import math, time
from dataclasses import dataclass, field
from typing import Optional, List
from .types import Confidence, Estimate, Position, Pose, Velocity

@dataclass
class INSSample:
    ax: float; ay: float; az: float
    gx: float; gy: float; gz: float
    timestamp: float = field(default_factory=time.time)

@dataclass
class DVLSample:
    vx_mps: float
    vy_mps: float
    vz_mps: float
    beam_valid: List[bool] = field(default_factory=lambda:[True,True,True,True])
    altitude_m: Optional[float] = None

@dataclass
class LBLFix:
    transponder_id: str
    x_m: float
    y_m: float
    z_m: float = 0.0
    slant_range_m: float = 0.0
    travel_time_s: float = 0.0

@dataclass
class USBLFix:
    ship_x_m: float
    ship_y_m: float
    ship_z_m: float
    bearing_rad: float
    elevation_rad: float
    range_m: float

class UnderwaterEngine:
    """Underwater strapdown INS + DVL + acoustic positioning."""

    def __init__(self):
        self._x = 0.0; self._y = 0.0; self._z = 0.0
        self._vx = 0.0; self._vy = 0.0; self._vz = 0.0
        self._heading = 0.0; self._pitch = 0.0; self._roll = 0.0
        self._dist_travelled = 0.0
        self._h_acc = float("inf")
        self._last_ts: Optional[float] = None
        self._lbl_fixes: dict[str, LBLFix] = {}

    def update_ins(self, sample: INSSample) -> Optional[Estimate]:
        ts = sample.timestamp
        if self._last_ts is None:
            self._last_ts = ts
            return None
        dt = max(ts - self._last_ts, 1e-6)
        self._last_ts = ts
        # Strapdown integration (simplified, NED frame)
        self._heading += sample.gz * dt
        self._pitch += sample.gy * dt
        self._roll += sample.gx * dt
        # Remove gravity (simplified, assume heading≈0)
        ax_world = sample.ax - 9.81 * math.sin(self._pitch)
        ay_world = sample.ay - 9.81 * math.sin(self._roll)
        self._vx += ax_world * dt; self._vy += ay_world * dt
        self._x += self._vx * dt; self._y += self._vy * dt; self._z += self._vz * dt
        self._h_acc = min(self._h_acc + 0.003 * dt, 50.0)
        return self._make_estimate("underwater-ins", self._h_acc)

    def update_dvl(self, sample: DVLSample) -> Optional[Estimate]:
        valid_beams = sum(1 for v in sample.beam_valid if v)
        # Degrade confidence with fewer valid beams (still return estimate)
        beam_conf = valid_beams / max(len(sample.beam_valid), 1)
        if valid_beams < 1:
            return None
        # DVL provides velocity-over-bottom — update velocity
        vx = sample.vx_mps * math.cos(self._heading) - sample.vy_mps * math.sin(self._heading)
        vy = sample.vx_mps * math.sin(self._heading) + sample.vy_mps * math.cos(self._heading)
        self._vx = vx; self._vy = vy; self._vz = sample.vz_mps
        dt = 0.1  # assumed
        self._x += self._vx * dt; self._y += self._vy * dt
        speed = math.sqrt(vx**2 + vy**2)
        self._dist_travelled += speed * dt
        self._h_acc = max(0.003 * self._dist_travelled, 0.1)
        return self._make_estimate("underwater-dvl", self._h_acc)

    def update_lbl(self, fix: LBLFix) -> Optional[Estimate]:
        self._lbl_fixes[fix.transponder_id] = fix
        transponders = list(self._lbl_fixes.values())
        if len(transponders) < 3:
            return None
        # Trilateration from 3 transponders
        t = transponders
        x1,y1,r1 = t[0].x_m, t[0].y_m, t[0].slant_range_m
        x2,y2,r2 = t[1].x_m, t[1].y_m, t[1].slant_range_m
        x3,y3,r3 = t[2].x_m, t[2].y_m, t[2].slant_range_m
        A = 2*(x2-x1); B = 2*(y2-y1)
        C = r1**2-r2**2-x1**2+x2**2-y1**2+y2**2
        D = 2*(x3-x2); E = 2*(y3-y2)
        F = r2**2-r3**2-x2**2+x3**2-y2**2+y3**2
        denom = A*E-B*D
        if abs(denom) < 1e-9:
            return None
        self._x = (C*E-F*B)/denom
        self._y = (A*F-D*C)/denom
        self._h_acc = 0.5  # LBL typically ±0.5 m
        self._dist_travelled = 0.0  # reset drift counter
        return self._make_estimate("underwater-lbl", self._h_acc)

    def update_usbl(self, fix: USBLFix) -> Optional[Estimate]:
        # Convert spherical to Cartesian
        self._x = fix.ship_x_m + fix.range_m * math.cos(fix.elevation_rad) * math.sin(fix.bearing_rad)
        self._y = fix.ship_y_m + fix.range_m * math.cos(fix.elevation_rad) * math.cos(fix.bearing_rad)
        self._z = fix.ship_z_m - fix.range_m * math.sin(fix.elevation_rad)
        self._h_acc = fix.range_m * 0.01  # ~1% of range
        return self._make_estimate("underwater-usbl", self._h_acc)

    def _make_estimate(self, src: str, h_acc: float) -> Estimate:
        return Estimate(
            pose=Pose(Position(self._x, self._y, self._z)),
            velocity=Velocity(east=self._vx, north=self._vy, up=self._vz),
            confidence=Confidence(horizontal_m=h_acc, vertical_m=h_acc*1.5, valid=True, source=src),
            source="underwater",
            raw={"dist_travelled_m":self._dist_travelled},
        )

    def reset(self):
        self.__init__()

UnderwaterEstimator = UnderwaterEngine

__all__ = ["UnderwaterEngine","UnderwaterEstimator",
           "INSSample","DVLSample","LBLFix","USBLFix"]
