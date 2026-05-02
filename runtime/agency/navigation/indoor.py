"""Tier 2 — Indoor: Visual SLAM + VIO + WiFi RTT + BLE + UWB + magnetic + PDR."""
from __future__ import annotations
from .types import Estimate, Pose, Position, Confidence


class IndoorEstimator:
    """Fuses indoor-only sensors. Target: ±1m accuracy in any building."""

    def __init__(self, use_uwb: bool = True, use_wifi_rtt: bool = True,
                 use_visual_slam: bool = True, use_magnetic: bool = True,
                 use_pdr: bool = True):
        self.flags = {
            "uwb": use_uwb, "wifi_rtt": use_wifi_rtt,
            "visual_slam": use_visual_slam, "magnetic": use_magnetic,
            "pdr": use_pdr,
        }

    def update(self, frames: dict) -> Estimate:
        """frames = {wifi_rtt: [...], ble: [...], uwb: [...], imu: [...], camera: bytes}"""
        return Estimate(
            pose=Pose(Position(0.0, 0.0, 0.0)),
            confidence=Confidence(valid=False, source="indoor-stub"),
            source="indoor",
            raw={"flags": self.flags},
        )
