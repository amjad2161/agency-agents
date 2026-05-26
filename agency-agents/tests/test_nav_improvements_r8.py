"""GODSKILL Navigation R8 — improvement-round tests.

Covers:
- SBASCorrector
- SlidingWindowFilter
- WiFiRTTPositioning
- PressureDepthNav
- GraphNeuralOdometry
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.satellite import SBASCorrector  # noqa: E402
from agency.navigation.fusion import SlidingWindowFilter  # noqa: E402
from agency.navigation.indoor_slam import WiFiRTTPositioning  # noqa: E402
from agency.navigation.underwater import PressureDepthNav  # noqa: E402
from agency.navigation.ai_enhance import GraphNeuralOdometry  # noqa: E402


# ============================================================================
# SBASCorrector
# ============================================================================

class TestSBASCorrector:
    def test_init(self):
        c = SBASCorrector()
        assert c is not None

    def test_fast_corr_reduces_range(self):
        c = SBASCorrector()
        out = c.apply_fast_corrections("G05", 22000000.0, {"G05": 1.5})
        assert out == pytest.approx(22000000.0 - 1.5)

    def test_iono_interp_returns_float(self):
        c = SBASCorrector()
        grid = [(10.0, 20.0, 5.0), (10.5, 20.5, 6.0), (10.2, 20.3, 5.5)]
        v = c.interpolate_ionospheric_grid(10.3, 20.3, grid)
        assert isinstance(v, float)

    def test_iono_interp_between_min_max(self):
        c = SBASCorrector()
        grid = [(0.0, 0.0, 1.0), (1.0, 1.0, 5.0), (0.5, 0.5, 3.0)]
        v = c.interpolate_ionospheric_grid(0.4, 0.4, grid)
        assert 1.0 <= v <= 5.0

    def test_protection_levels_positive(self):
        c = SBASCorrector()
        H = np.array([[1, 0, 1, 1], [0, 1, 1, 1], [1, 1, 1, 1],
                      [-1, 0, 1, 1]], dtype=float)
        sigma = np.array([1.0, 1.5, 0.8, 1.2])
        pl = c.compute_protection_levels(H, sigma)
        assert pl[0] > 0.0 and pl[1] > 0.0

    def test_protection_levels_shape(self):
        c = SBASCorrector()
        H = np.array([[1, 0, 1], [0, 1, 1], [1, 1, 1]], dtype=float)
        sigma = np.array([1.0, 1.0, 1.0])
        pl = c.compute_protection_levels(H, sigma)
        assert pl.shape == (2,)

    def test_correction_zero_when_missing(self):
        c = SBASCorrector()
        out = c.apply_fast_corrections("G99", 100.0, {"G05": 5.0})
        assert out == pytest.approx(100.0)


# ============================================================================
# SlidingWindowFilter
# ============================================================================

class TestSlidingWindowFilter:
    def test_init(self):
        f = SlidingWindowFilter(max_window=10)
        assert f.max_window == 10
        assert f.poses == []

    def test_add_pose(self):
        f = SlidingWindowFilter(max_window=5)
        f.add_pose(np.array([1.0, 2.0]), np.eye(2))
        assert len(f.poses) == 1
        assert len(f.covs) == 1

    def test_window_caps_at_max(self):
        f = SlidingWindowFilter(max_window=10)
        for k in range(20):
            f.add_pose(np.array([float(k), 0.0]), np.eye(2))
        assert len(f.poses) == 10
        # Newest preserved, oldest dropped
        assert float(f.poses[-1][0]) == pytest.approx(19.0)

    def test_marginalize_reduces_count(self):
        f = SlidingWindowFilter(max_window=10)
        for k in range(3):
            f.add_pose(np.array([float(k)]), np.eye(1))
        before = len(f.poses)
        f.marginalize_oldest()
        assert len(f.poses) == before - 1

    def test_get_window_returns_list(self):
        f = SlidingWindowFilter(max_window=10)
        f.add_pose(np.array([1.0]), np.eye(1))
        f.add_pose(np.array([2.0]), np.eye(1))
        out = f.get_window_poses()
        assert isinstance(out, list)
        assert len(out) == 2

    def test_information_matrix_shape(self):
        f = SlidingWindowFilter(max_window=10)
        f.add_pose(np.array([0.0, 0.0]), np.eye(2))
        f.add_pose(np.array([1.0, 1.0]), np.eye(2) * 2.0)
        Lam = f.information_matrix
        assert Lam.shape == (4, 4)

    def test_add_eleven_poses_window_le_ten(self):
        f = SlidingWindowFilter(max_window=10)
        for k in range(11):
            f.add_pose(np.array([float(k)]), np.eye(1))
        assert len(f.poses) <= 10


# ============================================================================
# WiFiRTTPositioning
# ============================================================================

class TestWiFiRTTPositioning:
    def test_init(self):
        w = WiFiRTTPositioning()
        assert w.aps == []

    def test_add_ap(self):
        w = WiFiRTTPositioning()
        w.add_ap("AP1", (0.0, 0.0), 100.0)
        assert len(w.aps) == 1

    def test_under_three_aps_returns_none(self):
        w = WiFiRTTPositioning()
        w.add_ap("A", (0.0, 0.0), 100.0)
        w.add_ap("B", (5.0, 0.0), 100.0)
        assert w.compute_position() is None

    def test_three_aps_returns_tuple(self):
        w = WiFiRTTPositioning()
        # 3 APs around origin, true pos = (1,1)
        # dist from (0,0)≈1.414, (10,0)≈9.06, (0,10)≈9.06
        # RTT(ns) = 2 * d / c * 1e9
        c = 299792458.0
        for ap_id, pos, d in [("A", (0.0, 0.0), 1.414),
                              ("B", (10.0, 0.0), 9.06),
                              ("C", (0.0, 10.0), 9.06)]:
            rtt_ns = 2.0 * d / c * 1e9
            w.add_ap(ap_id, pos, rtt_ns)
        out = w.compute_position()
        assert out is not None
        assert len(out) == 3

    def test_ranging_error_positive(self):
        w = WiFiRTTPositioning()
        assert w.ranging_error_model(5.0) > 0.0

    def test_ranging_error_increases_with_distance(self):
        w = WiFiRTTPositioning()
        e1 = w.ranging_error_model(1.0)
        e2 = w.ranging_error_model(20.0)
        assert e2 > e1

    def test_position_close_for_ideal_grid(self):
        w = WiFiRTTPositioning()
        c = 299792458.0
        true = np.array([3.0, 4.0])
        anchors = [("A", (0.0, 0.0)), ("B", (10.0, 0.0)),
                   ("C", (0.0, 10.0)), ("D", (10.0, 10.0))]
        for ap_id, pos in anchors:
            d = float(np.linalg.norm(np.asarray(pos) - true))
            rtt_ns = 2.0 * d / c * 1e9
            w.add_ap(ap_id, pos, rtt_ns)
        x, y, _ = w.compute_position()
        err = math.hypot(x - 3.0, y - 4.0)
        assert err < 5.0


# ============================================================================
# PressureDepthNav
# ============================================================================

class TestPressureDepthNav:
    def test_init(self):
        d = PressureDepthNav()
        assert d is not None

    def test_depth_at_zero_pressure(self):
        d = PressureDepthNav()
        assert d.depth_from_pressure(0.0, 45.0) == pytest.approx(0.0)

    def test_depth_positive_for_positive_pressure(self):
        d = PressureDepthNav()
        assert d.depth_from_pressure(100.0, 45.0) > 0.0

    def test_depth_increases_with_pressure(self):
        d = PressureDepthNav()
        d1 = d.depth_from_pressure(50.0, 0.0)
        d2 = d.depth_from_pressure(500.0, 0.0)
        assert d2 > d1

    def test_sound_speed_default_conditions(self):
        d = PressureDepthNav()
        c = d.sound_speed_mackenzie(temp_c=15.0, salinity_ppt=35.0,
                                    depth_m=0.0)
        # Mackenzie at 15°C/35‰/0m ≈ 1507.4 m/s
        assert abs(c - 1500.0) < 50.0

    def test_vertical_velocity_shape(self):
        d = PressureDepthNav()
        depths = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
        v = d.vertical_velocity(depths, dt=1.0)
        assert v.shape == depths.shape

    def test_sound_speed_increases_with_temperature(self):
        d = PressureDepthNav()
        c1 = d.sound_speed_mackenzie(5.0, 35.0, 0.0)
        c2 = d.sound_speed_mackenzie(25.0, 35.0, 0.0)
        assert c2 > c1


# ============================================================================
# GraphNeuralOdometry
# ============================================================================

class TestGraphNeuralOdometry:
    def test_init(self):
        g = GraphNeuralOdometry()
        assert g.nodes == {}
        assert g.edges == []

    def test_add_node_returns_int(self):
        g = GraphNeuralOdometry()
        nid = g.add_node(np.array([1.0, 2.0, 3.0]))
        assert isinstance(nid, int)

    def test_two_nodes_distinct_ids(self):
        g = GraphNeuralOdometry()
        n1 = g.add_node(np.array([1.0, 0.0]))
        n2 = g.add_node(np.array([0.0, 1.0]))
        assert n1 != n2

    def test_add_edge_stored(self):
        g = GraphNeuralOdometry()
        n1 = g.add_node(np.array([0.0, 0.0]))
        n2 = g.add_node(np.array([1.0, 0.0]))
        g.add_edge(n1, n2, np.array([1.0, 0.0]))
        assert len(g.edges) == 1

    def test_message_passing_runs(self):
        g = GraphNeuralOdometry()
        n1 = g.add_node(np.array([0.5, 0.0]))
        n2 = g.add_node(np.array([0.0, 0.5]))
        g.add_edge(n1, n2, np.array([0.0, 0.0]))
        g.message_passing_step()
        # No exception, features still 2-D
        assert g.predict_odometry(n1).shape == (2,)

    def test_predict_odometry_returns_array(self):
        g = GraphNeuralOdometry()
        n1 = g.add_node(np.array([0.1, 0.2, 0.3]))
        out = g.predict_odometry(n1)
        assert isinstance(out, np.ndarray)
        assert out.shape == (3,)

    def test_multistep_message_pass_changes_features(self):
        g = GraphNeuralOdometry()
        n1 = g.add_node(np.array([0.5, 0.5]))
        n2 = g.add_node(np.array([-0.5, 0.5]))
        n3 = g.add_node(np.array([0.5, -0.5]))
        g.add_edge(n1, n2, np.zeros(2))
        g.add_edge(n2, n3, np.zeros(2))
        g.add_edge(n1, n3, np.zeros(2))
        before = g.predict_odometry(n1).copy()
        for _ in range(3):
            g.message_passing_step()
        after = g.predict_odometry(n1)
        assert not np.allclose(before, after)
