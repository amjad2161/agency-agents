# Tier 5 — Sensor Fusion

**Role:** combines tier 1–4 estimators into one coherent pose stream.

## Algorithms

| Filter | Use case | Pros / Cons |
|---|---|---|
| Extended Kalman Filter (EKF) | mild non-linearity, low CPU | linearization error in highly non-linear cases |
| Unscented Kalman Filter (UKF) | strong non-linearity (rotation, attitude) | better than EKF without Jacobians |
| Particle Filter (PF) | multi-modal posteriors, GPS-denied indoor | O(N particles) compute |
| Graph-based SLAM (g2o, GTSAM, Ceres) | offline / batch loop-closure | global consistency, batch-optimal |

## Components

- `ekf_inertial.py` — strapdown INS error-state EKF (±loose / ±tight GNSS)
- `ukf_attitude.py` — quaternion attitude UKF
- `particle_filter_indoor.py` — magnetic-fingerprint + WiFi PF
- `graph_slam_gtsam.py` — pose-graph optimizer wrapper
- `data_association.py` — Mahalanobis gate + JCBB
- `outlier_rejection.py` — RANSAC + chi-squared gate
- `time_sync.py` — PPS / hardware-trigger / cross-correlation

## Coordinate frames

`ECEF` ⇄ `LLA` ⇄ `NED` ⇄ `body` ⇄ `sensor`. Conversions in `frames.py`.

## References

- GTSAM (BSD) — borg.cc.gatech.edu/projects/gtsam
- g2o (BSD) — github.com/RainerKuemmerle/g2o
- Ceres Solver (BSD) — google/ceres-solver
- "Probabilistic Robotics" — Thrun, Burgard, Fox
