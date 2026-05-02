"""GODSKILL Nav v11 — Round 4 improvement tests.

Covers:
  * IMUPreintegration:  integrate, reset, bias-corrected delta, covariance,
                        factor between two keyframes.
  * FactorGraph:        unary + binary factors, optimization convergence,
                        marginal extraction, build_nav_graph helper.
  * NeuralRadianceMap:  Fourier-feature encoding, forward, train_step (loss
                        decreases), batch query.
  * WMMModel:           declination, inclination, total intensity at known
                        sites, secular variation, grid_survey shape.
"""

from __future__ import annotations

import math
import os
import sys

_THIS = os.path.abspath(os.path.dirname(__file__))
_RUNTIME = os.path.abspath(os.path.join(_THIS, "..", "runtime"))
if _RUNTIME not in sys.path:
    sys.path.insert(0, _RUNTIME)

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from agency.navigation.indoor_inertial import IMUPreintegration  # noqa: E402
from agency.navigation.fusion import FactorGraph  # noqa: E402
from agency.navigation.ai_enhance import NeuralRadianceMap  # noqa: E402
from agency.navigation.offline_maps import WMMModel  # noqa: E402


# ---------------------------------------------------------------------------
# IMUPreintegration
# ---------------------------------------------------------------------------


def test_imu_preint_initial_state_identity():
    pre = IMUPreintegration()
    assert np.allclose(pre.dR, np.eye(3))
    assert np.allclose(pre.dv, 0.0)
    assert np.allclose(pre.dp, 0.0)
    assert pre.dt_total == 0.0


def test_imu_preint_zero_dt_is_noop():
    pre = IMUPreintegration()
    pre.integrate(np.array([1.0, 0.0, 0.0]), np.zeros(3), 0.0)
    assert pre.dt_total == 0.0
    assert np.allclose(pre.dv, 0.0)


def test_imu_preint_constant_accel_grows_velocity():
    pre = IMUPreintegration()
    for _ in range(100):
        pre.integrate(np.array([1.0, 0.0, 0.0]), np.zeros(3), 0.01)
    # 1 m/s^2 for 1 s → dv ≈ 1 m/s, dp ≈ 0.5 m
    assert pre.dv[0] == pytest.approx(1.0, rel=1e-2)
    assert pre.dp[0] == pytest.approx(0.5, rel=1e-2)
    assert pre.dt_total == pytest.approx(1.0, rel=1e-6)


def test_imu_preint_pure_rotation_keeps_v_zero():
    pre = IMUPreintegration()
    for _ in range(50):
        pre.integrate(np.zeros(3), np.array([0.0, 0.0, 0.5]), 0.01)
    assert np.allclose(pre.dv, 0.0)
    # dR rotates 0.25 rad about z
    yaw = math.atan2(pre.dR[1, 0], pre.dR[0, 0])
    assert yaw == pytest.approx(0.25, rel=1e-2)


def test_imu_preint_reset_clears_state():
    pre = IMUPreintegration()
    pre.integrate(np.ones(3), np.ones(3) * 0.1, 0.05)
    pre.reset()
    assert np.allclose(pre.dR, np.eye(3))
    assert pre.dt_total == 0.0
    assert np.allclose(pre.P, 0.0)


def test_imu_preint_bias_corrected_delta_returns_dict():
    pre = IMUPreintegration()
    for _ in range(10):
        pre.integrate(np.array([0.5, 0.0, 0.0]), np.zeros(3), 0.05)
    out = pre.bias_corrected_delta(
        bg_correction=np.zeros(3), ba_correction=np.zeros(3),
    )
    for k in ("dR", "dv", "dp"):
        assert k in out
    # Zero correction should match raw values.
    assert np.allclose(out["dv"], pre.dv)
    assert np.allclose(out["dp"], pre.dp)


def test_imu_preint_bias_correction_changes_velocity():
    pre = IMUPreintegration()
    for _ in range(10):
        pre.integrate(np.array([0.5, 0.0, 0.0]), np.zeros(3), 0.05)
    raw = pre.dv.copy()
    out = pre.bias_corrected_delta(
        bg_correction=np.zeros(3), ba_correction=np.array([0.1, 0.0, 0.0]),
    )
    # Adding a positive accel bias correction subtracts from accumulated dv.
    assert not np.allclose(out["dv"], raw)


def test_imu_preint_covariance_grows_monotonically_in_diag():
    pre = IMUPreintegration()
    pre.integrate(np.zeros(3), np.zeros(3), 0.05)
    P1 = pre.covariance().diagonal().sum()
    for _ in range(10):
        pre.integrate(np.zeros(3), np.zeros(3), 0.05)
    P2 = pre.covariance().diagonal().sum()
    assert P2 >= P1


def test_imu_preint_create_factor_residual_shape():
    pre = IMUPreintegration()
    for _ in range(20):
        pre.integrate(np.array([0.0, 0.0, 9.80665]), np.zeros(3), 0.05)
    pose_i = {"R": np.eye(3), "v": np.zeros(3), "p": np.zeros(3)}
    pose_j = {"R": np.eye(3), "v": np.zeros(3), "p": np.zeros(3)}
    fac = pre.create_factor(pose_i, pose_j)
    assert fac["residual"].shape == (9,)
    assert fac["dt"] == pytest.approx(1.0, rel=1e-2)


# ---------------------------------------------------------------------------
# FactorGraph
# ---------------------------------------------------------------------------


def test_factor_graph_add_variable_unique():
    g = FactorGraph()
    g.add_variable("a", 3)
    with pytest.raises(ValueError):
        g.add_variable("a", 3)


def test_factor_graph_add_factor_unknown_var():
    g = FactorGraph()
    with pytest.raises(ValueError):
        g.add_unary_factor("x", np.zeros(3), np.eye(3), lambda x: x)


def test_factor_graph_unary_prior_pulls_state():
    g = FactorGraph()
    g.add_variable("p", 3)
    g.add_unary_factor(
        "p", np.array([1.0, 2.0, 3.0]), np.eye(3) * 100.0, lambda x: x,
    )
    out = g.optimize(max_iter=20)
    val = g.get_value("p")
    assert val == pytest.approx(np.array([1.0, 2.0, 3.0]), abs=1e-3)
    assert out["converged"] is True or out["final_cost"] < 1e-3


def test_factor_graph_binary_difference_constraint():
    g = FactorGraph()
    g.add_variable("p1", 3)
    g.add_variable("p2", 3)
    g.add_unary_factor("p1", np.zeros(3), np.eye(3) * 100.0, lambda x: x)
    g.add_binary_factor(
        "p1", "p2", np.array([1.0, 0.0, 0.0]), np.eye(3) * 100.0,
        lambda x1, x2: x2 - x1,
    )
    g.optimize(max_iter=30)
    assert g.get_value("p2") == pytest.approx(np.array([1.0, 0.0, 0.0]),
                                              abs=1e-2)


def test_factor_graph_marginal_returns_block():
    g = FactorGraph()
    g.add_variable("p", 3)
    g.add_unary_factor(
        "p", np.array([5.0, 0.0, 0.0]), np.eye(3) * 50.0, lambda x: x,
    )
    g.optimize()
    marg = g.marginal("p")
    assert marg["mean"].shape == (3,)
    assert marg["cov"].shape == (3, 3)
    # Information matrix 50*I → covariance ≈ 1/50 I.
    assert marg["cov"][0, 0] == pytest.approx(1.0 / 50.0, rel=0.5)


def test_factor_graph_build_nav_graph():
    g = FactorGraph.build_nav_graph(
        gps_obs=[np.array([0.0, 0.0, 0.0]),
                 None,
                 np.array([2.0, 0.0, 0.0])],
        imu_preint=[np.array([1.0, 0.0, 0.0]),
                    np.array([1.0, 0.0, 0.0])],
        baro_obs=[None, None, None],
    )
    out = g.optimize(max_iter=20)
    p1 = g.get_value(("p", 1))
    assert p1[0] == pytest.approx(1.0, abs=1e-2)
    assert out["final_cost"] < 1.0


# ---------------------------------------------------------------------------
# NeuralRadianceMap
# ---------------------------------------------------------------------------


def test_nrm_encode_position_dim():
    enc = NeuralRadianceMap.encode_position(np.array([0.1, 0.2, 0.3]))
    assert enc.shape == (NeuralRadianceMap.K_FREQS * 2 * 3,)


def test_nrm_encode_position_at_zero_is_constant():
    enc = NeuralRadianceMap.encode_position(np.zeros(3))
    # sin(0)=0, cos(0)=1 — half zeros, half ones (any order).
    n = enc.size
    n_zeros = int(np.isclose(enc, 0.0).sum())
    n_ones = int(np.isclose(enc, 1.0).sum())
    assert n_zeros == n // 2
    assert n_ones == n // 2


def test_nrm_forward_returns_scalar():
    nrm = NeuralRadianceMap(seed=0)
    y = nrm.forward(np.array([0.5, 0.5, 0.5]))
    assert isinstance(y, float)


def test_nrm_train_step_reduces_loss():
    nrm = NeuralRadianceMap(seed=42)
    rng = np.random.default_rng(0)
    pos = rng.uniform(-1, 1, size=(64, 3))
    target = pos[:, 0] * 2.0  # learn a simple linear function of x
    initial_mse = nrm.train_step(pos, target, lr=0.001)
    for _ in range(60):
        nrm.train_step(pos, target, lr=0.001)
    final_mse = nrm.train_step(pos, target, lr=0.001)
    assert final_mse < initial_mse


def test_nrm_train_step_input_validation():
    nrm = NeuralRadianceMap(seed=0)
    with pytest.raises(ValueError):
        nrm.train_step(np.zeros((4, 3)), np.zeros(2), lr=0.01)


def test_nrm_query_map_batch_shape():
    nrm = NeuralRadianceMap(seed=0)
    grid = np.array([[0.0, 0.0, 0.0],
                     [1.0, 0.0, 0.0],
                     [0.0, 1.0, 0.0]])
    out = nrm.query_map(grid)
    assert out.shape == (3,)


# ---------------------------------------------------------------------------
# WMMModel (enhanced)
# ---------------------------------------------------------------------------


def test_wmm_declination_in_range():
    wmm = WMMModel()
    d = wmm.declination(35.0, 139.0, alt_km=0.0, year=2025.0)
    # Tokyo declination is roughly -7° — simplified dipole gives small +deg.
    assert -45.0 < d < 45.0


def test_wmm_inclination_extreme_at_equator_and_pole():
    wmm = WMMModel()
    i_eq = wmm.inclination(0.0, 0.0, year=2025.0)
    i_pole = wmm.inclination(89.0, 0.0, year=2025.0)
    # Near equator dip ≈ 0; near pole dip approaches ±90.
    assert abs(i_eq) < 30.0
    assert abs(i_pole) > 60.0


def test_wmm_total_intensity_positive_and_realistic():
    wmm = WMMModel()
    f = wmm.total_intensity(0.0, 0.0, year=2025.0)
    # Real Earth surface field ~25_000–65_000 nT.
    assert 20_000.0 < f < 70_000.0


def test_wmm_secular_variation_changes_value():
    wmm = WMMModel()
    d_2020 = wmm.declination(45.0, 0.0, year=2020.0)
    d_2025 = wmm.declination(45.0, 0.0, year=2025.0)
    assert d_2020 != d_2025


def test_wmm_grid_survey_shape():
    wmm = WMMModel()
    out = wmm.grid_survey((0.0, 5.0), (0.0, 5.0), step_deg=2.5, year=2025.0)
    assert out.shape[2] == 3
    assert out.shape[0] == 3 and out.shape[1] == 3


def test_wmm_legacy_3arg_declination_still_works():
    wmm = WMMModel()
    d = wmm.declination(45.0, 0.0, 2025.0)  # legacy 3-arg form
    assert isinstance(d, float)
