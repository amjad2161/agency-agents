"""GODSKILL Navigation R13 — improvement-round tests.

Covers:
- DifferentialGNSS
- ZeroVelocityUpdateFilter
- SemanticLandmarkMapper
- InertialTerrainFollowing
- ReinforcementPathPlanner
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.satellite import DifferentialGNSS  # noqa: E402
from agency.navigation.fusion import ZeroVelocityUpdateFilter  # noqa: E402
from agency.navigation.indoor_slam import SemanticLandmarkMapper  # noqa: E402
from agency.navigation.underground import InertialTerrainFollowing  # noqa: E402
from agency.navigation.ai_enhance import ReinforcementPathPlanner  # noqa: E402


# ============================================================================
# DifferentialGNSS
# ============================================================================

def _dgnss_setup():
    base_pos = np.array([0.0, 0.0, 0.0])
    sat_positions = {
        "G01": np.array([20000000.0, 0.0, 20000000.0]),
        "G02": np.array([0.0, 22000000.0, 18000000.0]),
        "G03": np.array([-19000000.0, -5000000.0, 21000000.0]),
    }
    # Measured pseudoranges = true + biased error
    base_pseudoranges = {}
    for sv, pos in sat_positions.items():
        true_range = float(np.linalg.norm(pos - base_pos))
        base_pseudoranges[sv] = true_range + 5.0  # +5 m bias
    return base_pos, sat_positions, base_pseudoranges


class TestDifferentialGNSS:
    def test_init(self):
        d = DifferentialGNSS()
        assert d is not None

    def test_compute_corrections_returns_dict(self):
        d = DifferentialGNSS()
        base_pos, sat_pos, base_pr = _dgnss_setup()
        corr = d.compute_corrections(base_pr, base_pos, sat_pos)
        assert isinstance(corr, dict)
        assert set(corr.keys()) == set(base_pr.keys())

    def test_corrections_reduce_range_error(self):
        d = DifferentialGNSS()
        base_pos, sat_pos, base_pr = _dgnss_setup()
        corr = d.compute_corrections(base_pr, base_pos, sat_pos)
        # Each correction should be ~ -5 m
        for sv in base_pr:
            assert corr[sv] == pytest.approx(-5.0, abs=1e-6)

    def test_apply_corrections_length_matches(self):
        d = DifferentialGNSS()
        rover_pr = {"G01": 100.0, "G02": 200.0, "G03": 300.0}
        corr = {"G01": -5.0, "G02": -5.0, "G03": -5.0}
        out = d.apply_corrections(rover_pr, corr)
        assert out.shape == (3,)

    def test_extrapolate_correction_increases_with_age(self):
        d = DifferentialGNSS()
        c0 = d.extrapolate_correction(1.0, age_s=0.0, correction_rate=0.5)
        c1 = d.extrapolate_correction(1.0, age_s=10.0, correction_rate=0.5)
        assert c1 > c0

    def test_quality_flag_good(self):
        d = DifferentialGNSS()
        assert d.quality_flag(10.0, threshold=30.0) == "good"

    def test_quality_flag_invalid(self):
        d = DifferentialGNSS()
        assert d.quality_flag(80.0, threshold=30.0) == "invalid"


# ============================================================================
# ZeroVelocityUpdateFilter
# ============================================================================

class TestZeroVelocityUpdateFilter:
    def test_init(self):
        f = ZeroVelocityUpdateFilter()
        assert f.x.shape == (9,)
        assert f.P.shape == (9, 9)

    def test_detect_stationary_true(self):
        f = ZeroVelocityUpdateFilter()
        a = np.tile([0.0, 0.0, 9.80665], (30, 1))
        g = np.zeros((30, 3))
        assert f.detect_stationary(a, g) is True

    def test_detect_stationary_false(self):
        f = ZeroVelocityUpdateFilter()
        rng = np.random.RandomState(0)
        a = 5.0 * rng.randn(30, 3) + np.array([0.0, 0.0, 9.81])
        g = 1.0 * rng.randn(30, 3)
        assert f.detect_stationary(a, g) is False

    def test_apply_zupt_zeros_velocity(self):
        f = ZeroVelocityUpdateFilter()
        f.x[3:6] = np.array([2.0, 1.5, -0.5])
        x, _ = f.apply_zupt(f.x, f.P)
        assert np.allclose(x[3:6], 0.0, atol=1e-3)

    def test_apply_zupt_reduces_P(self):
        f = ZeroVelocityUpdateFilter()
        before = float(np.trace(f.P[3:6, 3:6]))
        _, P = f.apply_zupt(f.x, f.P)
        after = float(np.trace(P[3:6, 3:6]))
        assert after < before

    def test_propagate_changes_pos(self):
        f = ZeroVelocityUpdateFilter()
        f.x[3:6] = np.array([1.0, 0.0, 0.0])
        x, _ = f.propagate(f.x, f.P, np.array([0.0, 0.0, 0.0]), dt=1.0)
        assert x[0] > 0.0

    def test_run_step_returns_three_tuple(self):
        f = ZeroVelocityUpdateFilter()
        out = f.run_step(np.tile([0.0, 0.0, 9.81], (10, 1)), dt=0.01)
        assert len(out) == 3
        for arr in out:
            assert arr.shape == (3,)


# ============================================================================
# SemanticLandmarkMapper
# ============================================================================

class TestSemanticLandmarkMapper:
    def test_init(self):
        m = SemanticLandmarkMapper()
        assert m.landmarks == {}

    def test_add_landmark(self):
        m = SemanticLandmarkMapper()
        m.add_landmark("door1", "door", (1.0, 2.0), [0.5, 0.3, 0.1])
        assert "door1" in m.landmarks

    def test_find_nearest_returns_tuple(self):
        m = SemanticLandmarkMapper()
        m.add_landmark("door1", "door", (1.0, 1.0), [0.0])
        m.add_landmark("door2", "door", (5.0, 5.0), [0.0])
        out = m.find_nearest((0.0, 0.0))
        assert isinstance(out, tuple)
        assert len(out) == 2

    def test_find_nearest_respects_category(self):
        m = SemanticLandmarkMapper()
        m.add_landmark("d1", "door", (1.0, 0.0), [0.0])
        m.add_landmark("e1", "elevator", (0.5, 0.0), [0.0])
        lm_id, _ = m.find_nearest((0.0, 0.0), category="door")
        assert lm_id == "d1"

    def test_recognize_landmark_returns_pair(self):
        m = SemanticLandmarkMapper()
        vocab = {"door": np.array([1.0, 0.0]),
                 "elevator": np.array([0.0, 1.0])}
        cat, conf = m.recognize_landmark(np.array([0.9, 0.1]), vocab)
        assert isinstance(cat, str)
        assert isinstance(conf, float)

    def test_confidence_in_unit_interval(self):
        m = SemanticLandmarkMapper()
        vocab = {"door": np.array([1.0, 0.0])}
        _, conf = m.recognize_landmark(np.array([0.5, 0.5]), vocab)
        assert 0.0 <= conf <= 1.0

    def test_topological_graph_connects_nearby(self):
        m = SemanticLandmarkMapper()
        m.add_landmark("a", "door", (0.0, 0.0), [0.0])
        m.add_landmark("b", "door", (5.0, 0.0), [0.0])
        m.add_landmark("c", "door", (50.0, 0.0), [0.0])
        adj = m.compute_topological_graph()
        assert "b" in adj["a"]
        assert "c" not in adj["a"]


# ============================================================================
# InertialTerrainFollowing
# ============================================================================

class TestInertialTerrainFollowing:
    def test_init(self):
        t = InertialTerrainFollowing()
        assert t.terrain_clearance == 0.0

    def test_update_returns_float(self):
        t = InertialTerrainFollowing()
        out = t.update_terrain_alt(50.0, 48.0, 0.1)
        assert isinstance(out, float)

    def test_terrain_contour_match_returns_float(self):
        t = InertialTerrainFollowing()
        m = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 4.0, 3.0, 2.0, 1.0,
                      0.0, 0.0, 0.0])
        observed = m[2:8]    # known offset of 2
        offset = t.terrain_contour_match(observed, m)
        assert isinstance(offset, float)

    def test_offset_within_profile_range(self):
        t = InertialTerrainFollowing()
        m = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 4.0, 3.0, 2.0, 1.0])
        observed = m[3:7]
        offset = t.terrain_contour_match(observed, m)
        assert -len(m) <= offset <= len(m)

    def test_slope_returns_array(self):
        t = InertialTerrainFollowing()
        slopes = t.slope_estimate(np.array([0.0, 1.0, 2.0, 3.0]), dx=1.0)
        assert slopes.shape == (4,)

    def test_flat_terrain_slope_zero(self):
        t = InertialTerrainFollowing()
        slopes = t.slope_estimate(np.array([5.0, 5.0, 5.0, 5.0, 5.0]),
                                  dx=1.0)
        assert np.allclose(slopes, 0.0)

    def test_update_position_changes_pos(self):
        t = InertialTerrainFollowing()
        new = t.update_position_from_terrain((0.0, 0.0), offset=3.0,
                                             heading=0.0)
        assert new[0] == pytest.approx(3.0)


# ============================================================================
# ReinforcementPathPlanner
# ============================================================================

class TestReinforcementPathPlanner:
    def test_init_q_table_shape(self):
        p = ReinforcementPathPlanner(grid_size=10)
        assert p.Q.shape == (100, 8)

    def test_choose_action_valid(self):
        p = ReinforcementPathPlanner()
        a = p.choose_action((5, 5), epsilon=0.0)
        assert 0 <= a <= 7

    def test_choose_action_explores(self):
        p = ReinforcementPathPlanner(seed=0)
        # ε=1 → uniformly random; expect at least 2 distinct actions in 20 draws
        actions = {p.choose_action((0, 0), epsilon=1.0) for _ in range(20)}
        assert len(actions) > 1

    def test_update_q_changes_value(self):
        p = ReinforcementPathPlanner()
        before = p.Q[0, 0]
        p.update_q((0, 0), 0, reward=10.0, next_state=(0, 1),
                   alpha=0.5, gamma=0.9)
        assert p.Q[0, 0] != before

    def test_plan_path_returns_list(self):
        p = ReinforcementPathPlanner(grid_size=5, seed=1)
        path = p.plan_path((0, 0), (3, 3), max_steps=20)
        assert isinstance(path, list)

    def test_plan_path_reaches_vicinity(self):
        p = ReinforcementPathPlanner(grid_size=5, seed=2)
        path = p.plan_path((0, 0), (3, 3), max_steps=40)
        end = path[-1]
        # Within 2 cells of goal after training rollout
        assert math.hypot(end[0] - 3, end[1] - 3) <= 2.5

    def test_plan_path_length_bounded(self):
        p = ReinforcementPathPlanner(grid_size=5, seed=3)
        path = p.plan_path((0, 0), (3, 3), max_steps=10)
        assert len(path) <= 10 + 1
