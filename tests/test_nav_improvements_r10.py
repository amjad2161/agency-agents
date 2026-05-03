"""GODSKILL Navigation R10 — milestone improvement-round tests.

Covers:
- ReceiverAutonomousIntegrityMonitoring
- NavStateInterpolator
- CrouchDetector
- UnderwaterDVLNavigator
- OnlineBayesianPosFilter
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.satellite import (  # noqa: E402
    ReceiverAutonomousIntegrityMonitoring,
)
from agency.navigation.fusion import NavStateInterpolator  # noqa: E402
from agency.navigation.indoor_inertial import CrouchDetector  # noqa: E402
from agency.navigation.underwater import UnderwaterDVLNavigator  # noqa: E402
from agency.navigation.ai_enhance import OnlineBayesianPosFilter  # noqa: E402


# ============================================================================
# ReceiverAutonomousIntegrityMonitoring
# ============================================================================

def _good_geometry():
    # 6-SV well-distributed geometry (line-of-sight unit vectors + 1 for clock)
    H = np.array([
        [0.5, 0.5, 0.7, 1.0],
        [-0.5, 0.5, 0.7, 1.0],
        [0.0, -0.7, 0.7, 1.0],
        [0.7, 0.0, 0.7, 1.0],
        [-0.7, 0.0, 0.7, 1.0],
        [0.0, 0.0, 1.0, 1.0],
    ])
    sigma = np.array([3.0, 3.5, 4.0, 3.2, 3.8, 3.0])
    return H, sigma


class TestRAIM:
    def test_init(self):
        r = ReceiverAutonomousIntegrityMonitoring()
        assert r.DEFAULT_HAL == pytest.approx(556.0)

    def test_hpl_positive(self):
        r = ReceiverAutonomousIntegrityMonitoring()
        H, sigma = _good_geometry()
        hpl, _ = r.compute_protection_level(H, sigma)
        assert hpl > 0.0

    def test_vpl_positive(self):
        r = ReceiverAutonomousIntegrityMonitoring()
        H, sigma = _good_geometry()
        _, vpl = r.compute_protection_level(H, sigma)
        assert vpl > 0.0

    def test_alert_true_when_hpl_above_hal(self):
        r = ReceiverAutonomousIntegrityMonitoring()
        assert r.alert(HPL=1000.0, HAL=556.0, VPL=10.0, VAL=50.0) is True

    def test_alert_false_when_small(self):
        r = ReceiverAutonomousIntegrityMonitoring()
        assert r.alert(HPL=10.0, HAL=556.0, VPL=5.0, VAL=50.0) is False

    def test_solution_separation_shape(self):
        r = ReceiverAutonomousIntegrityMonitoring()
        full = np.array([100.0, 200.0, 50.0])
        subs = [np.array([100.5, 199.5, 50.1]),
                np.array([99.0, 201.0, 49.5]),
                np.array([100.2, 200.3, 50.4])]
        sep = r.solution_separation(subs, full)
        assert sep.shape == full.shape

    def test_protection_level_scales_with_sigma(self):
        r = ReceiverAutonomousIntegrityMonitoring()
        H, sigma = _good_geometry()
        hpl_low, _ = r.compute_protection_level(H, sigma)
        hpl_high, _ = r.compute_protection_level(H, sigma * 5.0)
        assert hpl_high > hpl_low


# ============================================================================
# NavStateInterpolator
# ============================================================================

class TestNavStateInterpolator:
    def test_init(self):
        i = NavStateInterpolator()
        assert i.states == []

    def test_add_state(self):
        i = NavStateInterpolator()
        i.add_state(0.0, [0.0, 0.0, 0.0], [1.0, 0.0, 0.0])
        assert len(i.states) == 1

    def test_interpolate_between_two_states_midpoint(self):
        i = NavStateInterpolator()
        i.add_state(0.0, [0.0, 0.0, 0.0], [1.0, 0.0, 0.0])
        i.add_state(2.0, [2.0, 0.0, 0.0], [1.0, 0.0, 0.0])
        pos, vel = i.interpolate(1.0)
        # Constant-velocity motion → mid-point is (1, 0, 0)
        assert pos[0] == pytest.approx(1.0, abs=0.05)

    def test_interpolate_at_exact_time(self):
        i = NavStateInterpolator()
        i.add_state(0.0, [5.0, 5.0, 5.0], [0.0, 0.0, 0.0])
        i.add_state(1.0, [10.0, 10.0, 10.0], [0.0, 0.0, 0.0])
        pos, _ = i.interpolate(0.0)
        assert np.allclose(pos, [5.0, 5.0, 5.0])

    def test_velocity_from_positions_shape(self):
        i = NavStateInterpolator()
        states = [
            {"t": 0.0, "pos": np.array([0.0, 0.0, 0.0])},
            {"t": 1.0, "pos": np.array([1.0, 0.0, 0.0])},
            {"t": 2.0, "pos": np.array([2.0, 0.0, 0.0])},
        ]
        v = i.velocity_from_positions(states)
        assert v.shape == (3, 3)

    def test_clear_before_removes_old(self):
        i = NavStateInterpolator()
        for t in (0.0, 1.0, 2.0, 3.0, 4.0):
            i.add_state(t, [t, 0.0, 0.0], [1.0, 0.0, 0.0])
        i.clear_before(2.0)
        assert len(i.states) == 3
        assert i.states[0]["t"] == pytest.approx(2.0)

    def test_multistate_interpolation_continuous(self):
        i = NavStateInterpolator()
        for t in range(5):
            i.add_state(float(t), [float(t), 0.0, 0.0], [1.0, 0.0, 0.0])
        pos1, _ = i.interpolate(2.5)
        assert pos1[0] == pytest.approx(2.5, abs=0.1)


# ============================================================================
# CrouchDetector
# ============================================================================

class TestCrouchDetector:
    def test_init(self):
        d = CrouchDetector()
        assert d is not None

    def test_extract_features_returns_three(self):
        d = CrouchDetector()
        accel = np.tile(np.array([0.0, 0.0, 9.81]), (50, 1))
        f = d.extract_features(accel)
        assert len(f) == 3

    def test_classify_stationary(self):
        d = CrouchDetector()
        accel = np.tile(np.array([0.0, 0.0, 9.81]), (50, 1))
        assert d.classify(accel) == "stationary"

    def test_classify_walking(self):
        d = CrouchDetector()
        rng = np.random.RandomState(0)
        # Vertical-dominant moderate motion
        a = np.zeros((100, 3))
        a[:, 2] = 9.81 + 1.0 * np.sin(np.linspace(0, 4 * math.pi, 100))
        a += 0.05 * rng.randn(100, 3)
        assert d.classify(a) == "walking"

    def test_classify_running(self):
        d = CrouchDetector()
        rng = np.random.RandomState(1)
        a = np.zeros((100, 3))
        a[:, 2] = 9.81 + 5.0 * np.sin(np.linspace(0, 8 * math.pi, 100))
        a += 0.5 * rng.randn(100, 3)
        assert d.classify(a) == "running"

    def test_classify_crouching(self):
        d = CrouchDetector()
        rng = np.random.RandomState(2)
        # Lateral motion dominant (gravity-subtracted body frame), low variance
        a = np.zeros((100, 3))
        a[:, 0] = 1.0 * np.sin(np.linspace(0, 4 * math.pi, 100))
        a[:, 1] = 1.0 * np.cos(np.linspace(0, 4 * math.pi, 100))
        a[:, 2] = 0.0
        a += 0.05 * rng.randn(100, 3)
        assert d.classify(a) == "crouching"

    def test_vert_ratio_high_for_vertical_dominant(self):
        d = CrouchDetector()
        a = np.zeros((50, 3))
        a[:, 2] = 9.81
        _, _, vert = d.extract_features(a)
        assert vert > 0.9


# ============================================================================
# UnderwaterDVLNavigator
# ============================================================================

class TestUnderwaterDVLNavigator:
    def test_init(self):
        d = UnderwaterDVLNavigator(beam_angle_deg=30.0)
        assert d.beam_angle_deg == pytest.approx(30.0)

    def test_compute_velocity_shape(self):
        d = UnderwaterDVLNavigator()
        v = d.compute_velocity_from_beams([0.5, 0.0, -0.5, 0.0])
        assert v.shape == (3,)

    def test_bottom_lock_detected(self):
        d = UnderwaterDVLNavigator()
        assert d.detect_bottom_lock([0.5, 0.4, 0.3, 0.2], threshold=20.0) is True

    def test_bottom_lock_missed_for_high_velocity(self):
        d = UnderwaterDVLNavigator()
        assert d.detect_bottom_lock([25.0, 0.0, 0.0, 0.0],
                                    threshold=20.0) is False

    def test_integrate_position_returns_three_floats(self):
        d = UnderwaterDVLNavigator()
        out = d.integrate_position(1.0, 0.0, 0.0, heading_rad=0.0, dt=1.0)
        assert len(out) == 3
        for v in out:
            assert isinstance(v, float)

    def test_heading_rotation_applied(self):
        d = UnderwaterDVLNavigator()
        # Body vx=1, heading=π/2 → world dy=+1, dx≈0
        dx, dy, _ = d.integrate_position(1.0, 0.0, 0.0,
                                         heading_rad=math.pi / 2, dt=1.0)
        assert dx == pytest.approx(0.0, abs=1e-9)
        assert dy == pytest.approx(1.0)

    def test_zero_beams_zero_velocity(self):
        d = UnderwaterDVLNavigator()
        v = d.compute_velocity_from_beams([0.0, 0.0, 0.0, 0.0])
        assert np.allclose(v, 0.0)


# ============================================================================
# OnlineBayesianPosFilter
# ============================================================================

class TestOnlineBayesianPosFilter:
    def test_init_five_components(self):
        f = OnlineBayesianPosFilter(n_components=5, dim=2, seed=0)
        assert f.means.shape == (5, 2)
        assert f.weights.shape == (5,)
        assert f.weights.sum() == pytest.approx(1.0)

    def test_predict_moves_mean(self):
        f = OnlineBayesianPosFilter(n_components=5, dim=2, seed=0)
        before = f.means.copy()
        f.predict(motion_delta=np.array([1.0, 0.0]), motion_sigma=0.1)
        assert np.allclose(f.means - before, np.array([1.0, 0.0]))

    def test_update_pulls_toward_measurement(self):
        f = OnlineBayesianPosFilter(n_components=5, dim=2,
                                    init_spread=1.0, seed=0)
        target = np.array([10.0, 10.0])
        for _ in range(20):
            f.update(target, meas_sigma=0.5)
        mean, _ = f.get_position_estimate()
        assert float(np.linalg.norm(mean - target)) < 5.0

    def test_get_position_estimate_returns_pos_cov(self):
        f = OnlineBayesianPosFilter(n_components=5, dim=2, seed=0)
        mean, cov = f.get_position_estimate()
        assert mean.shape == (2,)
        assert cov.shape == (2, 2)

    def test_cov_positive_definite(self):
        f = OnlineBayesianPosFilter(n_components=5, dim=2, seed=0)
        f.update(np.array([0.0, 0.0]), meas_sigma=1.0)
        _, cov = f.get_position_estimate()
        sym = 0.5 * (cov + cov.T)
        eigs = np.linalg.eigvalsh(sym)
        assert np.all(eigs > -1e-6)

    def test_resample_runs(self):
        f = OnlineBayesianPosFilter(n_components=5, dim=2, seed=0)
        # Force a low-weight component
        f.weights = np.array([0.6, 0.3, 0.05, 0.04, 0.01])
        f.weights = f.weights / f.weights.sum()
        f.resample_components()
        assert f.weights.sum() == pytest.approx(1.0)

    def test_weights_sum_to_one(self):
        f = OnlineBayesianPosFilter(n_components=5, dim=2, seed=0)
        f.update(np.array([1.0, 1.0]), meas_sigma=0.5)
        assert float(f.weights.sum()) == pytest.approx(1.0)
