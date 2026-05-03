"""GODSKILL Navigation R20 — improvement-round tests."""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.satellite import GNSSSpoofingDetector  # noqa: E402
from agency.navigation.indoor_slam import NeuralSLAM  # noqa: E402
from agency.navigation.ai_enhance import SceneRecognizerR20 as SceneRecognizer  # noqa: E402
from agency.navigation.fusion import ConstrainedKalmanFilter  # noqa: E402
from agency.navigation.underwater import USBLPositionerR20 as USBLPositioner  # noqa: E402


# ============================================================================
# GNSSSpoofingDetector
# ============================================================================

class TestGNSSSpoofingDetector:
    def test_update_agc_first_call_baseline(self):
        d = GNSSSpoofingDetector()
        a = d.update_agc(40.0)
        assert a == GNSSSpoofingDetector.ALERT_NONE
        assert d._agc_baseline == pytest.approx(40.0)

    def test_update_agc_detects_drop(self):
        d = GNSSSpoofingDetector(agc_drop_threshold=6.0)
        d.update_agc(40.0)
        a = d.update_agc(30.0)
        assert a == GNSSSpoofingDetector.ALERT_SPOOF

    def test_check_cn0_low_returns_alert(self):
        d = GNSSSpoofingDetector(cn0_threshold=35.0)
        a = d.check_cn0(np.array([20.0, 22.0, 25.0]))
        assert a >= GNSSSpoofingDetector.ALERT_SUSPECT

    def test_check_cn0_normal_returns_none(self):
        d = GNSSSpoofingDetector(cn0_threshold=35.0)
        a = d.check_cn0(np.array([42.0, 38.0, 45.0, 40.0, 39.0]))
        assert a == GNSSSpoofingDetector.ALERT_NONE

    def test_check_position_jump_detects_large(self):
        d = GNSSSpoofingDetector(pos_jump_m=50.0)
        d.check_position_jump(np.array([0.0, 0.0, 0.0]))
        a = d.check_position_jump(np.array([100.0, 0.0, 0.0]))
        assert a == GNSSSpoofingDetector.ALERT_SPOOF

    def test_check_clock_jump_detects(self):
        d = GNSSSpoofingDetector()
        a = d.check_clock_jump(2000.0, 0.0, max_rate_m_s=1000.0)
        assert a == GNSSSpoofingDetector.ALERT_SPOOF

    def test_composite_alert_returns_max(self):
        d = GNSSSpoofingDetector()
        out = d.composite_alert(0, 1, 2, 0)
        assert out == GNSSSpoofingDetector.ALERT_SPOOF


# ============================================================================
# NeuralSLAM
# ============================================================================

class TestNeuralSLAM:
    def test_forward_shape(self):
        n = NeuralSLAM(state_dim=3, obs_dim=4, seed=1)
        z, h = n._forward(np.zeros(3))
        assert z.shape == (4,)
        assert h.shape == (n.hidden,)

    def test_jacobian_shape(self):
        n = NeuralSLAM(state_dim=3, obs_dim=4, seed=2)
        J = n._jacobian(np.array([0.1, 0.2, 0.3]))
        assert J.shape == (4, 3)

    def test_predict_advances_x(self):
        n = NeuralSLAM(state_dim=3, obs_dim=4)
        n.x = np.array([1.0, 2.0, 3.0])
        F = np.eye(3) * 2.0
        Q = np.eye(3) * 0.01
        n.predict(F, Q)
        assert np.allclose(n.x, [2.0, 4.0, 6.0])

    def test_update_changes_x(self):
        n = NeuralSLAM(state_dim=3, obs_dim=4, seed=3)
        before = n.x.copy()
        n.update(np.array([1.0, 2.0, 3.0, 4.0]), np.eye(4) * 0.5)
        assert not np.allclose(before, n.x)

    def test_update_decreases_uncertainty(self):
        n = NeuralSLAM(state_dim=3, obs_dim=4, seed=4)
        before = float(np.trace(n.P))
        n.update(np.zeros(4), np.eye(4) * 0.1)
        after = float(np.trace(n.P))
        assert after < before

    def test_train_step_changes_W1(self):
        n = NeuralSLAM(state_dim=3, obs_dim=4, lr=0.1, seed=5)
        before = n.W1.copy()
        n.train_step(np.array([1.0, 0.5, -0.2]),
                     np.array([0.0, 0.0, 0.0, 0.0]))
        assert not np.allclose(before, n.W1)

    def test_train_step_loss_decreases(self):
        n = NeuralSLAM(state_dim=3, obs_dim=4, lr=0.05, seed=6)
        x = np.array([0.5, 0.3, -0.1])
        y = np.array([1.0, -0.5, 0.2, 0.8])
        loss0 = n.train_step(x, y)
        for _ in range(20):
            n.train_step(x, y)
        loss1 = n.train_step(x, y)
        assert loss1 < loss0


# ============================================================================
# SceneRecognizer
# ============================================================================

def _img(seed=0):
    rng = np.random.RandomState(seed)
    return rng.randint(0, 256, (32, 32)).astype(float)


class TestSceneRecognizer:
    def test_extract_features_shape(self):
        s = SceneRecognizer(n_bins=8)
        f = s.extract_features(_img(0))
        assert f.shape == (8,)

    def test_features_l2_normalised(self):
        s = SceneRecognizer(n_bins=8)
        f = s.extract_features(_img(1))
        assert float(np.linalg.norm(f)) == pytest.approx(1.0, abs=1e-6)

    def test_add_scene_grows_database(self):
        s = SceneRecognizer()
        before = s.database_size()
        s.add_scene(_img(2), "kitchen")
        assert s.database_size() == before + 1

    def test_recognize_returns_list(self):
        s = SceneRecognizer()
        s.add_scene(_img(3), "lab")
        out = s.recognize(_img(3))
        assert isinstance(out, list)

    def test_recognize_top1_correct(self):
        s = SceneRecognizer()
        img = _img(7)
        s.add_scene(img, "office")
        s.add_scene(_img(99), "garage")
        result = s.recognize(img, top_k=1)
        assert result[0][0] == "office"

    def test_recognize_unknown_for_empty(self):
        s = SceneRecognizer()
        out = s.recognize(_img(0))
        assert out[0][0] == "unknown"

    def test_database_size_correct(self):
        s = SceneRecognizer()
        for k in range(4):
            s.add_scene(_img(k), f"room{k}")
        assert s.database_size() == 4


# ============================================================================
# ConstrainedKalmanFilter
# ============================================================================

class TestConstrainedKalmanFilter:
    def test_predict_advances_state(self):
        kf = ConstrainedKalmanFilter(state_dim=3)
        kf.x = np.array([1.0, 2.0, 3.0])
        kf.F = np.eye(3) * 2.0
        kf.predict()
        assert np.allclose(kf.x, [2.0, 4.0, 6.0])

    def test_update_changes_x(self):
        kf = ConstrainedKalmanFilter(state_dim=3)
        kf.H = np.eye(2, 3)
        kf.R = np.eye(2)
        before = kf.x.copy()
        kf.update(np.array([1.0, 2.0]))
        assert not np.allclose(before, kf.x)

    def test_project_enforces_constraint(self):
        kf = ConstrainedKalmanFilter(state_dim=3)
        kf.x = np.array([1.0, 2.0, 3.0])
        D = np.array([[1.0, 1.0, 0.0]])
        d = np.array([5.0])
        kf.set_constraint(D, d)
        kf.project()
        assert kf.constraint_residual() < 1e-8

    def test_project_keeps_P_spd(self):
        kf = ConstrainedKalmanFilter(state_dim=3)
        D = np.array([[1.0, -1.0, 0.0]])
        d = np.array([0.0])
        kf.set_constraint(D, d)
        kf.project()
        eigs = np.linalg.eigvalsh(0.5 * (kf.P + kf.P.T))
        assert np.all(eigs >= -1e-9)

    def test_constraint_residual_zero_no_constraint(self):
        kf = ConstrainedKalmanFilter(state_dim=3)
        assert kf.constraint_residual() == 0.0

    def test_set_constraint_stores(self):
        kf = ConstrainedKalmanFilter(state_dim=3)
        D = np.array([[1.0, 0.0, 0.0]])
        d = np.array([2.0])
        kf.set_constraint(D, d)
        assert np.allclose(kf._D, D)
        assert np.allclose(kf._d, d)

    def test_project_no_op_without_constraint(self):
        kf = ConstrainedKalmanFilter(state_dim=3)
        kf.x = np.array([1.0, 2.0, 3.0])
        before = kf.x.copy()
        kf.project()
        assert np.allclose(before, kf.x)


# ============================================================================
# USBLPositioner
# ============================================================================

class TestUSBLPositioner:
    def test_twtt_to_range_formula(self):
        u = USBLPositioner(sound_speed=1500.0)
        assert u.twtt_to_range(2.0) == pytest.approx(1500.0)

    def test_position_3d_shape(self):
        u = USBLPositioner()
        out = u.position_3d(100.0, 0.0, 0.0)
        assert out.shape == (3,)

    def test_position_3d_straight_down(self):
        u = USBLPositioner()
        out = u.position_3d(50.0, 0.0, math.pi / 2)
        assert out[0] == pytest.approx(0.0, abs=1e-9)
        assert out[1] == pytest.approx(0.0, abs=1e-9)
        assert out[2] == pytest.approx(50.0)

    def test_accuracy_increases_with_range(self):
        u = USBLPositioner()
        a1 = u.accuracy(10.0)
        a2 = u.accuracy(100.0)
        assert a2 > a1

    def test_max_unambiguous_angle_30(self):
        u = USBLPositioner()
        assert u.max_unambiguous_angle() == pytest.approx(30.0, abs=1e-6)

    def test_phase_to_bearing_returns_float(self):
        u = USBLPositioner()
        b = u.phase_to_bearing(0.5)
        assert isinstance(b, float)

    def test_phase_to_bearing_zero(self):
        u = USBLPositioner()
        assert u.phase_to_bearing(0.0) == pytest.approx(0.0)
