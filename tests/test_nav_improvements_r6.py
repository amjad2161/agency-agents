"""GODSKILL Nav R6 — PPPCorrector, IMMFilter, WheelOdometryIntegrator,
BayesianNeuralOdometry. 28 tests across 4 new classes.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from agency.navigation.satellite import PPPCorrector
from agency.navigation.fusion import IMMFilter
from agency.navigation.indoor_inertial import WheelOdometryIntegrator
from agency.navigation.ai_enhance import BayesianNeuralOdometry


# =====================================================================
# PPPCorrector — 7 tests
# =====================================================================

def test_ppp_init_default_state():
    ppp = PPPCorrector()
    assert ppp.get_satellite_clock_bias("G01") == 0.0


def test_ppp_set_and_get_satellite_clock_bias():
    ppp = PPPCorrector()
    ppp.set_satellite_clock_bias("G05", 1.2e-7)
    assert ppp.get_satellite_clock_bias("G05") == pytest.approx(1.2e-7)


def test_ppp_saastamoinen_zero_below_horizon():
    ppp = PPPCorrector()
    assert ppp.saastamoinen_delay(elevation_deg=-1.0, height_m=0.0) == 0.0
    assert ppp.saastamoinen_delay(elevation_deg=0.0, height_m=0.0) == 0.0


def test_ppp_saastamoinen_zenith_realistic_range():
    """At zenith near sea level the dry delay is ~2.3 m."""
    ppp = PPPCorrector()
    d = ppp.saastamoinen_delay(elevation_deg=90.0, height_m=0.0)
    assert 2.0 < d < 2.7


def test_ppp_saastamoinen_increases_at_lower_elevation():
    ppp = PPPCorrector()
    high = ppp.saastamoinen_delay(elevation_deg=80.0, height_m=0.0)
    low = ppp.saastamoinen_delay(elevation_deg=10.0, height_m=0.0)
    assert low > high * 2.0


def test_ppp_phase_windup_returns_finite_cycles():
    ppp = PPPCorrector()
    sat = np.array([20000e3, 1000e3, 0.0])
    rcv = np.array([0.0, 0.0, 0.0])
    cycles = ppp.phase_windup(sat, rcv, prev_windup=0.0)
    assert math.isfinite(cycles)


def test_ppp_apply_corrections_changes_pseudorange():
    ppp = PPPCorrector()
    sat = np.array([20000e3, 0.0, 0.0])
    rcv = np.array([0.0, 0.0, 0.0])
    raw = 20_000_000.0
    corrected = ppp.apply_ppp_corrections(
        pseudorange=raw, satellite_pos=sat, receiver_pos=rcv,
        clock_bias_seconds=1e-7, elevation_deg=45.0, height_m=0.0,
    )
    assert corrected != raw
    assert math.isfinite(corrected)
    # Within a few hundred metres of original (clock + tropo + windup)
    assert abs(corrected - raw) < 200.0


# =====================================================================
# IMMFilter — 7 tests
# =====================================================================

def test_imm_init_default_probabilities_sum_to_one():
    imm = IMMFilter()
    p = imm.model_probabilities
    assert p.shape == (2,)
    assert p.sum() == pytest.approx(1.0)


def test_imm_init_custom_probabilities_normalised():
    imm = IMMFilter(init_probs=[0.8, 0.2])
    p = imm.model_probabilities
    assert p[0] == pytest.approx(0.8)
    assert p[1] == pytest.approx(0.2)


def test_imm_predict_returns_4d_state():
    imm = IMMFilter(dt=0.5)
    state = imm.predict()
    assert state.shape == (4,)
    assert np.all(np.isfinite(state))


def test_imm_predict_propagates_velocity_under_cv():
    imm = IMMFilter(dt=1.0, init_probs=[1.0, 0.0])
    imm.x_cv = np.array([0.0, 0.0, 1.0, 0.0])
    state = imm.predict()
    assert state[0] == pytest.approx(1.0, rel=1e-6)


def test_imm_update_with_measurement_returns_dict():
    imm = IMMFilter()
    imm.predict()
    out = imm.update(np.array([1.0, 0.5]))
    assert "state" in out and "covariance" in out and "model_probabilities" in out
    assert out["state"].shape == (4,)


def test_imm_update_probabilities_renormalised():
    imm = IMMFilter()
    for _ in range(3):
        imm.predict()
        imm.update(np.array([0.3, 0.1]))
    p = imm.model_probabilities
    assert p.sum() == pytest.approx(1.0)
    assert (p >= 0).all()


def test_imm_cv_dominates_for_straight_line_track():
    """A straight-line track should keep the CV model dominant."""
    imm = IMMFilter(dt=1.0, q_cv=0.01, q_ct=1.0, r_pos=0.05,
                    turn_rate_rad_s=0.5)
    for k in range(20):
        imm.predict()
        z = np.array([float(k), 0.0])
        imm.update(z)
    p = imm.model_probabilities
    assert p[0] > p[1]


def test_imm_update_rejects_bad_measurement_shape():
    imm = IMMFilter()
    imm.predict()
    with pytest.raises(ValueError):
        imm.update(np.array([1.0, 2.0, 3.0]))


# =====================================================================
# WheelOdometryIntegrator — 7 tests
# =====================================================================

def test_wheel_odo_init_defaults():
    w = WheelOdometryIntegrator()
    assert w.x_total == 0.0 and w.y_total == 0.0 and w.theta_total == 0.0
    assert w.last_slip_detected is False


def test_wheel_odo_forward_motion_advances_x():
    w = WheelOdometryIntegrator(default_wheelbase_m=0.5)
    dx, dy, dth = w.integrate(v_left=1.0, v_right=1.0, dt=1.0)
    assert dx == pytest.approx(1.0)
    assert dy == pytest.approx(0.0)
    assert dth == pytest.approx(0.0)


def test_wheel_odo_pure_rotation_in_place():
    w = WheelOdometryIntegrator(default_wheelbase_m=0.5)
    dx, dy, dth = w.integrate(v_left=-0.25, v_right=0.25, dt=1.0)
    # |dtheta| = (vR - vL)/b * dt = 0.5/0.5 = 1 rad
    assert abs(dth) == pytest.approx(1.0, rel=1e-6)
    # Net displacement small (curve radius ~ 0)
    assert abs(dx) < 1e-6
    assert abs(dy) < 1e-6


def test_wheel_odo_arc_motion_curves():
    w = WheelOdometryIntegrator(default_wheelbase_m=0.5)
    dx, dy, dth = w.integrate(v_left=0.5, v_right=1.0, dt=1.0)
    assert dth > 0
    assert dx > 0
    # Arc bows to the left (positive y in body frame)
    assert dy > 0


def test_wheel_odo_slip_detected_when_one_wheel_freezes():
    w = WheelOdometryIntegrator(slip_threshold=1.5)
    ratio = w.estimate_slip(v_left=2.0, v_right=0.5)
    assert ratio > 1.5
    assert w.last_slip_detected is True


def test_wheel_odo_no_slip_for_balanced_motion():
    w = WheelOdometryIntegrator(slip_threshold=1.5)
    ratio = w.estimate_slip(v_left=1.0, v_right=1.05)
    assert ratio < 1.5
    assert w.last_slip_detected is False


def test_wheel_odo_zero_dt_returns_zero_delta():
    w = WheelOdometryIntegrator()
    dx, dy, dth = w.integrate(1.0, 1.0, dt=0.0)
    assert (dx, dy, dth) == (0.0, 0.0, 0.0)


def test_wheel_odo_invalid_wheelbase_raises():
    w = WheelOdometryIntegrator()
    with pytest.raises(ValueError):
        w.integrate(1.0, 1.0, dt=1.0, wheelbase=0.0)


# =====================================================================
# BayesianNeuralOdometry — 7 tests
# =====================================================================

def test_bno_init_creates_weights():
    bno = BayesianNeuralOdometry(seq_len=10, hidden=8, dropout=0.1)
    assert bno.W1.shape == (60, 8)
    assert bno.W2.shape == (8, 3)


def test_bno_predict_shape_is_3d():
    bno = BayesianNeuralOdometry(seq_len=10, hidden=8)
    seq = np.zeros((10, 6))
    out = bno.predict(seq)
    assert out.shape == (3,)


def test_bno_predict_with_uncertainty_returns_mean_std_3d():
    bno = BayesianNeuralOdometry(seq_len=10, hidden=8, dropout=0.3)
    seq = np.random.default_rng(0).normal(size=(10, 6))
    mean, std = bno.predict_with_uncertainty(seq, n_samples=10)
    assert mean.shape == (3,)
    assert std.shape == (3,)


def test_bno_uncertainty_positive_with_dropout():
    bno = BayesianNeuralOdometry(seq_len=10, hidden=16, dropout=0.4, seed=11)
    seq = np.random.default_rng(1).normal(size=(10, 6))
    _, std = bno.predict_with_uncertainty(seq, n_samples=20)
    assert (std > 0).all()


def test_bno_train_step_returns_finite_loss():
    bno = BayesianNeuralOdometry(seq_len=5, hidden=8, dropout=0.0)
    seq = np.random.default_rng(2).normal(size=(5, 6))
    target = np.array([0.5, -0.2, 0.1])
    loss = bno.train_step(seq, target, lr=1e-2)
    assert math.isfinite(loss)
    assert loss >= 0.0


def test_bno_train_step_reduces_loss_over_iterations():
    bno = BayesianNeuralOdometry(seq_len=5, hidden=16, dropout=0.0, seed=3)
    seq = np.random.default_rng(3).normal(size=(5, 6))
    target = np.array([0.4, -0.3, 0.2])
    initial = bno.train_step(seq, target, lr=5e-3)
    for _ in range(120):
        bno.train_step(seq, target, lr=5e-3)
    final = bno.train_step(seq, target, lr=5e-3)
    assert final < initial


def test_bno_short_sequence_pads_to_required_length():
    bno = BayesianNeuralOdometry(seq_len=10, hidden=8, dropout=0.0)
    short = np.ones((3, 6))
    out = bno.predict(short)
    assert out.shape == (3,)
    assert np.all(np.isfinite(out))


def test_bno_invalid_input_shape_raises():
    bno = BayesianNeuralOdometry(seq_len=5, hidden=8)
    with pytest.raises(ValueError):
        bno.predict(np.zeros((5, 4)))
