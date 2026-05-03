# Tier 4 — GNSS-Denied / Underground / Adversarial

**Target accuracy:** ±2–3 m typical without GNSS; sub-meter with LiDAR-SLAM + map fusion.

## Stack

| Modality | Use case | Notes |
|---|---|---|
| Terrain Referencing Navigation (TRN) | aircraft / cruise missiles | match radar altimeter profile to DEM |
| LiDAR SLAM (LIO-SAM, LeGO-LOAM, FAST-LIO2) | ground vehicles, drones, indoor robots | drift-free with loop closure |
| Radar positioning | through-fog, through-smoke | mmWave radar + map matching |
| Celestial navigation | open ocean, polar, space | sun/moon/star sextant + ephemeris |
| Radio beacon triangulation | military E-LORAN, eLoran | <100 km range, hardened |
| Gravity anomaly | submarines, deep aerospace | match measured `g` to gravity map |
| Magnetic anomaly | local geological signature | match crustal magnetic map |

## Components to implement

- `trn_engine.py` — radar-altimeter profile correlator vs DEM (SRTM, ASTER GDEM)
- `lidar_slam_fastlio2.py` — wrapper over FAST-LIO2 binary; ROS2 bridge
- `radar_slam.py` — mmWave radar feature extraction + map matching
- `celestial_solver.py` — sextant angle + ephemeris (DE440) → lat/lon
- `eloran_receiver.py` — opportunistic eLoran TOA decoding
- `gravity_match.py` — gravimeter reading correlator vs WGM2012 grid
- `mag_anomaly_match.py` — magnetometer correlator vs EMAG2 / WMM crustal map
- `denied_fusion.py` — fuse all of above when GNSS=down

## Offline assets needed

- DEM tiles (SRTM 1 arc-sec global, ASTER GDEM where finer)
- WGM2012 gravity anomaly grid
- EMAG2 / WMM 2025 crustal magnetic anomaly grid
- DE440 ephemeris (JPL) — sun/moon/planet positions
- Star catalog (Tycho-2, Hipparcos, Gaia DR3)
- eLoran chain database

## References

- FAST-LIO2 (MIT) — github.com/hku-mars/FAST_LIO
- LIO-SAM, LeGO-LOAM (BSD) — Tixiao Shan et al.
- "Fundamentals of Inertial Navigation, Satellite-based Positioning and their Integration" — A. Noureldin
- USGS WGM2012, NOAA EMAG2 v3
