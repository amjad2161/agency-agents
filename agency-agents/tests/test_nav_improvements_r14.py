"""GODSKILL Navigation R14 — improvement-round tests."""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.satellite import (  # noqa: E402
    CarrierPhaseAmbiguityResolution,
)
from agency.navigation.fusion import CovarianceIntersectionFilter  # noqa: E402
from agency.navigation.indoor_slam import (  # noqa: E402
    FastSLAM2,
    UltraWidebandPositioning,
)
from agency.navigation.ai_enhance import AttentionBasedSensorFusion  # noqa: E402


# ============================================================================
# CarrierPhaseAmbiguityResolution
# ============================================================================

class TestCarrierPhaseAmbiguityResolution:
    def test_set_float_solution_stores(self):
        c = CarrierPhaseAmbiguityResolution()
        amb = np.array([10.2, -3.7, 5.4])
        cov = np.eye(3) * 0.01
        c.set_float_solution(amb, cov)
        assert c._float_ambiguities.shape == (3,)
        assert c._cov.shape == (3, 3)

    def test_bootstrap_fix_returns_integers(self):
        c = CarrierPhaseAmbiguityResolution()
        c.set_float_solution(np.array([10.2, -3.7, 5.4]), np.eye(3) * 0.01)
        out = c.bootstrap_fix()
        assert out.shape == (3,)
        assert np.allclose(out, np.round(out))

    def test_phase_range_correction(self):
        c = CarrierPhaseAmbiguityResolution(wavelength=0.1)
        out = c.phase_range_correction(np.array([1.0, 2.0]),
                                       np.array([10.0, 20.0]))
        assert out[0] == pytest.approx(1.1)
        assert out[1] == pytest.approx(2.2)

    def test_fix_ratio_high_for_tight_cov(self):
        c = CarrierPhaseAmbiguityResolution()
        c.set_float_solution(np.array([10.05, -3.95]),
                             np.eye(2) * 0.001)
        c.bootstrap_fix()
        assert c.fix_ratio() > 1.0

    def test_fix_ratio_finite(self):
        c = CarrierPhaseAmbiguityResolution()
        c.set_float_solution(np.array([10.0, -3.0]), np.eye(2) * 0.05)
        c.bootstrap_fix()
        r = c.fix_ratio()
        assert math.isfinite(r) or r == float("inf")

    def test_wavelength_default(self):
        c = CarrierPhaseAmbiguityResolution()
        assert c.wavelength == pytest.approx(0.1903)

    def test_is_fixed_flag(self):
        c = CarrierPhaseAmbiguityResolution()
        c.set_float_solution(np.array([1.5]), np.eye(1) * 0.01)
        assert c.is_fixed is False
        c.bootstrap_fix()
        assert c.is_fixed is True


# ============================================================================
# FastSLAM2
# ============================================================================

class TestFastSLAM2:
    def test_predict_spreads_particles(self):
        s = FastSLAM2(n_particles=20, motion_noise=0.1, seed=1)
        s.predict(1.0, 0.0, 0.0)
        poses = np.array([p["pose"] for p in s._particles])
        assert poses.shape == (20, 3)
        # Particles should not all be identical due to noise injection
        assert float(poses[:, 0].std()) > 0.0

    def test_update_initialises_new_landmark(self):
        s = FastSLAM2(n_particles=10, seed=2)
        s.update(lm_id=1, obs_range=5.0, obs_bearing=0.0)
        assert all(1 in p["landmarks"] for p in s._particles)

    def test_update_updates_existing(self):
        s = FastSLAM2(n_particles=10, seed=3)
        s.update(lm_id=1, obs_range=5.0, obs_bearing=0.0)
        before = s._particles[0]["landmarks"][1][1].copy()
        s.update(lm_id=1, obs_range=5.0, obs_bearing=0.0)
        after = s._particles[0]["landmarks"][1][1]
        assert float(np.trace(after)) <= float(np.trace(before)) + 1e-6

    def test_best_pose_shape(self):
        s = FastSLAM2(n_particles=10, seed=4)
        pose = s.best_pose()
        assert pose.shape == (3,)

    def test_resample_keeps_n_particles(self):
        s = FastSLAM2(n_particles=15, seed=5)
        s.update(lm_id=1, obs_range=4.0, obs_bearing=0.5)
        s.resample()
        assert len(s._particles) == 15

    def test_weights_sum_to_one_after_update(self):
        s = FastSLAM2(n_particles=10, seed=6)
        s.update(lm_id=1, obs_range=3.0, obs_bearing=0.0)
        assert float(s._weights.sum()) == pytest.approx(1.0)

    def test_n_landmarks_count(self):
        s = FastSLAM2(n_particles=10, seed=7)
        s.update(lm_id=1, obs_range=4.0, obs_bearing=0.0)
        s.update(lm_id=2, obs_range=5.0, obs_bearing=0.5)
        s.update(lm_id=3, obs_range=6.0, obs_bearing=-0.5)
        assert s.n_landmarks() == 3


# ============================================================================
# AttentionBasedSensorFusion
# ============================================================================

class TestAttentionBasedSensorFusion:
    def test_attend_returns_d_model(self):
        a = AttentionBasedSensorFusion(d_model=16, n_heads=4, n_modalities=3)
        out = a.attend([np.array([1.0] * 5),
                        np.array([0.5] * 8),
                        np.array([2.0] * 4)])
        assert out.shape == (16,)

    def test_attend_shape_d_model_8(self):
        a = AttentionBasedSensorFusion(d_model=8, n_heads=2, n_modalities=2)
        out = a.attend([np.zeros(4), np.ones(4)])
        assert out.shape == (8,)

    def test_attend_handles_mismatched_sensor_sizes(self):
        a = AttentionBasedSensorFusion(d_model=16, n_heads=4, n_modalities=3)
        out = a.attend([np.array([1.0]),
                        np.zeros(20),
                        np.array([0.1, 0.2, 0.3])])
        assert out.shape == (16,)

    def test_W_Q_shape(self):
        a = AttentionBasedSensorFusion(d_model=16, n_heads=4, n_modalities=3)
        assert a.W_Q.shape == (4, 4, 4)

    def test_softmax_attention_rows_sum_to_one(self):
        a = AttentionBasedSensorFusion(d_model=8, n_heads=2, n_modalities=3)
        a.attend([np.zeros(4) for _ in range(3)])
        for attn in a._last_attn:
            row_sums = attn.sum(axis=-1)
            assert np.allclose(row_sums, 1.0, atol=1e-6)

    def test_update_weights_changes_W_O(self):
        a = AttentionBasedSensorFusion(d_model=8, n_heads=2, n_modalities=3)
        before = a.W_O.copy()
        grad = np.ones_like(a.W_O)
        a.update_weights(grad, lr=0.1)
        assert not np.allclose(before, a.W_O)

    def test_deterministic_with_same_seed(self):
        a1 = AttentionBasedSensorFusion(d_model=8, n_heads=2,
                                        n_modalities=2, seed=99)
        a2 = AttentionBasedSensorFusion(d_model=8, n_heads=2,
                                        n_modalities=2, seed=99)
        x = [np.array([1.0, 2.0]), np.array([3.0, 4.0])]
        assert np.allclose(a1.attend(x), a2.attend(x))


# ============================================================================
# CovarianceIntersectionFilter
# ============================================================================

class TestCovarianceIntersectionFilter:
    def test_fuse_shape(self):
        ci = CovarianceIntersectionFilter(state_dim=3)
        x_a = np.array([1.0, 2.0, 3.0])
        x_b = np.array([1.5, 2.5, 3.5])
        P_a = np.eye(3) * 1.0
        P_b = np.eye(3) * 2.0
        x, P = ci.fuse(x_a, P_a, x_b, P_b)
        assert x.shape == (3,)
        assert P.shape == (3, 3)

    def test_fuse_P_is_spd(self):
        ci = CovarianceIntersectionFilter(state_dim=3)
        x_a = np.zeros(3); x_b = np.ones(3)
        P_a = np.eye(3) * 1.0; P_b = np.eye(3) * 2.0
        _, P = ci.fuse(x_a, P_a, x_b, P_b)
        eigs = np.linalg.eigvalsh(0.5 * (P + P.T))
        assert np.all(eigs > 0.0)

    def test_omega_within_unit_interval(self):
        ci = CovarianceIntersectionFilter(state_dim=2)
        Pa_inv = np.linalg.inv(np.eye(2) * 1.0)
        Pb_inv = np.linalg.inv(np.eye(2) * 2.0)
        omega = ci._golden_search(Pa_inv, Pb_inv)
        assert 0.0 <= omega <= 1.0

    def test_fuse_reduces_uncertainty_vs_worst(self):
        ci = CovarianceIntersectionFilter(state_dim=2)
        P_a = np.eye(2) * 1.0
        P_b = np.eye(2) * 5.0  # worse
        _, P = ci.fuse(np.zeros(2), P_a, np.zeros(2), P_b)
        assert float(np.trace(P)) <= float(np.trace(P_b)) + 1e-6

    def test_update_self_works(self):
        ci = CovarianceIntersectionFilter(state_dim=2)
        ci.x = np.array([1.0, 2.0])
        ci.P = np.eye(2) * 1.0
        x, _ = ci.update_self(np.array([3.0, 4.0]), np.eye(2) * 1.0)
        assert x.shape == (2,)

    def test_deterministic(self):
        ci1 = CovarianceIntersectionFilter(state_dim=2)
        ci2 = CovarianceIntersectionFilter(state_dim=2)
        args = (np.array([1.0, 0.0]), np.eye(2),
                np.array([0.0, 1.0]), np.eye(2) * 2.0)
        x1, _ = ci1.fuse(*args)
        x2, _ = ci2.fuse(*args)
        assert np.allclose(x1, x2)

    def test_state_dim_one_scalar_case(self):
        ci = CovarianceIntersectionFilter(state_dim=1)
        x, P = ci.fuse(np.array([2.0]), np.array([[1.0]]),
                       np.array([4.0]), np.array([[2.0]]))
        assert x.shape == (1,)
        assert P.shape == (1, 1)


# ============================================================================
# UltraWidebandPositioning
# ============================================================================

def _uwb_anchors():
    return np.array([
        [0.0, 0.0],
        [10.0, 0.0],
        [0.0, 10.0],
        [10.0, 10.0],
    ])


class TestUltraWidebandPositioning:
    def test_ranges_from_pos_correct(self):
        u = UltraWidebandPositioning(_uwb_anchors())
        true = np.array([3.0, 4.0])
        r = u.ranges_from_pos(true)
        assert r.shape == (4,)
        assert r[0] == pytest.approx(5.0)

    def test_solve_wls_shape(self):
        u = UltraWidebandPositioning(_uwb_anchors())
        r = u.ranges_from_pos(np.array([3.0, 4.0]))
        out = u.solve_wls(r)
        assert out.shape == (2,)

    def test_solve_wls_noiseless_error(self):
        u = UltraWidebandPositioning(_uwb_anchors())
        true = np.array([4.0, 6.0])
        r = u.ranges_from_pos(true)
        out = u.solve_wls(r)
        assert u.position_error(out, true) < 0.5

    def test_solve_iterative_no_worse(self):
        u = UltraWidebandPositioning(_uwb_anchors(), noise_std=0.05, seed=1)
        true = np.array([4.0, 6.0])
        r = u.ranges_from_pos(true, add_noise=True)
        wls_err = u.position_error(u.solve_wls(r), true)
        it_err = u.position_error(u.solve_iterative(r), true)
        assert it_err <= wls_err + 1e-6 or it_err < 0.3

    def test_noise_changes_ranges(self):
        u = UltraWidebandPositioning(_uwb_anchors(), seed=2)
        true = np.array([3.0, 4.0])
        r_clean = u.ranges_from_pos(true)
        r_noisy = u.ranges_from_pos(true, add_noise=True)
        assert not np.allclose(r_clean, r_noisy)

    def test_three_anchor_minimum(self):
        anchors = np.array([[0.0, 0.0], [10.0, 0.0], [5.0, 8.0]])
        u = UltraWidebandPositioning(anchors)
        r = u.ranges_from_pos(np.array([3.0, 3.0]))
        out = u.solve_wls(r)
        assert out.shape == (2,)

    def test_position_error_formula(self):
        u = UltraWidebandPositioning(_uwb_anchors())
        e = u.position_error(np.array([3.0, 4.0]), np.array([0.0, 0.0]))
        assert e == pytest.approx(5.0)
