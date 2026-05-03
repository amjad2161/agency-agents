"""GODSKILL Nav v11 — Round 3 improvement tests.

Covers:
  * MultiConstellationClock:  ISB estimation, GPS↔Galileo time, BDT↔UTC,
                              combined Klobuchar + Hopfield atmospheric delay.
  * TransformerPredictor:     attention forward pass, encode shapes,
                              autoregressive predict, online update.
  * PoseGraphOptimizer:       node/edge add, GN convergence, loop closure
                              detection, marginal covariance.
  * SonarSLAM (NDT):          NDT scan matching returns valid transform,
                              bathymetric loop closure, uncertainty
                              propagation.
"""

from __future__ import annotations

import math
import os
import sys
from datetime import datetime, timezone

_THIS = os.path.abspath(os.path.dirname(__file__))
_RUNTIME = os.path.abspath(os.path.join(_THIS, "..", "runtime"))
if _RUNTIME not in sys.path:
    sys.path.insert(0, _RUNTIME)

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from agency.navigation.satellite import (  # noqa: E402
    MultiConstellationClock,
    InterSystemBias,
)
from agency.navigation.fusion import PoseGraphOptimizer  # noqa: E402
from agency.navigation.ai_enhance import TransformerPredictor  # noqa: E402
from agency.navigation.underwater import (  # noqa: E402
    SonarSLAM,
    BathymetricMatcher,
)


# ---------------------------------------------------------------------------
# MultiConstellationClock
# ---------------------------------------------------------------------------


def test_clock_isb_estimation_returns_per_system_keys():
    clock = MultiConstellationClock(reference="GPS")
    out = clock.estimate_inter_system_bias(
        gps_obs=[0.0, 0.1, -0.1],
        glonass_obs=[5.0, 5.0, 5.0],
        galileo_obs=[2.0, 2.0],
        beidou_obs=[3.0, 3.0],
    )
    for k in ("GPS_ns", "GLONASS_ns", "Galileo_ns", "BeiDou_ns"):
        assert k in out
    assert abs(out["GPS_ns"]) < 1.0  # near zero relative to itself
    assert out["GLONASS_ns"] > 0.0   # 5 m mean residual is positive bias
    assert out["n_observations"] == 10


def test_clock_isb_changes_with_reference():
    clock_gps = MultiConstellationClock(reference="GPS")
    clock_gal = MultiConstellationClock(reference="Galileo")
    args = dict(gps_obs=[0.0, 0.0], glonass_obs=[10.0, 10.0],
                galileo_obs=[5.0, 5.0], beidou_obs=[2.0, 2.0])
    a = clock_gps.estimate_inter_system_bias(**args)
    b = clock_gal.estimate_inter_system_bias(**args)
    # Galileo bias is zero relative to itself, nonzero relative to GPS.
    assert abs(b["Galileo_ns"]) < 1.0
    assert a["Galileo_ns"] > 0.0


def test_clock_isb_invalid_reference_raises():
    with pytest.raises(ValueError):
        MultiConstellationClock(reference="QZSS")


def test_clock_gps_to_galileo_time_within_week():
    clock = MultiConstellationClock()
    gst_week, gst_tow = clock.gps_to_galileo_time(2300, 100.0)
    # 100 s + 19 s offset → still in same week
    assert gst_week == 2300
    assert math.isclose(gst_tow, 119.0, abs_tol=1e-6)


def test_clock_gps_to_galileo_time_week_rollover():
    clock = MultiConstellationClock()
    # Last second of week + 19 s offset → next week
    gst_week, gst_tow = clock.gps_to_galileo_time(2300, 604_799.0)
    assert gst_week == 2301
    assert gst_tow >= 0.0 and gst_tow < 604_800.0


def test_clock_beidou_week_to_utc_returns_datetime():
    dt = MultiConstellationClock.beidou_week_to_utc(0, 0.0)
    assert isinstance(dt, datetime)
    assert dt == datetime(2006, 1, 1, tzinfo=timezone.utc)


def test_clock_beidou_week_to_utc_one_week_later():
    dt = MultiConstellationClock.beidou_week_to_utc(1, 0.0)
    assert dt == datetime(2006, 1, 8, tzinfo=timezone.utc)


def test_clock_atmospheric_delay_total_positive():
    clock = MultiConstellationClock()
    out = clock.predict_atmospheric_delay(
        lat=35.0, lon=139.0, elevation_deg=45.0, doy=180,
    )
    assert out["ionospheric_m"] > 0.0
    assert out["tropospheric_m"] > 0.0
    assert out["total_slant_m"] > out["ionospheric_m"]


def test_clock_atmospheric_delay_grows_at_low_elevation():
    clock = MultiConstellationClock()
    high = clock.predict_atmospheric_delay(0.0, 0.0, 80.0, 180)
    low = clock.predict_atmospheric_delay(0.0, 0.0, 10.0, 180)
    assert low["total_slant_m"] > high["total_slant_m"]


# ---------------------------------------------------------------------------
# TransformerPredictor
# ---------------------------------------------------------------------------


def test_transformer_construct_invalid_dims():
    with pytest.raises(ValueError):
        TransformerPredictor(d_model=15, n_heads=4)


def test_transformer_attention_output_shape():
    tp = TransformerPredictor(d_model=8, n_heads=2, n_layers=1)
    Q = np.random.default_rng(0).standard_normal((2, 4, 4))  # (heads, T, d_h)
    K = np.random.default_rng(1).standard_normal((2, 4, 4))
    V = np.random.default_rng(2).standard_normal((2, 4, 4))
    out = tp._attention(Q, K, V)
    assert out.shape == (2, 4, 4)


def test_transformer_encode_shape():
    tp = TransformerPredictor(d_model=16, n_heads=4, n_layers=2)
    traj = np.cumsum(np.ones((10, 2)), axis=0)
    enc = tp.encode(traj)
    assert enc.shape == (10, 16)


def test_transformer_encode_rejects_bad_shape():
    tp = TransformerPredictor()
    with pytest.raises(ValueError):
        tp.encode(np.zeros((10, 3)))


def test_transformer_predict_returns_steps_ahead():
    tp = TransformerPredictor()
    tp.encode(np.cumsum(np.ones((8, 2)), axis=0))
    out = tp.predict(steps_ahead=5)
    assert len(out["positions"]) == 5
    assert len(out["uncertainty_ellipses"]) == 5
    # Last ellipse should be at least as large as the first.
    assert (out["uncertainty_ellipses"][-1]["semi_major_m"]
            >= out["uncertainty_ellipses"][0]["semi_major_m"])


def test_transformer_predict_without_encode_raises():
    tp = TransformerPredictor()
    with pytest.raises(RuntimeError):
        tp.predict(steps_ahead=3)


def test_transformer_update_returns_mse_and_changes_weights():
    tp = TransformerPredictor(seed=42)
    tp.encode(np.cumsum(np.ones((6, 2)), axis=0))
    snapshot = tp.W_out.copy()
    mse = tp.update(actual_pos=np.array([10.0, 10.0]))
    assert mse >= 0.0
    assert not np.allclose(tp.W_out, snapshot)


# ---------------------------------------------------------------------------
# PoseGraphOptimizer
# ---------------------------------------------------------------------------


def _info() -> list:
    return [[1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0]]


def test_pose_graph_add_pose_and_constraint():
    g = PoseGraphOptimizer()
    g.add_pose(0, 0.0, 0.0, 0.0)
    g.add_pose(1, 1.0, 0.0, 0.0)
    g.add_constraint(0, 1, 1.0, 0.0, 0.0, _info())
    assert g.n_poses == 2
    assert g.n_edges == 1


def test_pose_graph_add_duplicate_raises():
    g = PoseGraphOptimizer()
    g.add_pose(0, 0.0, 0.0, 0.0)
    with pytest.raises(ValueError):
        g.add_pose(0, 1.0, 1.0, 0.0)


def test_pose_graph_constraint_unknown_node_raises():
    g = PoseGraphOptimizer()
    g.add_pose(0, 0.0, 0.0, 0.0)
    with pytest.raises(ValueError):
        g.add_constraint(0, 99, 1.0, 0.0, 0.0, _info())


def test_pose_graph_optimize_corrects_drift():
    g = PoseGraphOptimizer()
    # 5-node chain along x, but add jitter to initial estimates.
    for i in range(5):
        g.add_pose(i, float(i) + 0.5, 0.2, 0.05)
    for i in range(4):
        g.add_constraint(i, i + 1, 1.0, 0.0, 0.0, _info())
    # Anchor first node back to origin via strong self-edge surrogate.
    info_strong = [[1e6, 0, 0], [0, 1e6, 0], [0, 0, 1e6]]
    # No self-edge API; rely on the built-in anchor of the first node.
    out = g.optimize(max_iterations=50)
    assert out["iterations"] >= 1
    # Final cost should be small after optimization.
    assert out["final_cost"] < 10.0


def test_pose_graph_optimize_empty_returns_zero():
    g = PoseGraphOptimizer()
    out = g.optimize()
    assert out["final_cost"] == 0.0
    assert out["converged"] is True


def test_pose_graph_loop_closure_detection():
    g = PoseGraphOptimizer()
    # Trajectory loops back on itself.
    g.add_pose(0, 0.0, 0.0, 0.0)
    g.add_pose(1, 5.0, 0.0, 0.0)
    g.add_pose(2, 5.0, 5.0, 0.0)
    g.add_pose(3, 0.0, 5.0, 0.0)
    g.add_pose(4, 0.0, 1.0, 0.0)
    g.add_pose(5, 0.0, 0.5, 0.0)  # back near start
    g.add_pose(6, 0.1, 0.1, 0.0)
    candidates = g.detect_loop_closure(6, radius_m=2.0, min_id_gap=5)
    assert 0 in candidates  # node 0 is within radius and gap >= 5


def test_pose_graph_marginal_covariance_block_shape():
    g = PoseGraphOptimizer()
    g.add_pose(0, 0.0, 0.0, 0.0)
    g.add_pose(1, 1.0, 0.0, 0.0)
    g.add_constraint(0, 1, 1.0, 0.0, 0.0, _info())
    cov = g.marginal_covariance(1)
    assert len(cov) == 3
    assert all(len(row) == 3 for row in cov)
    # Diagonal entries should be non-negative.
    assert all(cov[i][i] >= 0.0 for i in range(3))


# ---------------------------------------------------------------------------
# SonarSLAM (NDT + bathymetric loop closure + uncertainty)
# ---------------------------------------------------------------------------


def test_sonar_ndt_scan_matching_returns_transform():
    slam = SonarSLAM()
    rng = np.random.default_rng(0)
    scan_a = rng.uniform(-10, 10, size=(40, 2))
    scan_b = scan_a + np.array([0.5, -0.3])  # pure translation
    out = slam.scan_matching_ndt(scan_a, scan_b, cell_size=2.0,
                                 max_iter=20)
    assert out["R"].shape == (2, 2)
    assert out["t"].shape == (2,)
    assert out["iterations"] >= 1


def test_sonar_ndt_handles_bad_input():
    slam = SonarSLAM()
    out = slam.scan_matching_ndt(np.zeros((0, 2)), np.zeros((0, 2)))
    assert out["iterations"] == 0
    assert np.allclose(out["R"], np.eye(2))


def test_sonar_bathymetric_loop_closure_no_map():
    slam = SonarSLAM()
    bath = BathymetricMatcher()  # not loaded
    out = slam.bathymetric_loop_closure(bath, np.array([1.0, 2.0, 3.0]))
    assert out["closed"] is False


def test_sonar_bathymetric_loop_closure_match():
    slam = SonarSLAM()
    bath = BathymetricMatcher()
    grid = np.array([
        [10.0, 11.0, 12.0, 13.0, 14.0],
        [10.0, 11.0, 12.0, 13.0, 14.0],
        [10.0, 11.0, 12.0, 13.0, 14.0],
    ])
    bath.load_map(grid, origin_lat=0.0, origin_lon=0.0, resolution_m=1.0)
    out = slam.bathymetric_loop_closure(
        bath, depth_profile=np.array([10.0, 11.0, 12.0]),
        heading=math.pi / 2, threshold=0.85,
    )
    # Score should be >= 0.85 along a constant ridge.
    assert out["score"] >= 0.85
    assert out["closed"] is True


def test_sonar_uncertainty_propagation_default():
    slam = SonarSLAM()
    cov = slam.uncertainty_propagation()
    assert cov.shape == (3, 3)
    # Diagonal must be > 0 after propagation.
    assert all(cov[i, i] > 0.0 for i in range(3))


def test_sonar_uncertainty_propagation_with_jacobian():
    slam = SonarSLAM()
    J = np.array([[2.0, 0.0, 0.0],
                  [0.0, 1.0, 0.0],
                  [0.0, 0.0, 1.0]])
    P = np.eye(3)
    cov = slam.uncertainty_propagation(J, P)
    # Variance along x should be ~4 after the 2x scaling.
    assert cov[0, 0] > 3.0


def test_sonar_uncertainty_propagation_bad_shape_returns_default():
    slam = SonarSLAM()
    bad = np.zeros((2, 2))
    cov = slam.uncertainty_propagation(bad, bad)
    assert cov.shape == (3, 3)
