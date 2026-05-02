"""GODSKILL Nav v28.4 — Round 4 improvement tests.

Covers:
  * IMUPreintegration:   integrate, reset, bias correction Jacobians,
                          covariance positive semi-definite, factor build.
  * FactorGraph:         add/optimize/marginal, build_nav_graph integration.
  * NeuralRadianceMap:   positional encoding shape, forward scalar,
                          train_step reduces loss, query_map batch.
  * WMMModel enhanced:   declination/inclination range, total intensity,
                          grid_survey shape, secular variation.
"""
from __future__ import annotations

import os
import sys

_THIS = os.path.abspath(os.path.dirname(__file__))
_RUNTIME = os.path.abspath(os.path.join(_THIS, "..", "runtime"))
if _RUNTIME not in sys.path:
    sys.path.insert(0, _RUNTIME)

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from agency.navigation.indoor_inertial import IMUPreintegration  # noqa: E402
from agency.navigation.fusion import FactorGraph, build_nav_graph  # noqa: E402
from agency.navigation.ai_enhance import NeuralRadianceMap  # noqa: E402
from agency.navigation.offline_maps import WMMModel  # noqa: E402


# ---------------------------------------------------------------------------
# IMU Preintegration
# ---------------------------------------------------------------------------


def test_imu_preint_integrate_increments_step_count():
    pre = IMUPreintegration()
    accel = np.array([0.0, 0.0, 9.81])  # gravity-canceling
    gyro = np.array([0.0, 0.0, 0.1])
    for _ in range(10):
        pre.integrate(accel, gyro, dt=0.01)
    assert pre.n_steps == 10
    assert pre.delta_t == pytest.approx(0.1, rel=1e-6)


def test_imu_preint_pure_rotation_yields_so3():
    pre = IMUPreintegration()
    for _ in range(50):
        pre.integrate(np.zeros(3), np.array([0.0, 0.0, 0.2]), dt=0.01)
    R = pre.delta_R
    # Should be a valid rotation: R @ R.T ≈ I and det ≈ 1.
    assert np.allclose(R @ R.T, np.eye(3), atol=1e-6)
    assert np.linalg.det(R) == pytest.approx(1.0, rel=1e-5)


def test_imu_preint_reset_clears_state_keeps_bias():
    pre = IMUPreintegration(bias_gyro=np.array([0.01, 0.0, 0.0]))
    pre.integrate(np.array([0.1, 0.0, 0.0]), np.array([0.05, 0.0, 0.0]), dt=0.01)
    pre.reset()
    assert pre.n_steps == 0
    assert pre.delta_t == 0.0
    assert np.allclose(pre.delta_R, np.eye(3))
    assert np.allclose(pre.delta_v, 0.0)
    assert pre.bias_gyro[0] == pytest.approx(0.01)


def test_imu_preint_bias_correction_returns_three_arrays():
    pre = IMUPreintegration()
    for _ in range(20):
        pre.integrate(np.array([0.05, 0.0, 0.0]), np.array([0.0, 0.0, 0.05]), dt=0.01)
    dR, dv, dp = pre.bias_corrected_delta(
        np.array([0.001, 0.0, 0.0]), np.array([0.001, 0.0, 0.0])
    )
    assert dR.shape == (3, 3)
    assert dv.shape == (3,)
    assert dp.shape == (3,)


def test_imu_preint_covariance_psd():
    pre = IMUPreintegration()
    for _ in range(15):
        pre.integrate(np.array([0.1, 0.0, 0.0]), np.array([0.0, 0.0, 0.1]), dt=0.01)
    cov = pre.covariance()
    assert cov.shape == (9, 9)
    # PSD: all eigenvalues >= 0 (within numerical tolerance).
    eigs = np.linalg.eigvalsh(0.5 * (cov + cov.T))
    assert eigs.min() >= -1e-9


def test_imu_preint_create_factor_residual_shape():
    pre = IMUPreintegration()
    for _ in range(5):
        pre.integrate(np.array([0.0, 0.0, 9.81]), np.zeros(3), dt=0.02)
    pose_i = {"R": np.eye(3), "v": np.zeros(3), "p": np.zeros(3), "t": 0.0}
    pose_j = {"R": np.eye(3), "v": np.zeros(3), "p": np.zeros(3), "t": 0.1}
    factor = pre.create_factor(pose_i, pose_j)
    assert factor["residual"].shape == (9,)
    assert factor["info_matrix"].shape == (9, 9)


def test_imu_preint_zero_dt_raises():
    pre = IMUPreintegration()
    with pytest.raises(ValueError):
        pre.integrate(np.zeros(3), np.zeros(3), dt=0.0)


# ---------------------------------------------------------------------------
# Factor Graph
# ---------------------------------------------------------------------------


def test_factor_graph_add_variable_indexes_correctly():
    fg = FactorGraph()
    fg.add_variable("x0", 3)
    fg.add_variable("x1", 3)
    assert fg.n_variables == 2


def test_factor_graph_unary_factor_anchors_variable():
    fg = FactorGraph()
    fg.add_variable("x0", 3)
    fg.add_unary_factor("x0", measurement=np.array([1.0, 2.0, 3.0]),
                        info_matrix=np.eye(3))
    result = fg.optimize(max_iter=20)
    assert np.allclose(result["values"]["x0"], [1.0, 2.0, 3.0], atol=1e-3)


def test_factor_graph_binary_chain_converges():
    fg = FactorGraph()
    fg.add_variable("x0", 2)
    fg.add_variable("x1", 2)
    fg.add_variable("x2", 2)
    # Anchor x0.
    fg.add_unary_factor("x0", np.array([0.0, 0.0]), np.eye(2) * 100.0)
    fg.add_binary_factor("x0", "x1", np.array([1.0, 0.0]), np.eye(2))
    fg.add_binary_factor("x1", "x2", np.array([1.0, 0.0]), np.eye(2))
    result = fg.optimize(max_iter=30)
    assert np.allclose(result["values"]["x2"], [2.0, 0.0], atol=1e-2)
    assert result["chi2_final"] < 1e-3


def test_factor_graph_marginal_returns_covariance():
    fg = FactorGraph()
    fg.add_variable("x0", 2)
    fg.add_unary_factor("x0", np.array([1.0, 2.0]), np.eye(2))
    fg.optimize()
    m = fg.marginal("x0")
    assert m["mean"].shape == (2,)
    assert m["covariance"].shape == (2, 2)
    # Symmetric.
    assert np.allclose(m["covariance"], m["covariance"].T, atol=1e-6)


def test_factor_graph_unknown_variable_raises():
    fg = FactorGraph()
    fg.add_variable("x0", 3)
    with pytest.raises(KeyError):
        fg.add_binary_factor("x0", "x9", np.zeros(3), np.eye(3))


def test_build_nav_graph_runs_end_to_end():
    gps = [
        ("p0", np.array([0.0, 0.0, 0.0]), np.eye(3) * 10.0),
        ("p2", np.array([2.0, 0.0, 0.0]), np.eye(3) * 10.0),
    ]
    imu = [
        ("p0", "p1", np.array([1.0, 0.0, 0.0]), np.eye(3)),
        ("p1", "p2", np.array([1.0, 0.0, 0.0]), np.eye(3)),
    ]
    baro = [("p1", 0.0, 1.0)]
    res = build_nav_graph(gps, imu, baro)
    assert "values" in res
    assert "p1" in res["values"]
    assert res["values"]["p1"][0] == pytest.approx(1.0, abs=0.1)


# ---------------------------------------------------------------------------
# Neural Radiance Map
# ---------------------------------------------------------------------------


def test_neural_radiance_encode_position_shape():
    nrm = NeuralRadianceMap(L=4)
    pos = np.array([[0.1, 0.2, 0.3]])
    enc = nrm.encode_position(pos)
    expected_dim = 3 + 3 * 2 * 4
    assert enc.shape == (1, expected_dim)


def test_neural_radiance_forward_returns_scalar():
    nrm = NeuralRadianceMap(hidden_dim=16, n_layers=3, L=4)
    val = nrm.forward(np.array([0.0, 0.0, 0.0]))
    assert isinstance(val, float)


def test_neural_radiance_train_step_reduces_loss():
    nrm = NeuralRadianceMap(hidden_dim=32, n_layers=3, L=4, seed=7)
    rng = np.random.default_rng(0)
    P = rng.standard_normal((20, 3)) * 0.5
    Y = (P[:, 0] * -2.0 - 50.0).reshape(-1, 1)
    losses = []
    for _ in range(40):
        loss = nrm.train_step(P, Y, lr=0.01)
        losses.append(loss)
    assert losses[-1] < losses[0]


def test_neural_radiance_query_map_batch_shape():
    nrm = NeuralRadianceMap(hidden_dim=16, n_layers=3, L=3)
    grid = np.random.default_rng(1).standard_normal((25, 3))
    out = nrm.query_map(grid)
    assert out.shape == (25,)


def test_neural_radiance_invalid_config_raises():
    with pytest.raises(ValueError):
        NeuralRadianceMap(hidden_dim=0)
    with pytest.raises(ValueError):
        NeuralRadianceMap(n_layers=1)


# ---------------------------------------------------------------------------
# WMM Model — Enhanced (full field + secular variation + grid survey)
# ---------------------------------------------------------------------------


def test_wmm_compute_full_field_keys():
    wmm = WMMModel()
    full = wmm.compute_full_field(45.0, 10.0, alt_km=0.0, year=2025.0)
    for key in (
        "X_nT", "Y_nT", "Z_nT", "H_nT", "F_nT",
        "declination_deg", "inclination_deg",
    ):
        assert key in full


def test_wmm_inclination_in_valid_range():
    wmm = WMMModel()
    for lat in (-60.0, -30.0, 0.0, 30.0, 60.0):
        incl = wmm.inclination(lat, 0.0, alt_km=0.0, year=2025.0)
        assert -90.0 <= incl <= 90.0


def test_wmm_total_intensity_positive():
    wmm = WMMModel()
    F = wmm.total_intensity(45.0, 10.0, alt_km=0.0, year=2025.0)
    # Earth field magnitude lies in roughly 22000–67000 nT.
    assert 15000.0 < F < 80000.0


def test_wmm_grid_survey_shape():
    wmm = WMMModel()
    grid = wmm.grid_survey(
        lat_range=(0.0, 4.0), lon_range=(0.0, 6.0), step_deg=2.0, year=2025.0
    )
    assert grid["declination"].shape == (3, 4)
    assert grid["inclination"].shape == (3, 4)
    assert grid["intensity"].shape == (3, 4)
    assert grid["lats"].shape == (3,)
    assert grid["lons"].shape == (4,)


def test_wmm_grid_survey_invalid_step_raises():
    wmm = WMMModel()
    with pytest.raises(ValueError):
        wmm.grid_survey(lat_range=(0.0, 1.0), lon_range=(0.0, 1.0), step_deg=0.0)


def test_wmm_secular_variation_changes_intensity():
    wmm = WMMModel()
    F_2020 = wmm.total_intensity(0.0, 0.0, 0.0, 2020.0)
    F_2050 = wmm.total_intensity(0.0, 0.0, 0.0, 2050.0)
    # Secular variation must produce a measurable difference.
    assert F_2020 != F_2050
