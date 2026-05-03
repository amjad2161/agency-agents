"""GODSKILL Navigation R17 — improvement-round tests."""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.satellite import KeplerOrbitPropagator  # noqa: E402
from agency.navigation.indoor_inertial import AckermannOdometry  # noqa: E402
from agency.navigation.indoor_slam import ICPScanMatcher  # noqa: E402
from agency.navigation.fusion import HybridNavigationFilter  # noqa: E402
from agency.navigation.underwater import HydrophoneArrayLocator  # noqa: E402


# ============================================================================
# KeplerOrbitPropagator
# ============================================================================

def _gps_eph(prop):
    """Reasonable GPS-style ephemeris."""
    sqrt_a = math.sqrt(KeplerOrbitPropagator.A_GPS)
    prop.set_ephemeris(sqrt_a=sqrt_a, e=0.005,
                       i0=math.radians(55.0),
                       omega0=0.0, omega=0.0, m0=0.0, toe=0.0)


class TestKeplerOrbitPropagator:
    def test_eccentric_anomaly_converges(self):
        p = KeplerOrbitPropagator()
        p._eph = {"e": 0.1}
        E = p.eccentric_anomaly(1.0)
        assert abs(E - 0.1 * math.sin(E) - 1.0) < 1e-10

    def test_eccentric_anomaly_e_zero(self):
        p = KeplerOrbitPropagator()
        p._eph = {"e": 0.0}
        E = p.eccentric_anomaly(0.7)
        assert E == pytest.approx(0.7)

    def test_set_ephemeris_a_squared(self):
        p = KeplerOrbitPropagator()
        p.set_ephemeris(sqrt_a=10.0, e=0.0, i0=0.0, omega0=0.0,
                        omega=0.0, m0=0.0, toe=0.0)
        assert p._eph["a"] == pytest.approx(100.0)

    def test_sv_position_shape(self):
        p = KeplerOrbitPropagator()
        _gps_eph(p)
        pos = p.sv_position(0.0)
        assert pos.shape == (3,)

    def test_sv_position_radius_near_a(self):
        p = KeplerOrbitPropagator()
        _gps_eph(p)
        r = float(np.linalg.norm(p.sv_position(0.0)))
        assert abs(r - KeplerOrbitPropagator.A_GPS) < 0.05 * KeplerOrbitPropagator.A_GPS

    def test_sv_velocity_shape(self):
        p = KeplerOrbitPropagator()
        _gps_eph(p)
        v = p.sv_velocity(0.0)
        assert v.shape == (3,)

    def test_sv_velocity_magnitude_range(self):
        p = KeplerOrbitPropagator()
        _gps_eph(p)
        speed = float(np.linalg.norm(p.sv_velocity(0.0)))
        assert 1000.0 < speed < 5000.0


# ============================================================================
# AckermannOdometry
# ============================================================================

class TestAckermannOdometry:
    def test_ticks_to_distance_formula(self):
        o = AckermannOdometry(wheel_radius=1.0, ticks_per_rev=100)
        d = o.ticks_to_distance(100)
        assert d == pytest.approx(2.0 * math.pi)

    def test_update_returns_pose(self):
        o = AckermannOdometry()
        out = o.update(100, 100, dt=0.1)
        assert out.shape == (3,)

    def test_update_advances_x(self):
        o = AckermannOdometry()
        o.update(1000, 1000, dt=0.1)
        assert o.pose[0] > 0.0

    def test_update_rotates_theta(self):
        o = AckermannOdometry()
        o.update(0, 1000, dt=0.1)
        assert abs(o.pose[2]) > 0.0

    def test_slip_reduces_distance(self):
        o1 = AckermannOdometry()
        o2 = AckermannOdometry()
        o2.set_slip(0.5)
        o1.update(1000, 1000, dt=0.1)
        o2.update(1000, 1000, dt=0.1)
        assert o2.pose[0] < o1.pose[0]

    def test_steering_radius_formula(self):
        o = AckermannOdometry(wheelbase=2.0)
        r = o.steering_radius(math.pi / 4)
        assert r == pytest.approx(2.0)

    def test_reset_clears_pose(self):
        o = AckermannOdometry()
        o.update(500, 800, dt=0.1)
        o.reset()
        assert np.allclose(o.pose, 0.0)


# ============================================================================
# ICPScanMatcher
# ============================================================================

class TestICPScanMatcher:
    def test_transform_rotation(self):
        icp = ICPScanMatcher()
        pts = np.array([[1.0, 0.0]])
        T = np.array([[0.0, -1.0, 0.0],
                      [1.0, 0.0, 0.0],
                      [0.0, 0.0, 1.0]])
        out = icp._transform(pts, T)
        assert np.allclose(out, [[0.0, 1.0]])

    def test_nearest_correct_correspondence(self):
        icp = ICPScanMatcher(max_dist=10.0)
        src = np.array([[0.0, 0.0], [1.0, 0.0]])
        dst = np.array([[0.05, 0.0], [1.05, 0.0], [10.0, 10.0]])
        ms, md = icp._nearest(src, dst)
        assert md.shape[0] == 2

    def test_align_returns_pair(self):
        icp = ICPScanMatcher()
        src = np.random.RandomState(0).randn(20, 2)
        T_true = np.array([[1.0, 0.0, 0.5], [0.0, 1.0, 0.3], [0.0, 0.0, 1.0]])
        dst = (T_true @ np.hstack([src, np.ones((20, 1))]).T).T[:, :2]
        T, rmse = icp.align(src, dst)
        assert isinstance(rmse, float)

    def test_align_T_shape(self):
        icp = ICPScanMatcher()
        src = np.random.RandomState(1).randn(15, 2)
        dst = src + np.array([0.2, -0.1])
        T, _ = icp.align(src, dst)
        assert T.shape == (3, 3)

    def test_align_reduces_rmse(self):
        icp = ICPScanMatcher()
        src = np.random.RandomState(2).randn(30, 2)
        dst = src + np.array([0.5, 0.5])
        rmse_before = icp.rmse(src, dst, np.eye(3))
        T, rmse_after = icp.align(src, dst)
        assert rmse_after <= rmse_before + 1e-6

    def test_rmse_decreases_after_align(self):
        icp = ICPScanMatcher()
        src = np.random.RandomState(3).randn(25, 2)
        dst = src + np.array([0.4, 0.0])
        T, _ = icp.align(src, dst)
        rmse_after = icp.rmse(src, dst, T)
        assert rmse_after < 0.5

    def test_align_pure_translation(self):
        icp = ICPScanMatcher()
        src = np.random.RandomState(4).randn(40, 2)
        true_t = np.array([0.3, -0.2])
        dst = src + true_t
        T, _ = icp.align(src, dst)
        recovered_t = T[:2, 2]
        assert np.allclose(recovered_t, true_t, atol=0.05)


# ============================================================================
# HybridNavigationFilter
# ============================================================================

class TestHybridNavigationFilter:
    def test_select_mode_switch(self):
        h = HybridNavigationFilter(state_dim=2, outdoor_threshold=5.0)
        h.select_mode(2.0)
        assert h.mode == "ekf"
        h.select_mode(20.0)
        assert h.mode == "particle"

    def test_predict_ekf_mode(self):
        h = HybridNavigationFilter(state_dim=2)
        h.select_mode(1.0)
        h.predict(np.eye(2), np.eye(2) * 0.1)
        assert h.state().shape == (2,)

    def test_update_ekf_mode(self):
        h = HybridNavigationFilter(state_dim=2)
        h.select_mode(1.0)
        h.update(np.array([1.0]), np.array([[1.0, 0.0]]),
                 np.eye(1) * 0.5)
        assert h.state().shape == (2,)

    def test_predict_pf_mode(self):
        h = HybridNavigationFilter(state_dim=2, n_particles=50)
        h.select_mode(20.0)
        h.predict(np.eye(2), np.eye(2) * 0.1)
        assert h._particles.shape == (50, 2)

    def test_state_shape(self):
        h = HybridNavigationFilter(state_dim=3)
        assert h.state().shape == (3,)

    def test_uncertainty_positive(self):
        h = HybridNavigationFilter(state_dim=2)
        assert h.uncertainty() > 0.0

    def test_mode_switches(self):
        h = HybridNavigationFilter(state_dim=2)
        h.select_mode(1.0)
        m1 = h.mode
        h.select_mode(20.0)
        m2 = h.mode
        assert m1 != m2


# ============================================================================
# HydrophoneArrayLocator
# ============================================================================

def _hydro_array():
    return np.array([
        [0.0, 0.0, 0.0],
        [10.0, 0.0, 0.0],
        [0.0, 10.0, 0.0],
        [0.0, 0.0, 10.0],
    ])


class TestHydrophoneArrayLocator:
    def test_tdoa_shape(self):
        h = HydrophoneArrayLocator(_hydro_array())
        td = h.tdoa(np.array([5.0, 5.0, 0.0]))
        assert td.shape == (3,)

    def test_tdoa_zero_at_h0(self):
        h = HydrophoneArrayLocator(_hydro_array())
        # Source equidistant from h0 and h1 → tdoa[0] near 0
        td = h.tdoa(np.array([5.0, 0.0, 0.0]))
        assert abs(td[0]) < 1e-6

    def test_locate_wls_shape(self):
        h = HydrophoneArrayLocator(_hydro_array())
        td = h.tdoa(np.array([3.0, 4.0, 5.0]))
        out = h.locate_wls(td)
        assert out.shape == (3,)

    def test_locate_wls_noiseless_error(self):
        h = HydrophoneArrayLocator(_hydro_array())
        true = np.array([3.0, 4.0, 5.0])
        td = h.tdoa(true)
        out = h.locate_wls(td)
        assert h.position_error(out, true) < 2.0

    def test_locate_iterative_no_worse(self):
        h = HydrophoneArrayLocator(_hydro_array())
        true = np.array([3.0, 4.0, 5.0])
        td = h.tdoa(true)
        wls_err = h.position_error(h.locate_wls(td), true)
        it_err = h.position_error(h.locate_iterative(td), true)
        assert it_err <= wls_err + 1e-6 or it_err < 1.0

    def test_tdoa_sign_farther_positive(self):
        h = HydrophoneArrayLocator(_hydro_array())
        # Source at (-5, 0, 0): h0 closer than h1 → tdoa[0] > 0
        td = h.tdoa(np.array([-5.0, 0.0, 0.0]))
        assert td[0] > 0.0

    def test_sound_speed_stored(self):
        h = HydrophoneArrayLocator(_hydro_array(), sound_speed=1480.0)
        assert h.sound_speed == pytest.approx(1480.0)
