"""Tier 1 — Multi-constellation GNSS + RTK estimator (scaffold)."""
from __future__ import annotations
from .types import Estimate, Pose, Position, Confidence


class SatelliteEstimator:
    """Multi-constellation: GPS+GLONASS+Galileo+BeiDou+QZSS+NavIC. RTK ±2cm.

    Real impl plugs into rtklib / GNSS-SDR / serial RTK module.
    Stub returns last-known with infinite uncertainty.
    """

    def __init__(self, rtk_enabled: bool = True,
                 spoofing_detection: bool = True):
        self.rtk = rtk_enabled
        self.spoof = spoofing_detection
        self._last: Estimate | None = None

    def update(self, raw: dict) -> Estimate:
        """raw = parsed NMEA / RTCM / SBP frame."""
        # TODO real fix → this is interface only
        if self._last is None:
            self._last = Estimate(
                pose=Pose(Position(0.0, 0.0, 0.0)),
                confidence=Confidence(valid=False, source="satellite-stub"),
                source="satellite",
            )
        return self._last

    def detect_spoofing(self, raw: dict) -> bool:
        """Return True if signal anomaly suggests spoofing/jamming."""
        return False
