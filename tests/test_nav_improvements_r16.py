"""GODSKILL Navigation R16 — improvement-round tests."""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.satellite import AdvancedRAIM  # noqa: E402
from agency.navigation.indoor_inertial import TiltCompensatedCompass  # noqa: E402
from agency.navigation.indoor_slam import GraphSLAM  # noqa: E402
from agency.navigation.fusion import FadingMemoryFilter  # noqa: E402
from agency.navigation.underwater import SoundVelocityProfile  # noqa: E402


# ============================================================================
# AdvancedRAIM
# ============================================================================

def _good_sky():
    az = np.radians([0.0, 60.0, 120.0, 180.0, 240.0, 300.0])
    el = np.radians([45.0, 60.0, 30.0, 75.0, 50.0, 40.0])
    return az, el


class TestAdvancedRAIM:
    def test_geometry_matrix_shape(self):
        r = AdvancedRAIM()
        az, el = _good_sky()
        H = r.geometry_matrix(az, el)
        assert H.shape == (6, 4)

    def test_geometry_last_column_ones(self):
        r = AdvancedRAIM()
        az, el = _good_sky()
        H = r.geometry_matrix(az, el)
        assert np.allclose(H[:, 3], 1.0)

    def test_protection_level_returns_two_floats(self):
        r = AdvancedRAIM()
        hpl, vpl = r.protection_level(*_good_sky())
        assert isinstance(hpl, float)
        assert isinstance(vpl, float)

    def test_hpl_positive(self):
        r = AdvancedRAIM()
        hpl, _ = r.protection_level(*_good_sky())
        assert hpl > 0.0

    def test_vpl_positive(self):
        r = AdvancedRAIM()
        _, vpl = r.protection_level(*_good_sky())
        assert vpl > 0.0

    def test_check_alert_limits(self):
        r = AdvancedRAIM()
        assert r.check_alert_limits(10.0, 20.0, hal=40.0, val=50.0) is True
        assert r.check_alert_limits(50.0, 20.0, hal=40.0, val=50.0) is False

    def test_subset_test_shape_bool(self):
        r = AdvancedRAIM()
        az, el = _good_sky()
        flags = r.subset_test(az, el)
        assert flags.shape == (6,)
        assert flags.dtype == bool


# ============================================================================
# TiltCompensatedCompass
# ============================================================================

class TestTiltCompensatedCompass:
    def test_calibrate_sets_hard_iron(self):
        c = TiltCompensatedCompass()
        # 6 samples on a sphere centred at (1, 2, 3)
        offset = np.array([1.0, 2.0, 3.0])
        radii = np.array([5.0, 5.0, 5.0])
        samples = np.array([
            offset + radii * np.array([1, 0, 0]),
            offset + radii * np.array([-1, 0, 0]),
            offset + radii * np.array([0, 1, 0]),
            offset + radii * np.array([0, -1, 0]),
            offset + radii * np.array([0, 0, 1]),
            offset + radii * np.array([0, 0, -1]),
        ])
        c.calibrate(samples)
        assert np.allclose(c._hard_iron, offset)

    def test_calibrate_soft_iron_diagonal(self):
        c = TiltCompensatedCompass()
        offset = np.zeros(3)
        # Anisotropic radii so soft-iron is non-trivial
        samples = np.array([
            [10.0, 0.0, 0.0], [-10.0, 0.0, 0.0],
            [0.0, 5.0, 0.0], [0.0, -5.0, 0.0],
            [0.0, 0.0, 2.0], [0.0, 0.0, -2.0],
        ])
        c.calibrate(samples)
        # Diagonal should be (avg/r) per axis
        assert c._soft_iron.shape == (3, 3)
        off_diag = c._soft_iron - np.diag(np.diag(c._soft_iron))
        assert np.allclose(off_diag, 0.0)

    def test_correct_removes_hard_iron(self):
        c = TiltCompensatedCompass()
        c._hard_iron = np.array([10.0, -5.0, 3.0])
        c._soft_iron = np.eye(3)
        out = c.correct(np.array([10.0, -5.0, 3.0]))
        assert np.allclose(out, 0.0)

    def test_heading_in_range(self):
        c = TiltCompensatedCompass()
        h = c.heading(np.array([1.0, 0.0, 0.0]),
                      np.array([0.0, 0.0, 9.81]))
        assert 0.0 <= h < 360.0

    def test_heading_changes_with_tilt(self):
        c = TiltCompensatedCompass()
        # Use a mag vector with vertical component → tilt rotates it
        # into the horizontal plane and changes apparent heading.
        m = np.array([0.5, 0.5, -0.7])
        h1 = c.heading(m, np.array([0.0, 0.0, 9.81]))      # level
        h2 = c.heading(m, np.array([0.0, 4.0, 9.0]))       # rolled
        assert abs(h1 - h2) > 0.5

    def test_declination_correct_wraps(self):
        c = TiltCompensatedCompass()
        out = c.declination_correct(350.0, 20.0)
        assert out == pytest.approx(10.0)

    def test_heading_returns_float(self):
        c = TiltCompensatedCompass()
        h = c.heading(np.array([0.5, 0.5, 0.0]),
                      np.array([0.0, 0.0, 9.81]))
        assert isinstance(h, float)


# ============================================================================
# GraphSLAM
# ============================================================================

class TestGraphSLAM:
    def test_add_odometry_grows_poses(self):
        g = GraphSLAM()
        n0 = g.n_poses()
        g.add_odometry(np.array([1.0, 0.0, 0.0]), np.eye(3))
        assert g.n_poses() == n0 + 1

    def test_add_loop_closure_grows_edges(self):
        g = GraphSLAM()
        g.add_odometry(np.array([1.0, 0.0, 0.0]), np.eye(3))
        n_before = len(g._edges)
        g.add_loop_closure(0, 1, np.array([1.0, 0.0, 0.0]), np.eye(3))
        assert len(g._edges) == n_before + 1

    def test_optimize_returns_float(self):
        g = GraphSLAM()
        g.add_odometry(np.array([1.0, 0.0, 0.0]), np.eye(3))
        g.add_odometry(np.array([0.0, 1.0, 0.0]), np.eye(3))
        err = g.optimize(n_iter=3)
        assert isinstance(err, float)

    def test_optimize_reduces_error(self):
        g = GraphSLAM()
        for _ in range(5):
            g.add_odometry(np.array([1.0, 0.0, 0.0]), np.eye(3))
        # Inject a loop closure inconsistent with odometry to make it work
        g.add_loop_closure(0, 5, np.array([4.5, 0.2, 0.0]), np.eye(3) * 10)
        before = g._total_error()
        after = g.optimize(n_iter=10)
        assert after <= before + 1e-6

    def test_poses_shape(self):
        g = GraphSLAM()
        g.add_odometry(np.array([1.0, 0.0, 0.0]), np.eye(3))
        g.add_odometry(np.array([0.0, 1.0, 0.0]), np.eye(3))
        assert g.poses().shape == (3, 3)

    def test_n_poses_correct(self):
        g = GraphSLAM()
        for _ in range(4):
            g.add_odometry(np.array([0.5, 0.0, 0.0]), np.eye(3))
        assert g.n_poses() == 5

    def test_loop_closure_same_node_zero_error(self):
        g = GraphSLAM()
        g.add_odometry(np.array([1.0, 0.0, 0.0]), np.eye(3))
        # Loop closure between pose 1 and itself with z=0 → exact zero error
        g.add_loop_closure(1, 1, np.zeros(3), np.eye(3))
        # Per-edge error: e = z − (pj − pi) with i=j → e = z = 0
        e = g._error(g._poses[1], g._poses[1], np.zeros(3))
        assert np.allclose(e, 0.0)


# ============================================================================
# FadingMemoryFilter
# ============================================================================

class TestFadingMemoryFilter:
    def test_predict_inflates_P(self):
        f = FadingMemoryFilter(state_dim=2, obs_dim=1, fading_factor=1.5)
        f.P = np.eye(2)
        f.Q = np.zeros((2, 2))
        before = float(np.trace(f.P))
        f.predict()
        after = float(np.trace(f.P))
        assert after > before

    def test_predict_advances_state(self):
        f = FadingMemoryFilter(state_dim=2, obs_dim=1)
        F = np.array([[1.0, 1.0], [0.0, 1.0]])
        f.set_transition(F)
        f.x = np.array([0.0, 1.0])
        f.predict()
        assert f.x[0] == pytest.approx(1.0)

    def test_update_shape(self):
        f = FadingMemoryFilter(state_dim=2, obs_dim=1)
        f.update(np.array([2.0]))
        assert f.x.shape == (2,)

    def test_update_reduces_uncertainty(self):
        f = FadingMemoryFilter(state_dim=2, obs_dim=1)
        f.predict()
        before = float(np.trace(f.P))
        f.update(np.array([0.5]))
        after = float(np.trace(f.P))
        assert after < before

    def test_beta_one_degenerates(self):
        f = FadingMemoryFilter(state_dim=2, obs_dim=1, fading_factor=1.0)
        f.Q = np.zeros((2, 2))
        f.P = np.eye(2) * 1.0
        f.predict()
        assert np.allclose(f.P, np.eye(2) * 1.0)

    def test_innovation_value(self):
        f = FadingMemoryFilter(state_dim=2, obs_dim=1)
        f.x = np.array([3.0, 0.0])
        innov = f.innovation(np.array([5.0]))
        assert innov[0] == pytest.approx(2.0)

    def test_set_transition_stores(self):
        f = FadingMemoryFilter(state_dim=3)
        F = np.eye(3) * 0.5
        f.set_transition(F)
        assert np.allclose(f.F, F)


# ============================================================================
# SoundVelocityProfile
# ============================================================================

class TestSoundVelocityProfile:
    def test_mackenzie_surface(self):
        s = SoundVelocityProfile()
        c = s.mackenzie(25.0, 35.0, 0.0)
        assert abs(c - 1531.0) < 5.0

    def test_profile_at_depth_surface(self):
        s = SoundVelocityProfile()
        c = s.profile_at_depth(0.0)
        assert c > 1500.0

    def test_average_velocity_above_1400(self):
        s = SoundVelocityProfile()
        v = s.average_velocity(0.0, 100.0)
        assert v > 1400.0

    def test_tof_to_range_formula(self):
        s = SoundVelocityProfile()
        r = s.tof_to_range(1.0, avg_speed=1500.0)
        assert r == pytest.approx(1500.0)

    def test_snell_parallel(self):
        s = SoundVelocityProfile()
        out = s.snell_refraction(0.5, c1=1500.0, c2=1500.0)
        assert out == pytest.approx(0.5)

    def test_snell_total_internal_reflection(self):
        s = SoundVelocityProfile()
        out = s.snell_refraction(math.radians(80.0),
                                 c1=1500.0, c2=2500.0)
        assert math.isnan(out)

    def test_depth_interpolation_monotonic(self):
        s = SoundVelocityProfile()
        speeds = [s.profile_at_depth(d) for d in [0.0, 50.0, 100.0]]
        # Top 100m: temperature dropping → speed dropping
        assert speeds[0] >= speeds[2] - 1e-6
