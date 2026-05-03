# Tier 3 — Underwater Positioning

**Target accuracy:** ±0.3 % of distance traveled (INS+DVL), ±0.5 m absolute (USBL).

## Stack

| Modality | Range | Notes |
|---|---|---|
| Inertial Navigation System (INS) | continuous | drift = f(IMU grade); FOG / RLG <0.001 °/h |
| Doppler Velocity Logger (DVL) | 100–500 m altitude | bottom-lock velocity ±0.2 % |
| Long-Baseline (LBL) acoustic | 1–10 km | seafloor transponders; absolute ±0.5–2 m |
| Short-Baseline (SBL) | 100 m | hull-mounted transponders |
| Ultra-Short-Baseline (USBL) | 1–7 km | single transducer + phase-array receiver |
| Sonar SLAM | sensor-range | mechanical/multibeam sonar + ICP map alignment |
| Bathymetric map matching | global (where mapped) | match measured depth profile to chart |

## Components to implement

- `ins_strapdown.py` — strapdown mechanization (NED frame); supports MEMS / FOG / RLG IMUs
- `dvl_bottom_lock.py` — Teledyne Pathfinder / Nortek protocol; corrects for sound speed
- `lbl_solver.py` — TOA from N transponders → 3-D position (≥4 baselines)
- `usbl_phase_array.py` — phase-difference angle-of-arrival + slant range
- `sonar_slam.py` — feature extraction + ICP between successive multibeam scans
- `bathymetric_matcher.py` — 1-D depth-profile correlator vs chart
- `underwater_fusion.py` — UKF over INS+DVL+USBL+bathy; handles acoustic-update outages

## Offline assets needed

- Bathymetric chart tiles (GEBCO 2024 grid, 15 arc-sec global)
- Sound-speed profile vs depth (CTD-derived)
- LBL/USBL transponder registry per area

## References

- Doppler Velocity Logging primer (Teledyne, Nortek)
- ICRA / IEEE-Oceans literature on graph-SLAM underwater
- Kongsberg HiPAP USBL spec
- WHOI MicroModem acoustic comms
