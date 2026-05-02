"""Tier 3 — Underwater: INS + DVL + acoustic positioning + sonar SLAM."""
from __future__ import annotations
from .types import Estimate, Pose, Position, Confidence


class UnderwaterEstimator:
    """Target: ±0.3% of distance traveled."""

    def __init__(self, has_dvl: bool = True, has_lbl: bool = False,
                 has_usbl: bool = True, has_sonar: bool = True):
        self.cfg = {"dvl": has_dvl, "lbl": has_lbl,
                    "usbl": has_usbl, "sonar": has_sonar}

    def update(self, frames: dict) -> Estimate:
        return Estimate(
            pose=Pose(Position(0.0, 0.0, 0.0)),
            confidence=Confidence(valid=False, source="underwater-stub"),
            source="underwater",
            raw={"cfg": self.cfg},
        )
