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

Status: SCAFFOLD — interfaces + stub estimators. Production fusion = future pass.
"""

__version__ = "11.0.0-scaffold"

from .types import Position, Velocity, Pose, Estimate, Confidence
from .fusion import SensorFusion
from .satellite import SatelliteEstimator
from .indoor import IndoorEstimator
from .underwater import UnderwaterEstimator
from .underground import UndergroundEstimator
from .ai_enhance import AIEnhancer

__all__ = [
    "Position", "Velocity", "Pose", "Estimate", "Confidence",
    "SensorFusion",
    "SatelliteEstimator", "IndoorEstimator",
    "UnderwaterEstimator", "UndergroundEstimator",
    "AIEnhancer",
]
