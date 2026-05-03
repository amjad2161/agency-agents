"""GODSKILL Navigation R24 — improvement-round tests."""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.satellite import QZSSReceiver  # noqa: E402
from agency.navigation.indoor_inertial import ZUPTVelocityAider  # noqa: E402
from agency.navigation.underwater import AcousticDopplerCurrentProfiler  # noqa: E402
from agency.navigation.fusion import IteratedEKF  # noqa: E402
from agency.navigation.ai_enhance import MapBasedLaneEstimator  # noqa: E402


# ============================================================================
# QZSSReceiver
# ============================================================================

class TestQZSSReceiver:
    def setup_method(self):
        self.r = QZSSReceiver()
        self.r.add_satellite(193, [0, 0, 42164e3], health=True)
        self.r.add_satellite(194, [30000e3, 0, 30000e3], health=False)

    def test_corrected_pseudorange_no_correction(self):
        pr = self.r.corrected_pseudorange(193, 40000e3)
        assert abs(pr - 40000e3) < 1.0

    def test_corrected_pseudorange_with_correction(self):
        self.r.add_sbas_correction(193, -5.0)
        pr = self.r.corrected_pseudorange(193, 40000e3)
        assert abs(pr - (40000e3 - 5.0)) < 1e-9

    def test_elevation_mask_excludes_unhealthy(self):
        visible = self.r.elevation_mask([0, 0, 0])
        assert 194 not in visible

    def test_elevation_mask_high_sat_visible(self):
        visible = self.r.elevation_mask([0, 0, 0])
        assert 193 in visible

    def test_lex_clock_correction_scales(self):
        c = self.r.lex_clock_correction(193, 10.0)
        assert abs(c - 9.5) < 1e-9

    def test_dop_finite_with_enough_sats(self):
        for i, pos in enumerate([[20000e3, 0, 20000e3],
                                 [0, 20000e3, 20000e3],
                                 [-20000e3, 0, 20000e3]]):
            self.r.add_satellite(200 + i, pos, health=True)
        dop = self.r.dop_from_visible([0, 0, 0])
        assert np.isfinite(dop)

    def test_dop_inf_with_too_few_sats(self):
        r = QZSSReceiver()
        r.add_satellite(1, [0, 0, 36000e3], health=True)
        dop = r.dop_from_visible([0, 0, 0])
        assert dop == float("inf")


# ============================================================================
# ZUPTVelocityAider
# ============================================================================

class TestZUPTVelocityAider:
    def setup_method(self):
        self.z = ZUPTVelocityAider(accel_threshold=0.1,
                                   gyro_threshold=0.05, window=5)

    def test_not_stationary_empty_buffer(self):
        assert not self.z.is_stationary()

    def test_stationary_with_constant_samples(self):
        for _ in range(6):
            self.z.push_sample([0, 0, 9.8], [0, 0, 0])
        assert self.z.is_stationary()

    def test_not_stationary_with_varying_samples(self):
        for i in range(6):
            self.z.push_sample([0, 0, 9.8 + i * 0.5],
                               [0, 0, i * 0.1])
        assert not self.z.is_stationary()

    def test_predict_velocity_integrates(self):
        v = self.z.predict_velocity([1.0, 0.0, 0.0], dt=0.1)
        assert abs(v[0]) > 0

    def test_zupt_zeroes_velocity(self):
        self.z.velocity = np.array([1.0, 2.0, 3.0])
        for _ in range(6):
            self.z.push_sample([0, 0, 9.8], [0, 0, 0])
        self.z.apply_zupt()
        assert np.linalg.norm(self.z.velocity) < 0.1

    def test_step_returns_tuple(self):
        result = self.z.step([0, 0, 9.8], [0, 0, 0],
                             [0, 0, 0], 0.01)
        assert len(result) == 2

    def test_covariance_positive_after_zupt(self):
        self.z.velocity[:] = 1.0
        self.z.apply_zupt()
        assert np.all(np.linalg.eigvalsh(self.z.P_vel) > 0)


# ============================================================================
# AcousticDopplerCurrentProfiler
# ============================================================================

class TestAcousticDopplerCurrentProfiler:
    def setup_method(self):
        self.adcp = AcousticDopplerCurrentProfiler(n_bins=5,
                                                   bin_size_m=2.0,
                                                   beam_angle_deg=20.0)

    def test_doppler_to_velocity_zero_shift(self):
        v = self.adcp.doppler_to_velocity(0.0, 300e3)
        assert abs(v) < 1e-9

    def test_doppler_to_velocity_positive(self):
        v = self.adcp.doppler_to_velocity(100.0, 300e3)
        assert v > 0

    def test_process_beam_shape(self):
        shifts = np.ones(5) * 50.0
        profile = self.adcp.process_beam(shifts, 300e3)
        assert profile.shape == (5,)

    def test_add_profile_stores(self):
        self.adcp.add_profile(5.0, [0.3, 0.1, 0.0])
        assert len(self.adcp.profiles) == 1

    def test_mean_current_empty(self):
        mc = self.adcp.mean_current()
        assert np.allclose(mc, 0.0)

    def test_mean_current_with_profiles(self):
        self.adcp.add_profile(2.0, [1.0, 0.0, 0.0])
        self.adcp.add_profile(4.0, [3.0, 0.0, 0.0])
        mc = self.adcp.mean_current()
        assert abs(mc[0] - 2.0) < 1e-9

    def test_bottom_track_velocity_shape(self):
        shifts = [10.0, -10.0, 10.0, -10.0]
        v = self.adcp.bottom_track_velocity(shifts, 300e3)
        assert v.shape == (4,)


# ============================================================================
# IteratedEKF
# ============================================================================

class TestIteratedEKF:
    def setup_method(self):
        self.ekf = IteratedEKF(dim_x=3, dim_z=2, n_iter=3)

    def test_predict_shape(self):
        x = self.ekf.predict()
        assert x.shape == (3,)

    def test_update_returns_state_and_innov(self):
        H = np.array([[1, 0, 0], [0, 1, 0]])
        R = np.eye(2) * 0.1
        x, innov = self.ekf.update([1.0, 2.0], H, R)
        assert x.shape == (3,)
        assert innov.shape == (2,)

    def test_update_moves_toward_measurement(self):
        H = np.array([[1, 0, 0], [0, 1, 0]])
        R = np.eye(2) * 0.01
        x, _ = self.ekf.update([1.0, 0.0], H, R)
        assert x[0] > 0.5

    def test_innovation_covariance_shape(self):
        H = np.array([[1, 0, 0], [0, 1, 0]])
        S = self.ekf.innovation_covariance(H, np.eye(2) * 0.1)
        assert S.shape == (2, 2)

    def test_mahalanobis_nonneg(self):
        H = np.array([[1, 0, 0], [0, 1, 0]])
        d = self.ekf.mahalanobis_distance([0.0, 0.0], H,
                                          np.eye(2) * 0.1)
        assert d >= 0

    def test_covariance_symmetric_after_update(self):
        H = np.array([[1, 0, 0], [0, 1, 0]])
        self.ekf.update([1.0, 0.5], H, np.eye(2) * 0.1)
        assert np.allclose(self.ekf.P, self.ekf.P.T, atol=1e-10)

    def test_n_iter_one_equals_standard_ekf(self):
        ekf1 = IteratedEKF(3, 2, n_iter=1)
        ekf2 = IteratedEKF(3, 2, n_iter=1)
        H = np.array([[1, 0, 0], [0, 1, 0]])
        R = np.eye(2) * 0.1
        x1, _ = ekf1.update([1.0, 0.0], H, R)
        x2, _ = ekf2.update([1.0, 0.0], H, R)
        np.testing.assert_allclose(x1, x2, atol=1e-12)


# ============================================================================
# MapBasedLaneEstimator
# ============================================================================

class TestMapBasedLaneEstimator:
    def setup_method(self):
        self.est = MapBasedLaneEstimator(lane_width_m=3.5)
        self.est.add_lane(0, [0.0, 0.0], 0.0)
        self.est.add_lane(1, [0.0, 3.5], 0.0)

    def test_assign_lane_correct(self):
        lane, d = self.est.assign_lane([0.0, 0.5])
        assert lane["id"] == 0

    def test_lateral_distance_centre_is_zero(self):
        lat = self.est._lateral_distance(self.est.lanes[0], [0.0, 0.0])
        assert abs(lat) < 1e-9

    def test_lateral_distance_offset(self):
        lat = self.est._lateral_distance(self.est.lanes[0], [0.0, 1.0])
        assert abs(abs(lat) - 1.0) < 1e-9

    def test_in_lane_bounds_centre(self):
        assert self.est.in_lane_bounds([0.0, 0.0])

    def test_in_lane_bounds_outside(self):
        # y=10 is well outside both lanes (centres at y=0 and y=3.5, half-width 1.75)
        assert not self.est.in_lane_bounds([0.0, 10.0])

    def test_lane_constrained_snaps_to_centre(self):
        snapped = self.est.lane_constrained_position([0.0, 0.5])
        assert abs(snapped[1]) < 1e-9

    def test_lane_constrained_no_snap_outside(self):
        raw = np.array([0.0, 10.0])
        snapped = self.est.lane_constrained_position(raw)
        assert np.allclose(snapped, raw)
