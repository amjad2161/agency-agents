"""Tier 4 — Underground / GNSS-denied: TRN + LiDAR SLAM + celestial + magnetic anomaly."""
from __future__ import annotations
from .types import Estimate, Pose, Position, Confidence


class UndergroundEstimator:
    """Target: ±2-3m without any satellite signal."""

    def __init__(self, has_lidar: bool = True, has_celestial: bool = False,
                 has_gravity: bool = False, has_magnetic_anomaly: bool = True):
        self.cfg = {"lidar": has_lidar, "celestial": has_celestial,
                    "gravity": has_gravity, "magnetic_anomaly": has_magnetic_anomaly}

    def update(self, frames: dict) -> Estimate:
        return Estimate(
            pose=Pose(Position(0.0, 0.0, 0.0)),
            confidence=Confidence(valid=False, source="underground-stub"),
            source="underground",
            raw={"cfg": self.cfg},
        )
