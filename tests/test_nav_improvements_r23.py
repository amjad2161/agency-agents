"""GODSKILL Navigation R23 — improvement-round tests."""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.satellite import NavICReceiver  # noqa: E402
from agency.navigation.indoor_inertial import WheelEncoderOdometry  # noqa: E402
from agency.navigation.underwater import SonarRayCasting  # noqa: E402
from agency.navigation.fusion import CovarianceResamplingPF  # noqa: E402
from agency.navigation.ai_enhance import OnlinePlaceDatabase  # noqa: E402


# ============================================================================
# NavICReceiver
# ============================================================================

class TestNavICReceiver:
    def setup_method(self):
        self.nav = NavICReceiver()
        self.nav.add_satellite(1, [0, 0, 36000e3])
        self.nav.add_satellite(2, [25000e3, 0, 25000e3])

    def test_pseudorange_positive(self):
        pr = self.nav.pseudorange(1, [0, 0, 0])
        assert pr > 0

    def test_pseudorange_increases_with_distance(self):
        pr1 = self.nav.pseudorange(1, [0, 0, 0])
        pr2 = self.nav.pseudorange(1, [1e6, 0, 0])
        assert pr2 > pr1

    def test_dual_freq_iono_float(self):
        v = self.nav.dual_freq_iono(1, 20e6, 20.1e6)
        assert isinstance(v, float)

    def test_dual_freq_iono_equal_ranges(self):
        P = 20e6
        v = self.nav.dual_freq_iono(1, P, P)
        assert abs(v - P) < 100.0

    def test_elevation_angle_range(self):
        el = self.nav.elevation_angle(1, [0, 0, 0])
        assert -np.pi / 2 <= el <= np.pi / 2

    def test_elevation_nadir_satellite(self):
        el = self.nav.elevation_angle(1, [0, 0, 0])
        assert el > 0.5

    def test_dop_positive(self):
        dop = self.nav.dilution_of_precision([1, 2], [0, 0, 0])
        assert dop > 0


# ============================================================================
# WheelEncoderOdometry
# ============================================================================

class TestWheelEncoderOdometry:
    def setup_method(self):
        self.odo = WheelEncoderOdometry(0.1, 0.5, 360)

    def test_ticks_to_distance(self):
        d = self.odo.ticks_to_distance(360)
        assert abs(d - 2 * np.pi * 0.1) < 1e-9

    def test_straight_motion(self):
        pose = self.odo.update(360, 360)
        assert abs(pose[2]) < 1e-9

    def test_straight_position(self):
        d = 2 * np.pi * 0.1
        pose = self.odo.update(360, 360)
        assert abs(pose[0] - d) < 1e-9

    def test_in_place_rotation(self):
        self.odo.update(0, 360)
        assert self.odo.theta != 0.0

    def test_pose_returns_3_elements(self):
        p = self.odo.pose()
        assert len(p) == 3

    def test_reset_clears_state(self):
        self.odo.update(100, 200)
        self.odo.reset()
        assert np.allclose(self.odo.pose(), 0.0)

    def test_velocity_from_ticks(self):
        v, w = self.odo.velocity_from_ticks(360, 360, dt=1.0)
        assert abs(v - 2 * np.pi * 0.1) < 1e-9
        assert abs(w) < 1e-9


# ============================================================================
# SonarRayCasting
# ============================================================================

class TestSonarRayCasting:
    def setup_method(self):
        grid = np.zeros((20, 20), dtype=bool)
        grid[:, 19] = True
        self.sonar = SonarRayCasting(grid, resolution_m=1.0,
                                     max_range_m=25.0)

    def test_cast_ray_hits_wall(self):
        d = self.sonar.cast_ray((0, 10), 0.0)
        assert d < 25.0

    def test_cast_ray_open_direction(self):
        d = self.sonar.cast_ray((10, 10), -np.pi / 2)
        assert d == 25.0

    def test_scan_shape(self):
        angles = np.linspace(0, 2 * np.pi, 8, endpoint=False)
        ranges = self.sonar.scan((5, 10), angles)
        assert ranges.shape == (8,)

    def test_scan_ranges_positive(self):
        angles = np.linspace(0, np.pi, 6)
        ranges = self.sonar.scan((5, 5), angles)
        assert np.all(ranges > 0)

    def test_expected_obstacle_xy_shape(self):
        pt = self.sonar.expected_obstacle_xy((0, 10), 0.0, 10.0)
        assert pt.shape == (2,)

    def test_expected_obstacle_xy_correct(self):
        pt = self.sonar.expected_obstacle_xy((0.0, 0.0), 0.0, 5.0)
        assert abs(pt[0] - 5.0) < 1e-9 and abs(pt[1]) < 1e-9

    def test_scan_match_score_range(self):
        angles = np.linspace(0, np.pi, 4)
        sim = self.sonar.scan((5, 5), angles)
        score = self.sonar.scan_match_score((5, 5), sim, angles)
        assert 0.0 < score <= 1.0


# ============================================================================
# CovarianceResamplingPF
# ============================================================================

class TestCovarianceResamplingPF:
    def setup_method(self):
        np.random.seed(42)
        self.pf = CovarianceResamplingPF(n_particles=100, state_dim=2,
                                         process_noise_std=0.05, seed=42)

    def test_initialize_particle_count(self):
        self.pf.initialize([0, 0], np.eye(2) * 0.1)
        assert self.pf.particles.shape == (100, 2)

    def test_weights_sum_to_one_after_init(self):
        self.pf.initialize([0, 0], np.eye(2) * 0.1)
        assert abs(self.pf.weights.sum() - 1.0) < 1e-9

    def test_predict_changes_particles(self):
        self.pf.initialize([0, 0], np.eye(2) * 0.1)
        before = self.pf.particles.copy()
        self.pf.predict()
        assert not np.allclose(before, self.pf.particles)

    def test_update_weights_not_uniform(self):
        self.pf.initialize([0, 0], np.eye(2) * 0.1)
        self.pf.update([1.0, 0.0], np.eye(2), np.eye(2) * 0.1)
        assert not np.allclose(self.pf.weights, 1.0 / 100)

    def test_effective_n_positive(self):
        self.pf.initialize([0, 0], np.eye(2) * 0.1)
        assert self.pf.effective_n() > 0

    def test_regularized_resample_uniform_weights(self):
        self.pf.initialize([0, 0], np.eye(2) * 0.1)
        self.pf.update([0.0, 0.0], np.eye(2), np.eye(2) * 0.1)
        self.pf.regularized_resample()
        assert abs(self.pf.weights.sum() - 1.0) < 1e-9

    def test_estimate_scalar(self):
        self.pf.initialize([5.0, 3.0], np.eye(2) * 0.01)
        est = self.pf.estimate()
        assert abs(est - 5.0) < 1.0


# ============================================================================
# OnlinePlaceDatabase
# ============================================================================

class TestOnlinePlaceDatabase:
    def setup_method(self):
        np.random.seed(0)
        self.db = OnlinePlaceDatabase(feature_dim=8,
                                      similarity_threshold=0.9)

    def test_add_place_returns_true_first(self):
        f = np.random.randn(8)
        assert self.db.add_place(f, label="A")

    def test_add_duplicate_returns_false(self):
        f = np.random.randn(8)
        self.db.add_place(f, label="A")
        assert not self.db.add_place(f, label="A2")

    def test_size_increases(self):
        self.db.add_place(np.random.randn(8))
        self.db.add_place(np.random.randn(8) * 10)
        assert self.db.size() >= 1

    def test_query_returns_top_k(self):
        f1 = np.ones(8) / np.sqrt(8)
        f2 = -np.ones(8) / np.sqrt(8)
        self.db.add_place(f1, "pos")
        self.db.add_place(f2, "neg")
        results = self.db.query(f1, top_k=2)
        assert len(results) == 2

    def test_query_best_match(self):
        f1 = np.array([1, 0, 0, 0, 0, 0, 0, 0], dtype=float)
        f2 = np.array([0, 1, 0, 0, 0, 0, 0, 0], dtype=float)
        self.db.add_place(f1, "x")
        self.db.add_place(f2, "y")
        results = self.db.query(f1, top_k=1)
        assert results[0][1] == "x"

    def test_update_feature(self):
        f = np.ones(8)
        self.db.add_place(f, "old")
        new_f = np.array([1, 0, 0, 0, 0, 0, 0, 0], dtype=float)
        self.db.update_feature(0, new_f)
        results = self.db.query(new_f, top_k=1)
        assert results[0][0] > 0.99

    def test_prune_removes_duplicates(self):
        f1 = np.ones(8)
        f2 = np.ones(8) * 0.999
        self.db.threshold = 0.0
        self.db.add_place(f1, "A")
        self.db.add_place(f2, "B")
        self.db.threshold = 0.9
        before = self.db.size()
        self.db.prune()
        assert self.db.size() <= before
