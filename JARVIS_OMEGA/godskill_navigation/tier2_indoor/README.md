# Tier 2 — Indoor Positioning

**Target accuracy:** ±1 m typical, ±10 cm with UWB, sub-meter with VIO + magnetic-fingerprint fusion.

## Stack

| Modality | Module | Range | Accuracy |
|---|---|---|---|
| Visual SLAM | ORB-SLAM3 / Cartographer | mono / stereo / RGB-D | ±0.1–0.5 m, drift-corrected by loop closure |
| Visual-Inertial Odometry (VIO) | VINS-Mono / OpenVINS | continuous | ±1 % distance |
| WiFi RTT (802.11mc) | FTM ranging to 3+ APs | 50 m radius | ±1–2 m |
| BLE / iBeacon | RSSI + path-loss model + filter | 30 m | ±2–3 m |
| Ultra-Wideband (UWB) | DW3000 / NXP SR150 | 100 m | ±10 cm |
| Magnetic field map | learned per-floor fingerprint | building-wide | ±2 m, drift-free |
| Pedestrian Dead Reckoning | step + heading + height | continuous | ±5 % distance |

## Components to implement

- `vslam_orb3.py` — wrapper over ORB-SLAM3 binary; produces 6-DoF pose @ 30 Hz
- `vio_openvins.py` — IMU-camera fusion; supports MAV/handheld
- `wifi_rtt_trilateration.py` — 802.11mc RTT scan + multilateration
- `ble_rssi_filter.py` — Kalman + path-loss + AP map
- `uwb_twr.py` — Two-Way-Ranging (Decawave protocol)
- `magnetic_fingerprint_matcher.py` — particle-filter on prebuilt magnetic map
- `pdr_engine.py` — accelerometer step detection + gyro heading + barometer floor
- `indoor_fusion_ekf.py` — EKF that consumes all of the above; outputs unified pose

## Offline assets needed

- Per-floor magnetic field map (`mag_<bldg>_<floor>.npz`)
- AP location database (`wifi_aps.json` with MAC → coords)
- BLE beacon registry (`ble_beacons.json`)
- Floor plan (`floorplan_<bldg>.geojson`)

## References

- ORB-SLAM3 (GPLv3) — github.com/UZ-SLAMLab/ORB_SLAM3
- VINS-Mono (GPLv3) — github.com/HKUST-Aerial-Robotics/VINS-Mono
- IEEE 802.11mc Fine Time Measurement spec
- Apple iBeacon spec, Eddystone (Google) BLE protocol
