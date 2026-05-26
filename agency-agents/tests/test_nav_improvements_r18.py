"""GODSKILL Navigation R18 — improvement-round tests."""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.satellite import PVTSolver  # noqa: E402
from agency.navigation.indoor_inertial import MotionClassifier  # noqa: E402
from agency.navigation.indoor_slam import MonteCarloLocalization  # noqa: E402
from agency.navigation.fusion import RobustMEstimator  # noqa: E402
from agency.navigation.underwater import UnderwaterCurrentEstimator  # noqa: E402


# ============================================================================
# PVTSolver
# ============================================================================

def _pvt_setup():
    # Place 6 SVs around true position [10000, 5000, 3000] ECEF (small scale demo)
    true_pos = np.array([1e4, 5e3, 3e3])
    sv_pos = np.array([
        [2e7, 0.0, 1e7],
        [-2e7, 0.0, 1e7],
        [0.0, 2e7, 1e7],
        [0.0, -2e7, 1e7],
        [1.5e7, 1.5e7, 1e7],
        [-1.5e7, 1.5e7, 1e7],
    ])
    true_clock = 100.0  # m
    pr = np.linalg.norm(sv_pos - true_pos, axis=1) + true_clock
    return sv_pos, pr, true_pos


class TestPVTSolver:
    def test_compute_pvt_shape(self):
        s = PVTSolver()
        sv, pr, _ = _pvt_setup()
        out = s.compute_pvt(sv, pr)
        assert out.shape == (4,)

    def test_compute_pvt_position_near_truth(self):
        s = PVTSolver()
        sv, pr, true = _pvt_setup()
        s.compute_pvt(sv, pr)
        err = float(np.linalg.norm(s.position - true))
        assert err < 10.0

    def test_compute_pvt_converges(self):
        s = PVTSolver()
        sv, pr, _ = _pvt_setup()
        s.compute_pvt(sv, pr, n_iter=20)
        # Re-running should not change the state appreciably
        before = s._x.copy()
        s.compute_pvt(sv, pr, n_iter=5)
        assert float(np.linalg.norm(s._x - before)) < 1e-3

    def test_compute_dop_shape(self):
        s = PVTSolver()
        sv, pr, _ = _pvt_setup()
        s.compute_pvt(sv, pr)
        d = s.compute_dop(sv)
        assert d.shape == (4,)

    def test_hdop_le_pdop(self):
        s = PVTSolver()
        sv, pr, _ = _pvt_setup()
        s.compute_pvt(sv, pr)
        gdop, pdop, hdop, vdop = s.compute_dop(sv)
        assert hdop <= pdop + 1e-6

    def test_pdop_le_gdop(self):
        s = PVTSolver()
        sv, pr, _ = _pvt_setup()
        s.compute_pvt(sv, pr)
        gdop, pdop, hdop, vdop = s.compute_dop(sv)
        assert pdop <= gdop + 1e-6

    def test_ecef_to_lla_shape_and_range(self):
        s = PVTSolver()
        # Approximate Earth-surface point
        xyz = np.array([4510023.92, 549154.0, 4488055.5])
        lla = s.ecef_to_lla(xyz)
        assert lla.shape == (3,)
        assert -90.0 <= lla[0] <= 90.0


# ============================================================================
# MotionClassifier
# ============================================================================

class TestMotionClassifier:
    def test_push_fills_buffer(self):
        m = MotionClassifier(window=10)
        for _ in range(5):
            m.push(np.array([0.0, 0.0, 9.81]), np.zeros(3))
        assert len(m._buffer) == 5

    def test_features_shape(self):
        m = MotionClassifier(window=20)
        for _ in range(20):
            m.push(np.array([0.0, 0.0, 9.81]), np.zeros(3))
        f = m.features()
        assert f.shape == (6,)

    def test_features_accel_mean_norm_g(self):
        m = MotionClassifier(window=30)
        for _ in range(30):
            m.push(np.array([0.0, 0.0, 9.81]), np.zeros(3))
        f = m.features()
        assert abs(f[1] - 9.81) < 0.1

    def test_classify_returns_valid_state(self):
        m = MotionClassifier(window=20)
        for _ in range(20):
            m.push(np.array([0.0, 0.0, 9.81]), np.zeros(3))
        st = m.classify()
        assert st in MotionClassifier.STATES

    def test_classify_stationary(self):
        m = MotionClassifier(window=30)
        for _ in range(30):
            m.push(np.array([0.0, 0.0, 9.81]), np.zeros(3))
        assert m.classify() == "stationary"

    def test_classify_walking_sinusoid(self):
        m = MotionClassifier(window=128, fs=50.0)
        # Synthesize 1.5 Hz sinusoid in accel z
        n = 128
        t = np.arange(n) / 50.0
        for k in range(n):
            a = np.array([0.0, 0.0, 9.81 + 1.0 * math.sin(2 * math.pi * 1.5 * t[k])])
            g = np.array([0.0, 0.0, 0.1 * math.sin(2 * math.pi * 1.5 * t[k])])
            m.push(a, g)
        assert m.classify() == "walking"

    def test_state_property_updated(self):
        m = MotionClassifier(window=20)
        for _ in range(20):
            m.push(np.array([0.0, 0.0, 9.81]), np.zeros(3))
        m.classify()
        assert m.state in MotionClassifier.STATES


# ============================================================================
# MonteCarloLocalization
# ============================================================================

def _make_map(size: int = 20):
    m = np.ones((size, size), dtype=bool)
    m[0, :] = False; m[-1, :] = False
    m[:, 0] = False; m[:, -1] = False
    return m


class TestMonteCarloLocalization:
    def test_init_n_particles(self):
        mcl = MonteCarloLocalization(_make_map(), n_particles=200)
        assert mcl.n_particles == 200

    def test_particles_shape(self):
        mcl = MonteCarloLocalization(_make_map(), n_particles=100)
        assert mcl._particles.shape == (100, 3)

    def test_predict_spreads_particles(self):
        mcl = MonteCarloLocalization(_make_map(), n_particles=100)
        before = mcl._particles.copy()
        mcl.predict(0.5, 0.0, 0.1, noise=0.05)
        assert not np.allclose(before, mcl._particles)

    def test_weight_changes_weights(self):
        mcl = MonteCarloLocalization(_make_map(), n_particles=100)
        before = mcl._weights.copy()
        mcl.weight(np.array([0.5, 0.6]), np.array([0.0, math.pi / 2]))
        assert not np.allclose(before, mcl._weights)

    def test_weights_sum_to_one(self):
        mcl = MonteCarloLocalization(_make_map(), n_particles=100)
        mcl.weight(np.array([0.5]), np.array([0.0]))
        assert float(mcl._weights.sum()) == pytest.approx(1.0)

    def test_resample_keeps_n(self):
        mcl = MonteCarloLocalization(_make_map(), n_particles=100)
        mcl.weight(np.array([0.5]), np.array([0.0]))
        mcl.resample()
        assert mcl._particles.shape[0] == 100

    def test_estimate_shape(self):
        mcl = MonteCarloLocalization(_make_map(), n_particles=100)
        est = mcl.estimate()
        assert est.shape == (3,)


# ============================================================================
# RobustMEstimator
# ============================================================================

class TestRobustMEstimator:
    def test_huber_weight_one_for_small(self):
        m = RobustMEstimator()
        assert m.huber_weight(0.5) == pytest.approx(1.0)

    def test_huber_weight_lt_one_for_large(self):
        m = RobustMEstimator()
        assert m.huber_weight(5.0) < 1.0

    def test_tukey_weight_zero_beyond_c(self):
        m = RobustMEstimator()
        assert m.tukey_weight(5.0, c=4.685) == pytest.approx(0.0)

    def test_tukey_weight_one_at_zero(self):
        m = RobustMEstimator()
        assert m.tukey_weight(0.0) == pytest.approx(1.0)

    def test_robust_update_shape(self):
        m = RobustMEstimator(state_dim=3, obs_dim=1)
        out = m.robust_update(np.array([1.0]), mode="huber")
        assert out.shape == (3,)

    def test_huber_outlier_smaller_step(self):
        m1 = RobustMEstimator(state_dim=3, obs_dim=1)
        m2 = RobustMEstimator(state_dim=3, obs_dim=1)
        # Inlier vs outlier: outlier should produce smaller relative shift
        m1.robust_update(np.array([1.0]), mode="huber")
        m2.robust_update(np.array([100.0]), mode="huber")
        # |dx_outlier|/100 < |dx_inlier|/1 → robust downweighting
        assert abs(m2.x[0]) / 100.0 < abs(m1.x[0]) / 1.0

    def test_predict_advances_state(self):
        m = RobustMEstimator(state_dim=2, obs_dim=1)
        m.x = np.array([0.0, 1.0])
        F = np.array([[1.0, 1.0], [0.0, 1.0]])
        Q = np.eye(2) * 0.01
        m.predict(F, Q)
        assert m.x[0] == pytest.approx(1.0)


# ============================================================================
# UnderwaterCurrentEstimator
# ============================================================================

class TestUnderwaterCurrentEstimator:
    def test_update_changes_estimate(self):
        u = UnderwaterCurrentEstimator(alpha=0.5)
        before = u._current.copy()
        u.update(np.array([1.0, 0.0, 0.0]), np.array([0.0, 0.0, 0.0]))
        assert not np.allclose(before, u._current)

    def test_alpha_one_matches_raw(self):
        u = UnderwaterCurrentEstimator(alpha=1.0)
        u.update(np.array([2.0, -1.0, 0.5]), np.zeros(3))
        assert np.allclose(u._current, np.array([2.0, -1.0, 0.5]))

    def test_compensate_dvl_shape(self):
        u = UnderwaterCurrentEstimator()
        out = u.compensate_dvl(np.array([1.0, 0.0, 0.0]), np.eye(3))
        assert out.shape == (3,)

    def test_current_magnitude_non_negative(self):
        u = UnderwaterCurrentEstimator()
        u.update(np.array([1.0, 0.5, 0.0]), np.zeros(3))
        assert u.current_magnitude() >= 0.0

    def test_current_direction_in_range(self):
        u = UnderwaterCurrentEstimator(alpha=1.0)
        u.update(np.array([0.0, 1.0, 0.0]), np.zeros(3))
        d = u.current_direction_deg()
        assert 0.0 <= d < 360.0

    def test_reset_clears_current(self):
        u = UnderwaterCurrentEstimator(alpha=1.0)
        u.update(np.array([3.0, 0.0, 0.0]), np.zeros(3))
        u.reset()
        assert np.allclose(u._current, 0.0)
        assert u._history == []

    def test_history_accumulates(self):
        u = UnderwaterCurrentEstimator()
        for _ in range(5):
            u.update(np.array([1.0, 0.0, 0.0]), np.zeros(3))
        assert len(u._history) == 5
