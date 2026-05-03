"""
GODSKILL Navigation System v11.0
================================
Multi-tier sensor fusion stack. Goal: ±0.5m-3m accuracy in any environment,
fully offline. Per OMEGA_NEXUS Tier-4 specification.

Tiers (each = independent estimator, fused by EKF/UKF/PF):
    1. Satellite      (GPS/GLONASS/Galileo/BeiDou/QZSS/NavIC + RTK)
    2. Indoor         (Visual SLAM, VIO, WiFi RTT, BLE, UWB, magnetic, PDR)
    3. Underwater     (INS, DVL, LBL/SBL/USBL, sonar SLAM, bathymetric match)
    4. Underground    (TRN, LiDAR SLAM, radar, celestial, gravity/magnetic anomaly)
    5. Sensor fusion  (EKF + UKF + PF + graph SLAM + outlier rejection)
    6. AI/ML          (deep radio maps, scene recognition, neural SLAM, LSTM trajectory)
    7. Offline data   (vector maps, satellite imagery, DEM, bathymetric, fingerprints)

Status: PRODUCTION — all 7 tiers fully implemented. Pure Python, zero external deps.
        Optional PyTorch / ONNX backends activate automatically when available.
"""

__version__ = "11.0.0"

from .types import Position, Velocity, Pose, Estimate, Confidence
from .fusion import SensorFusion
from .satellite import SatelliteEstimator
from .indoor import IndoorEstimator
from .underwater import UnderwaterEstimator
from .underground import UndergroundEstimator
from .ai_enhance import AIEnhancer
from .offline_maps import OfflineMaps

# Canonical public-API aliases (preferred names going forward).
NavigationFusion = SensorFusion
SatellitePositioner = SatelliteEstimator
IndoorPositioner = IndoorEstimator
UnderwaterPositioner = UnderwaterEstimator
UndergroundPositioner = UndergroundEstimator
AIEnhancement = AIEnhancer

__all__ = [
    # Shared types
    "Position", "Velocity", "Pose", "Estimate", "Confidence",
    # Tier estimators (legacy names)
    "SatelliteEstimator",
    "IndoorEstimator",
    "UnderwaterEstimator",
    "UndergroundEstimator",
    # Core engines (legacy names)
    "SensorFusion",
    "AIEnhancer",
    "OfflineMaps",
    # Canonical public-API names
    "NavigationFusion",
    "SatellitePositioner",
    "IndoorPositioner",
    "UnderwaterPositioner",
    "UndergroundPositioner",
    "AIEnhancement",
]
