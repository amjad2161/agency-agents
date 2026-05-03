"""GODSKILL Navigation R19 — improvement-round tests."""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.satellite import CelestialNavigator  # noqa: E402
from agency.navigation.underground import RadioBeaconTriangulation  # noqa: E402
from agency.navigation.indoor_slam import LiDARSLAM  # noqa: E402
from agency.navigation.fusion import SchmidtKalmanFilter  # noqa: E402
from agency.navigation.underwater import BathymetricMapper  # noqa: E402


# ============================================================================
# CelestialNavigator
# ============================================================================

class TestCelestialNavigator:
    def test_sun_decl_summer(self):
        c = CelestialNavigator()
        # Day 172 ≈ June 21 (summer solstice, N hemisphere)
        d = c.sun_declination(172)
        assert d > 22.0

    def test_sun_decl_winter(self):
        c = CelestialNavigator()
        # Day 355 ≈ Dec 21 (winter solstice)
        d = c.sun_declination(355)
        assert d < -22.0

    def test_gha_sun_at_noon(self):
        c = CelestialNavigator()
        assert c.gha_sun(12.0) == pytest.approx(180.0)

    def test_intercept_returns_pair(self):
        c = CelestialNavigator()
        out = c.intercept_method(45.0, -75.0, 60.0, 23.0, 30.0)
        assert isinstance(out, tuple)
        assert len(out) == 2

    def test_two_body_fix_shape(self):
        c = CelestialNavigator()
        sights = [(60.0, 23.0, 30.0), (180.0, -10.0, 25.0)]
        out = c.two_body_fix(45.0, -75.0, sights)
        assert out.shape == (2,)

    def test_altitude_correction_reduces(self):
        c = CelestialNavigator()
        out = c.altitude_correction(30.0, dip_arcmin=2.0, refraction=True)
        assert out < 30.0

    def test_intercept_azimuth_in_range(self):
        c = CelestialNavigator()
        _, az = c.intercept_method(45.0, -75.0, 60.0, 23.0, 30.0)
        assert 0.0 <= az < 360.0


# ============================================================================
# RadioBeaconTriangulation
# ============================================================================

def _beacons():
    return np.array([
        [0.0, 0.0],
        [10.0, 0.0],
        [0.0, 10.0],
        [10.0, 10.0],
    ])


class TestRadioBeaconTriangulation:
    def test_rssi_at_1m(self):
        t = RadioBeaconTriangulation(_beacons())
        # tx_power=20, rssi=20 → distance=1m
        d = t.rssi_to_distance(20.0, tx_power_dbm=20.0)
        assert d == pytest.approx(1.0)

    def test_trilaterate_shape(self):
        t = RadioBeaconTriangulation(_beacons())
        true = np.array([3.0, 4.0])
        d = np.linalg.norm(_beacons() - true, axis=1)
        out = t.trilaterate(d)
        assert out.shape == (2,)

    def test_trilaterate_noiseless_error(self):
        t = RadioBeaconTriangulation(_beacons())
        true = np.array([3.0, 4.0])
        d = np.linalg.norm(_beacons() - true, axis=1)
        out = t.trilaterate(d)
        err = float(np.linalg.norm(out - true))
        assert err < 1.0

    def test_tdoa_locate_shape(self):
        t = RadioBeaconTriangulation(_beacons())
        # 3 TDOA values for 4 beacons (relative to b0)
        out = t.tdoa_locate(np.array([1.0, 2.0, 3.0]))
        assert out.shape == (2,)

    def test_bearing_from_rssi_returns_float(self):
        t = RadioBeaconTriangulation(_beacons())
        out = t.bearing_from_rssi(np.array([-80.0, -50.0, -90.0, -85.0]))
        assert isinstance(out, float)

    def test_wavelength_stored(self):
        t = RadioBeaconTriangulation(_beacons(), freq_mhz=433.0)
        assert t._lambda == pytest.approx(299.792458 / 433.0)

    def test_beacons_shape_preserved(self):
        b = _beacons()
        t = RadioBeaconTriangulation(b)
        assert t.beacons.shape == b.shape


# ============================================================================
# LiDARSLAM
# ============================================================================

class TestLiDARSLAM:
    def test_scan_to_points_shape(self):
        s = LiDARSLAM()
        pts = s.scan_to_points(np.array([1.0, 2.0, 3.0]),
                               np.array([0.0, math.pi / 2, math.pi]))
        assert pts.shape == (3, 2)

    def test_scan_to_points_at_zero_angle(self):
        s = LiDARSLAM()
        pts = s.scan_to_points(np.array([5.0]), np.array([0.0]))
        assert pts[0, 0] == pytest.approx(5.0)
        assert pts[0, 1] == pytest.approx(0.0)

    def test_update_map_changes_log_odds(self):
        s = LiDARSLAM()
        before = float(np.sum(np.abs(s.log_odds)))
        pts = np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]])
        s.update_map(pts)
        after = float(np.sum(np.abs(s.log_odds)))
        assert after > before

    def test_scan_match_returns_pose(self):
        s = LiDARSLAM()
        body_pts = np.array([[1.0, 0.0], [0.0, 1.0]])
        pose = s.scan_match(body_pts, n_iter=5)
        assert pose.shape == (3,)

    def test_process_scan_increments(self):
        s = LiDARSLAM()
        before = s.scan_count
        s.process_scan(np.array([1.0, 2.0]),
                       np.array([0.0, math.pi / 2]))
        assert s.scan_count == before + 1

    def test_probability_map_in_unit_interval(self):
        s = LiDARSLAM()
        s.update_map(np.array([[1.0, 0.0]]))
        p = s.probability_map()
        assert np.all(p >= 0.0) and np.all(p <= 1.0)

    def test_map_size_preserved(self):
        s = LiDARSLAM(map_size=80)
        assert s.log_odds.shape == (80, 80)


# ============================================================================
# SchmidtKalmanFilter
# ============================================================================

class TestSchmidtKalmanFilter:
    def test_predict_advances_state(self):
        kf = SchmidtKalmanFilter(est_dim=2, con_dim=1)
        kf.x = np.array([1.0, 0.0, 5.0])
        F = np.eye(3); F[0, 1] = 1.0
        Q = np.eye(3) * 0.01
        kf.predict(F, Q)
        assert kf.x[0] == pytest.approx(1.0)

    def test_predict_grows_P(self):
        kf = SchmidtKalmanFilter(est_dim=2, con_dim=1)
        before = float(np.trace(kf.P))
        kf.predict(np.eye(3), np.eye(3) * 0.5)
        after = float(np.trace(kf.P))
        assert after > before

    def test_update_estimated_state_shape(self):
        kf = SchmidtKalmanFilter(est_dim=2, con_dim=1)
        H = np.array([[1.0, 0.0, 0.0]])
        R = np.eye(1)
        out = kf.update(np.array([2.0]), H, R)
        assert out.shape == (2,)

    def test_update_only_changes_estimated(self):
        kf = SchmidtKalmanFilter(est_dim=2, con_dim=1)
        kf.x = np.array([0.0, 0.0, 5.0])
        H = np.array([[1.0, 0.0, 0.0]])
        R = np.eye(1)
        kf.update(np.array([10.0]), H, R)
        # Consider state must be untouched
        assert kf.x[2] == pytest.approx(5.0)

    def test_consider_covariance_shape(self):
        kf = SchmidtKalmanFilter(est_dim=2, con_dim=3)
        assert kf.consider_covariance().shape == (3, 3)

    def test_estimated_state_shape(self):
        kf = SchmidtKalmanFilter(est_dim=4, con_dim=2)
        assert kf.estimated_state().shape == (4,)

    def test_full_P_symmetric_after_update(self):
        kf = SchmidtKalmanFilter(est_dim=2, con_dim=1)
        H = np.array([[1.0, 0.0, 0.0]])
        kf.update(np.array([1.0]), H, np.eye(1))
        assert np.allclose(kf.P, kf.P.T, atol=1e-9)


# ============================================================================
# BathymetricMapper
# ============================================================================

class TestBathymetricMapper:
    def test_add_ping_stores(self):
        m = BathymetricMapper(grid_size=20, resolution=1.0)
        m.add_ping(0.0, 0.0, 50.0)
        assert m.depth_at(0.0, 0.0) == pytest.approx(50.0)

    def test_ping_count_increments(self):
        m = BathymetricMapper(grid_size=20)
        before = m.ping_count
        m.add_ping(0.0, 0.0, 100.0)
        assert m.ping_count == before + 1

    def test_depth_at_returns_stored(self):
        m = BathymetricMapper(grid_size=20, resolution=1.0)
        m.add_ping(2.0, 3.0, 75.0)
        assert m.depth_at(2.0, 3.0) == pytest.approx(75.0)

    def test_depth_at_unmapped_nan(self):
        m = BathymetricMapper(grid_size=20)
        v = m.depth_at(50.0, 50.0)
        assert math.isnan(v)

    def test_match_profile_shape(self):
        m = BathymetricMapper(grid_size=20, resolution=1.0)
        m.add_ping(0.0, 0.0, 50.0)
        out = m.match_profile(np.array([[0.0, 0.0]]), np.array([50.0]))
        assert out.shape == (2,)

    def test_coverage_increases(self):
        m = BathymetricMapper(grid_size=20, resolution=1.0)
        c0 = m.coverage_fraction()
        for k in range(5):
            m.add_ping(float(k), 0.0, 50.0 + k)
        assert m.coverage_fraction() > c0

    def test_depth_stats_returns_pair(self):
        m = BathymetricMapper(grid_size=20, resolution=1.0)
        for k in range(5):
            m.add_ping(float(k), 0.0, 100.0 + k * 10.0)
        mean, std = m.depth_stats()
        assert isinstance(mean, float)
        assert isinstance(std, float)
        assert std > 0.0
