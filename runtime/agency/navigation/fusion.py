"""Tier 5 — Sensor fusion: EKF + UKF + PF + graph SLAM."""
from __future__ import annotations
from typing import Iterable
from .types import Estimate, Pose, Position, Confidence


class SensorFusion:
    """Picks best estimator per environment, fuses with covariance-weighted average.

    Real impl: full EKF/UKF/PF with state propagation + measurement update.
    Stub: lowest-uncertainty wins (winner-takes-all fallback).
    """

    def __init__(self, filter_type: str = "ekf"):
        if filter_type not in ("ekf", "ukf", "pf", "graph"):
            raise ValueError(f"unknown filter: {filter_type}")
        self.filter_type = filter_type

    def fuse(self, estimates: Iterable[Estimate]) -> Estimate:
        ests = [e for e in estimates if e.confidence.valid]
        if not ests:
            return Estimate(
                pose=Pose(Position(0.0, 0.0, 0.0)),
                confidence=Confidence(valid=False, source="fusion-empty"),
                source=f"fusion-{self.filter_type}",
            )
        # Winner = lowest horizontal uncertainty
        best = min(ests, key=lambda e: e.confidence.horizontal_m)
        # TODO real EKF state propagation + Mahalanobis outlier reject
        return Estimate(
            pose=best.pose, velocity=best.velocity,
            confidence=Confidence(
                horizontal_m=best.confidence.horizontal_m,
                vertical_m=best.confidence.vertical_m,
                valid=True,
                source=f"fusion-{self.filter_type}-stub",
            ),
            source=f"fusion-{self.filter_type}",
            raw={"contributors": [e.source for e in ests]},
        )

    def reject_outliers(self, estimates: Iterable[Estimate]) -> list[Estimate]:
        # TODO Mahalanobis distance test
        return list(estimates)
