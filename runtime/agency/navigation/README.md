# GODSKILL Navigation System v11.0 — scaffold

Per user OMEGA_NEXUS Tier-4 spec. Multi-tier sensor fusion targeting ±0.5–3m accuracy in any environment, fully offline.

## Tiers

| # | Module | Target accuracy | Status |
|---|--------|----------------|--------|
| 1 | `satellite.py` (GPS/GLONASS/Galileo/BeiDou/QZSS/NavIC + RTK) | ±0.5m outdoor (±2cm RTK) | scaffold |
| 2 | `indoor.py` (V-SLAM + VIO + WiFi RTT + BLE + UWB + mag + PDR) | ±1m indoor | scaffold |
| 3 | `underwater.py` (INS + DVL + LBL/SBL/USBL + sonar SLAM) | ±0.3% of distance | scaffold |
| 4 | `underground.py` (TRN + LiDAR SLAM + celestial + grav/mag anomaly) | ±2-3m | scaffold |
| 5 | `fusion.py` (EKF/UKF/PF/graph) | n/a — fuses tiers | scaffold |
| 6 | `ai_enhance.py` (deep radio maps, neural SLAM, LSTM) | n/a — refines tiers | scaffold |
| 7 | `data/` (offline maps + DEM + radio fingerprints) | n/a — supports tiers | scaffold |

## Usage (when implemented)

```python
from runtime.agency.navigation import (
    SatelliteEstimator, IndoorEstimator, SensorFusion, AIEnhancer
)

sat = SatelliteEstimator(rtk_enabled=True)
indoor = IndoorEstimator(use_uwb=True, use_wifi_rtt=True)
fusion = SensorFusion(filter_type="ekf")
ai = AIEnhancer(model_dir="./models")

# Each tier produces an Estimate; fusion picks/blends best
sat_est    = sat.update(nmea_frame)
indoor_est = indoor.update(sensor_frames)
fused      = fusion.fuse([sat_est, indoor_est])
predicted  = ai.predict_next(history=[fused])
```

## Roadmap to production (≈4-6 wk)

1. Wire `satellite.py` to `pyrtcm` + serial → real RTK fix
2. Port ORB-SLAM3 / DROID-SLAM into `indoor.py`
3. Implement EKF state propagation in `fusion.py` (replace winner-takes-all)
4. Train + ship ResNet/LSTM models in `ai_enhance.py`
5. Bundle global vector tile + DEM data under `data/`

This scaffold is consumed by `SUPER_DRIVER.ps1` STEP 3 (copies to `runtime/agency/navigation/`).
