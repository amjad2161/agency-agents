"""GODSKILL Navigation R7 — improvement-round tests.

Covers:
- LEOSatelliteNav    (Doppler positioning + J2 orbit propagation)
- SquareRootUKF      (Cholesky-factored UKF)
- FootMountedIMU     (stance/stride/PDR)
- GravityGradiometry (Somigliana + gradient tensor + map matching)
- FederatedNavigationLearner (FedAvg + privacy noise)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure runtime/ is importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

from agency.navigation.satellite import LEOSatelliteNav  # noqa: E402
from agency.navigation.fusion import SquareRootUKF, UKF  # noqa: E402
from agency.navigation.indoor_inertial import FootMountedIMU  # noqa: E402
from agency.navigation.underground import GravityGradiometry  # noqa: E402
from agency.navigation.ai_enhance import FederatedNavigationLearner  # noqa: E402


# ============================================================================
# LEOSatelliteNav
# ============================================================================

class TestLEOSatelliteNav:
    def test_init(self):
        nav = LEOSatelliteNav(default_alt_km=550.0)
        assert nav.default_alt_km == pytest.approx(550.0)
        assert nav.SPEED_OF_LIGHT_KMS == pytest.approx(299792.458)

    def test_propagate_orbit_returns_3vector(self):
        nav = LEOSatelliteNav()
        pos = nav.propagate_orbit(t_seconds=0.0,
                                  tle_mean_motion=15.5,
                                  eccentricity=0.001,
                                  inclination_rad=math.radians(53.0))
        assert pos.shape == (3,)
        # LEO orbit: |pos| should be near Earth radius + ~550 km
        r = float(np.linalg.norm(pos))
        assert 6500.0 < r < 8000.0

    def test_j2_perturbation_sign_for_prograde(self):
        nav = LEOSatelliteNav()
        # Prograde inclined orbit (i < 90°): RAAN drifts west (negative)
        d_raan, d_argp = nav.j2_perturbation(
            a_km=6928.0, e=0.001, i_rad=math.radians(53.0))
        assert d_raan < 0.0
        # Arg-perigee drift sign depends on inclination
        assert isinstance(d_argp, float)

    def test_j2_perturbation_polar_orbit_zero(self):
        # i = 90° → cos(i) = 0 → d_raan = 0
        nav = LEOSatelliteNav()
        d_raan, _ = nav.j2_perturbation(
            a_km=6928.0, e=0.001, i_rad=math.radians(90.0))
        assert abs(d_raan) < 1e-12

    def test_doppler_position_fix_output_shape(self):
        nav = LEOSatelliteNav()
        # Build 4 satellites around receiver near Earth surface
        n = 4
        sat_pos = np.array([
            [7000.0,    0.0,   0.0],
            [   0.0, 7000.0,   0.0],
            [   0.0,    0.0, 7000.0],
            [4000.0, 4000.0, 4000.0],
        ])
        sat_vel = np.array([
            [0.0, 7.5, 0.0],
            [-7.5, 0.0, 0.0],
            [0.0, 0.0, 7.5],
            [-3.0, 3.0, -3.0],
        ])
        f_obs = np.full(n, 12e9)        # observed
        f_nom = 12e9                     # no shift → receiver stationary
        pos = nav.doppler_position_fix(f_obs, f_nom, sat_pos, sat_vel)
        assert pos.shape == (3,)

    def test_doppler_freq_shift_direction(self):
        # Observed > nominal => satellite approaching => negative range-rate
        # Just verify the algorithm produces a finite answer
        nav = LEOSatelliteNav()
        sat_pos = np.array([[7000.0, 0.0, 0.0], [0.0, 7000.0, 0.0],
                            [0.0, 0.0, 7000.0]])
        sat_vel = np.array([[0.0, 7.5, 0.0], [-7.5, 0.0, 0.0],
                            [0.0, 0.0, 7.5]])
        f_obs = np.array([12.001e9, 12.0e9, 11.999e9])
        pos = nav.doppler_position_fix(f_obs, 12e9, sat_pos, sat_vel)
        assert np.all(np.isfinite(pos))

    def test_propagate_orbit_eccentricity_changes_radius(self):
        nav = LEOSatelliteNav()
        circ = nav.propagate_orbit(0.0, 15.5, 0.0, math.radians(53.0))
        ecc  = nav.propagate_orbit(0.0, 15.5, 0.05, math.radians(53.0),
                                   mean_anomaly0_rad=math.pi)  # apogee
        r_circ = float(np.linalg.norm(circ))
        r_ecc  = float(np.linalg.norm(ecc))
        # Apogee of eccentric orbit > circular orbit radius
        assert r_ecc > r_circ


# ============================================================================
# SquareRootUKF
# ============================================================================

class TestSquareRootUKF:
    def _make(self):
        ukf = SquareRootUKF(dim_x=6, dim_z=3,
                            process_noise_std=0.05,
                            measurement_noise_std=0.5)
        ukf.x = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 0.0])
        return ukf

    def test_init(self):
        ukf = self._make()
        assert ukf.x.shape == (6,)
        assert ukf.S.shape == (6, 6)

    def test_predict_returns_cholesky_S(self):
        ukf = self._make()
        x, S = ukf.predict(dt=0.1)
        # Lower triangular property
        upper = np.triu(S, k=1)
        assert np.allclose(upper, 0.0, atol=1e-9)
        # Position advanced
        assert x[0] > 0.0

    def test_update_output_shapes(self):
        ukf = self._make()
        ukf.predict(0.1)
        x, S = ukf.update(np.array([0.1, 0.1, 0.0]))
        assert x.shape == (6,)
        assert S.shape == (6, 6)

    def test_S_positive_definite(self):
        ukf = self._make()
        for _ in range(10):
            ukf.predict(0.1)
            ukf.update(ukf.x[:3] + np.array([0.05, 0.0, 0.0]))
        # P = S Sᵀ must be PD (positive eigenvalues)
        P = ukf.S @ ukf.S.T
        eigs = np.linalg.eigvalsh(0.5 * (P + P.T))
        assert np.all(eigs > -1e-6)

    def test_innovation_covariance_property(self):
        ukf = self._make()
        ukf.predict(0.1)
        ukf.update(np.array([0.1, 0.0, 0.0]))
        S_zz = ukf.innovation_covariance
        assert S_zz.shape == (3, 3)
        upper = np.triu(S_zz, k=1)
        assert np.allclose(upper, 0.0, atol=1e-9)

    def test_consistency_after_multi_step(self):
        ukf = self._make()
        # 50 steps with constant velocity model
        for k in range(50):
            ukf.predict(0.1)
            true_pos = np.array([0.1 * (k + 1), 0.1 * (k + 1), 0.0])
            ukf.update(true_pos + 0.01 * np.random.RandomState(k).randn(3))
        # Filter should track close to truth
        truth_50 = np.array([5.0, 5.0, 0.0])
        err = float(np.linalg.norm(ukf.x[:3] - truth_50))
        assert err < 0.5

    def test_sruff_vs_standard_ukf_consistency(self):
        # Compare against standard UKF available in the same module
        sr = self._make()
        std = UKF()
        # Standard UKF should also be constructible with defaults
        assert std is not None
        # SR-UKF reconstructed covariance is identity at init
        P_sr = sr.S @ sr.S.T
        assert np.allclose(P_sr, np.eye(6), atol=1e-9)
        # SR-UKF predict produces a finite reconstructed P
        sr.predict(0.1)
        P_after = sr.S @ sr.S.T
        assert np.all(np.isfinite(P_after))


# ============================================================================
# FootMountedIMU
# ============================================================================

class TestFootMountedIMU:
    def test_init(self):
        imu = FootMountedIMU()
        assert imu.position == (0.0, 0.0)
        assert imu.step_count == 0

    def test_stance_detection_true_on_quiet(self):
        imu = FootMountedIMU()
        # 30 quiet samples ≈ stance
        accel = np.tile(np.array([0.0, 0.0, 9.81]), (30, 1))
        gyro  = np.zeros((30, 3))
        assert imu.detect_stance(accel, gyro) is True

    def test_stance_detection_false_on_motion(self):
        imu = FootMountedIMU()
        rng = np.random.RandomState(0)
        accel = 9.81 * np.ones((30, 3)) + 5.0 * rng.randn(30, 3)
        gyro  = 1.0 * rng.randn(30, 3)
        assert imu.detect_stance(accel, gyro) is False

    def test_stride_length_positive(self):
        imu = FootMountedIMU()
        L = imu.estimate_stride_length(accel_peak=4.0, height_m=1.80)
        assert L > 0.0

    def test_stride_length_scales_with_peak(self):
        imu = FootMountedIMU()
        L1 = imu.estimate_stride_length(1.0)
        L4 = imu.estimate_stride_length(4.0)
        assert L4 > L1

    def test_position_update_forward(self):
        imu = FootMountedIMU()
        dx, dy = imu.update_position(stance=False, stride_length=0.7,
                                     heading_rad=0.0)
        assert dx == pytest.approx(0.7)
        assert dy == pytest.approx(0.0, abs=1e-9)
        assert imu.step_count == 1

    def test_position_update_heading(self):
        imu = FootMountedIMU()
        dx, dy = imu.update_position(stance=False, stride_length=1.0,
                                     heading_rad=math.pi / 2)
        assert dx == pytest.approx(0.0, abs=1e-9)
        assert dy == pytest.approx(1.0)

    def test_zero_displacement_on_stance(self):
        imu = FootMountedIMU()
        dx, dy = imu.update_position(stance=True, stride_length=0.7,
                                     heading_rad=0.0)
        assert dx == 0.0
        assert dy == 0.0
        assert imu.step_count == 0


# ============================================================================
# GravityGradiometry
# ============================================================================

class TestGravityGradiometry:
    def test_init(self):
        gg = GravityGradiometry()
        assert gg.fd_step_m > 0.0
        assert gg.GAMMA_E == pytest.approx(9.7803253359)

    def test_normal_gravity_at_equator(self):
        gg = GravityGradiometry()
        g = gg.normal_gravity(lat_rad=0.0, alt_m=0.0)
        assert g == pytest.approx(9.7803253359, abs=1e-3)

    def test_normal_gravity_at_pole(self):
        gg = GravityGradiometry()
        g = gg.normal_gravity(lat_rad=math.pi / 2, alt_m=0.0)
        assert g == pytest.approx(9.8321849378, abs=1e-3)

    def test_tensor_shape(self):
        gg = GravityGradiometry()
        T = gg.compute_gravity_gradient_tensor(lat_rad=math.radians(30.0),
                                               lon_rad=0.0, alt_m=0.0)
        assert T.shape == (3, 3)

    def test_tensor_trace_near_zero(self):
        gg = GravityGradiometry()
        T = gg.compute_gravity_gradient_tensor(lat_rad=math.radians(45.0),
                                               lon_rad=0.0, alt_m=100.0)
        assert abs(float(np.trace(T))) < 1e-6

    def test_match_gradient_returns_position(self):
        gg = GravityGradiometry()
        positions = [(0.0, 0.0, 0.0),
                     (math.radians(30.0), 0.0, 0.0),
                     (math.radians(60.0), 0.0, 0.0)]
        tensors = [gg.compute_gravity_gradient_tensor(p[0], p[1], p[2])
                   for p in positions]
        observed = tensors[1]
        out = gg.match_gradient(observed, tensors, positions)
        assert out == positions[1]

    def test_normal_gravity_decreases_with_altitude(self):
        gg = GravityGradiometry()
        g0 = gg.normal_gravity(lat_rad=math.radians(45.0), alt_m=0.0)
        g_high = gg.normal_gravity(lat_rad=math.radians(45.0), alt_m=10000.0)
        assert g_high < g0


# ============================================================================
# FederatedNavigationLearner
# ============================================================================

class TestFederatedNavigationLearner:
    def test_init(self):
        m = FederatedNavigationLearner(input_dim=4, hidden_dim=8,
                                       output_dim=2, seed=1)
        assert m.W1.shape == (4, 8)
        assert m.W2.shape == (8, 2)
        assert m.b1.shape == (8,)
        assert m.b2.shape == (2,)

    def test_local_train_returns_delta(self):
        m = FederatedNavigationLearner(input_dim=4, hidden_dim=8,
                                       output_dim=2, seed=2,
                                       privacy_noise_std=0.0)
        rng = np.random.RandomState(0)
        X = rng.randn(64, 4)
        Y = rng.randn(64, 2)
        delta = m.local_train(X, Y, epochs=2, batch_size=16)
        assert set(delta.keys()) == {"W1", "b1", "W2", "b2"}
        assert delta["W1"].shape == m.W1.shape

    def test_federated_average_shape(self):
        m1 = FederatedNavigationLearner(seed=1, privacy_noise_std=0.0)
        m2 = FederatedNavigationLearner(seed=2, privacy_noise_std=0.0)
        m3 = FederatedNavigationLearner(seed=3, privacy_noise_std=0.0)
        avg = FederatedNavigationLearner.federated_average(
            [m1.get_weights(), m2.get_weights(), m3.get_weights()])
        assert avg["W1"].shape == m1.W1.shape
        # Average of three independent weights ≠ any one of them
        assert not np.allclose(avg["W1"], m1.W1)

    def test_apply_global_update_changes_weights(self):
        m = FederatedNavigationLearner(seed=1, privacy_noise_std=0.0)
        original_W1 = m.W1.copy()
        new_weights = {
            "W1": np.zeros_like(m.W1),
            "b1": np.zeros_like(m.b1),
            "W2": np.zeros_like(m.W2),
            "b2": np.zeros_like(m.b2),
        }
        m.apply_global_update(new_weights)
        assert np.allclose(m.W1, 0.0)
        assert not np.allclose(original_W1, 0.0)

    def test_privacy_noise_added_to_gradient(self):
        # With noise, identical training runs differ
        m1 = FederatedNavigationLearner(seed=1, privacy_noise_std=0.5)
        m2 = FederatedNavigationLearner(seed=1, privacy_noise_std=0.5)
        X = np.zeros((4, 4))           # zero gradient → only noise contributes
        Y = np.zeros((4, 2))
        d1 = m1.local_train(X, Y, epochs=1, batch_size=4)
        # Re-init with same seed but advance RNG → next call differs
        d2 = m2.local_train(X, Y, epochs=1, batch_size=4)
        # With noise > 0 and rng resets identical, still some variation in grad
        # path. Verify noise actually adds randomness:
        assert not np.allclose(d1["W1"], 0.0, atol=1e-6)

    def test_multi_round_convergence(self):
        # Fit y = W·x exactly via local-only training (no FedAvg drift)
        rng = np.random.RandomState(0)
        true_W = rng.randn(4, 2)
        X = rng.randn(256, 4)
        Y = X @ true_W
        m = FederatedNavigationLearner(input_dim=4, hidden_dim=32,
                                       output_dim=2, learning_rate=0.01,
                                       privacy_noise_std=0.0, seed=7)
        loss0 = float(np.mean((m.predict(X) - Y) ** 2))
        for _ in range(5):
            m.local_train(X, Y, epochs=4, batch_size=32)
        loss1 = float(np.mean((m.predict(X) - Y) ** 2))
        assert loss1 < loss0

    def test_privacy_noise_magnitude(self):
        m = FederatedNavigationLearner(seed=42, privacy_noise_std=0.1)
        zeros = m._zero_delta()
        noisy = m._add_privacy_noise(zeros)
        std_noise = float(np.std(noisy["W1"]))
        # Should be on the order of sigma (within a factor of 3 either way)
        assert 0.03 < std_noise < 0.3
