# Tier 6 — AI / ML Enhancement

**Role:** learn priors and corrections that classical estimators can't capture.

## Components

- `radio_map_learner.py` — deep model that predicts WiFi/BLE/cellular RSSI from (x,y,floor); trained on crowd-sourced fingerprints
- `scene_recognition.py` — ResNet50 / ViT-B/16 → scene class + global-localization prior
- `neural_slam.py` — DROID-SLAM / NeRF-SLAM wrappers; differentiable bundle adjustment
- `trajectory_lstm.py` — LSTM motion-prediction (gait, vehicle dynamics)
- `uncertainty_quantification.py` — Deep Ensembles / MC-Dropout calibrated covariance
- `transfer_learning.py` — fine-tune scene/radio models on new sites with ≤ 100 samples

## Models to ship offline

- ResNet50 ImageNet (98 MB int8)
- MobileNetV3-Small (5 MB int8) — for edge inference
- DROID-SLAM weights (1.2 GB) — optional; only if compute budget allows
- Tiny radio-map model (1–5 MB per building)

## References

- DROID-SLAM (MIT) — github.com/princeton-vl/DROID-SLAM
- NeRF-SLAM, iMAP, NICE-SLAM
- "Deep Ensembles for Uncertainty" — Lakshminarayanan 2017
- Radio-map learning surveys 2024–2025 (arXiv)
