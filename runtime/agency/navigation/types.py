"""Common types — shared by all GODSKILL nav modules."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class Position:
    """WGS-84 lat/lon/alt (m). Lat/lon in decimal degrees."""
    lat: float
    lon: float
    alt: float = 0.0


@dataclass(frozen=True)
class Velocity:
    """ENU (East-North-Up) m/s."""
    east: float = 0.0
    north: float = 0.0
    up: float = 0.0


@dataclass(frozen=True)
class Pose:
    """Position + orientation (quaternion w,x,y,z)."""
    position: Position
    qw: float = 1.0
    qx: float = 0.0
    qy: float = 0.0
    qz: float = 0.0


@dataclass
class Confidence:
    """Per-axis 1-σ uncertainty (m). Lower = better."""
    horizontal_m: float = float("inf")
    vertical_m: float = float("inf")
    valid: bool = False
    source: str = "unknown"


@dataclass
class Estimate:
    """Output of any tier. Stamped + tagged with source + confidence."""
    pose: Pose
    velocity: Velocity = field(default_factory=Velocity)
    confidence: Confidence = field(default_factory=Confidence)
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "stub"
    raw: dict = field(default_factory=dict)
