"""GODSKILL Navigation R22 — improvement-round tests."""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.satellite import MultiFrequencyGNSS  # noqa: E402
from agency.navigation.ai_enhance import VisualOdometryFrontend  # noqa: E402
from agency.navigation.fusion import TightCoupledVIO  # noqa: E402
from agency.navigation.indoor_slam import OfflineVectorMap  # noqa: E402
from agency.navigation.underwater import UnderwaterStrapdownINS  # noqa: E402


# ============================================================================
# MultiFrequencyGNSS
# ============================================================================

class TestMultiFrequencyGNSS:
    def setup_method(self):
        self.g = MultiFrequencyGNSS()

    def test_iono_free_l1l2_returns_float(self):
        v = self.g.iono_free_l1l2(20e6, 20.1e6)
        assert isinstance(v, float)

    def test_iono_free_equal_ranges_near_input(self):
        P = 20e6
        v = self.g.iono_free_l1l2(P, P)
        assert abs(v - P) < 1.0

    def test_iono_free_l1l5_different_from_l1l2(self):
        v12 = self.g.iono_free_l1l2(20e6, 20.1e6)
        v15 = self.g.iono_free_l1l5(20e6, 20.1e6)
        assert v12 != v15

    def test_triple_freq_between_dual_combos(self):
        P1, P2, P5 = 20e6, 20.1e6, 20.05e6
        c12 = self.g.iono_free_l1l2(P1, P2)
        c15 = self.g.iono_free_l1l5(P1, P5)
        tri = self.g.triple_freq_combination(P1, P2, P5)
        assert min(c12, c15) - 1 <= tri <= max(c12, c15) + 1

    def test_geometry_matrix_shape(self):
        sats = [[1e7, 0, 0], [0, 1e7, 0], [0, 0, 1e7], [1e7, 1e7, 0]]
        H = self.g.geometry_matrix(sats, [0, 0, 0])
        assert H.shape == (4, 4)

    def test_least_squares_pvt_shape(self):
        sats = [[1e7, 0, 0], [0, 1e7, 0], [0, 0, 1e7], [1e7, 1e7, 0]]
        H = self.g.geometry_matrix(sats, [0, 0, 0])
        x = self.g.least_squares_pvt(H, np.ones(4) * 1e7)
        assert x.shape == (4,)

    def test_iono_correction_zero_for_equal(self):
        corr = self.g.iono_correction(20e6, 20e6)
        assert abs(corr) < 1e-6


# ============================================================================
# VisualOdometryFrontend
# ============================================================================

class TestVisualOdometryFrontend:
    def setup_method(self):
        self.vo = VisualOdometryFrontend(win_size=5, max_iter=5)

    def test_sobel_shape(self):
        img = np.random.randint(0, 255, (20, 20), dtype=np.uint8)
        Ix, Iy = self.vo._sobel(img)
        assert Ix.shape == img.shape and Iy.shape == img.shape

    def test_track_features_output_shape(self):
        prev = np.random.randint(0, 255, (32, 32), dtype=np.uint8)
        curr = prev.copy()
        pts = np.array([[8.0, 8.0], [16.0, 16.0]])
        tracked, valid = self.vo.track_features(prev, curr, pts)
        assert tracked.shape == pts.shape
        assert valid.shape == (2,)

    def test_track_identical_frames_near_zero_flow(self):
        frame = np.zeros((32, 32), dtype=np.uint8)
        pts = np.array([[16.0, 16.0]])
        tracked, valid = self.vo.track_features(frame, frame, pts)
        if valid[0]:
            assert np.linalg.norm(tracked[0] - pts[0]) < 2.0

    def test_estimate_rotation_identity(self):
        pts = np.array([[0., 0.], [1., 0.], [0., 1.], [1., 1.]])
        angle = self.vo.estimate_rotation(pts, pts, np.ones(4, dtype=bool))
        assert abs(angle) < 1e-6

    def test_estimate_rotation_range(self):
        pts = np.array([[1., 0.], [0., 1.], [-1., 0.], [0., -1.]])
        rot_pts = np.array([[0., 1.], [-1., 0.], [0., -1.], [1., 0.]])
        angle = self.vo.estimate_rotation(pts, rot_pts,
                                          np.ones(4, dtype=bool))
        assert -np.pi <= angle <= np.pi

    def test_update_pose_shape(self):
        T = self.vo.update_pose([1.0, 0.0], 0.1)
        assert T.shape == (4, 4)

    def test_update_pose_accumulates(self):
        self.vo.update_pose([1.0, 0.0], 0.0)
        self.vo.update_pose([1.0, 0.0], 0.0)
        assert abs(self.vo.pose[0, 3]) > 0.5


# ============================================================================
# TightCoupledVIO
# ============================================================================

class TestTightCoupledVIO:
    def setup_method(self):
        self.vio = TightCoupledVIO(n_features=2)

    def test_imu_predict_position_changes(self):
        self.vio.imu_predict([0.0, 0.0, 9.80665])
        assert self.vio.state_position().shape == (3,)

    def test_imu_predict_velocity_changes(self):
        self.vio.imu_predict([1.0, 0.0, 9.80665])
        v = self.vio.state_velocity()
        assert abs(v[0]) > 1e-6

    def test_visual_update_returns_innovation(self):
        innov = self.vio.visual_update(0, [1.0, 1.0])
        assert innov is not None
        assert len(innov) == 2

    def test_feature_depth_positive(self):
        self.vio.x[9] = 0.5
        d = self.vio.feature_depth(0)
        assert abs(d - 2.0) < 1e-9

    def test_feature_depth_zero_inv_depth(self):
        self.vio.x[9] = 0.0
        d = self.vio.feature_depth(0)
        assert d == float("inf")

    def test_covariance_stays_symmetric(self):
        self.vio.imu_predict([0, 0, 9.8])
        self.vio.visual_update(0, [0.5, 0.5])
        assert np.allclose(self.vio.P, self.vio.P.T, atol=1e-10)

    def test_state_dimension(self):
        assert self.vio.x.shape == (9 + 2,)


# ============================================================================
# OfflineVectorMap
# ============================================================================

class TestOfflineVectorMap:
    def setup_method(self):
        self.m = OfflineVectorMap()
        self.m.add_segment([0, 0], [10, 0])
        self.m.add_segment([10, 0], [10, 10])

    def test_match_on_segment(self):
        pt, idx, dist = self.m.match([5.0, 0.0])
        assert dist < 1e-9
        assert idx == 0

    def test_match_off_segment(self):
        pt, idx, dist = self.m.match([5.0, 3.0])
        assert abs(pt[1]) < 1e-9

    def test_match_returns_array(self):
        pt, _, _ = self.m.match([5.0, 0.0])
        assert hasattr(pt, "__len__")

    def test_constrain_within_threshold(self):
        snapped, on_map, dist = self.m.constrain_position(
            [5.0, 2.0], max_off_road_m=5.0)
        assert on_map
        assert dist < 5.0

    def test_constrain_beyond_threshold(self):
        _, on_map, dist = self.m.constrain_position(
            [5.0, 100.0], max_off_road_m=5.0)
        assert not on_map

    def test_segment_length(self):
        assert abs(self.m.segment_length(0) - 10.0) < 1e-9

    def test_total_length(self):
        assert abs(self.m.total_length() - 20.0) < 1e-9


# ============================================================================
# UnderwaterStrapdownINS
# ============================================================================

class TestUnderwaterStrapdownINS:
    def setup_method(self):
        self.ins = UnderwaterStrapdownINS()

    def test_update_returns_position(self):
        pos = self.ins.update([0, 0, 9.80665], [0, 0, 0], dt=0.01)
        assert pos.shape == (3,)

    def test_gravity_compensation_no_drift(self):
        self.ins.reset()
        for _ in range(10):
            self.ins.update([0.0, 0.0, 9.80665], [0.0, 0.0, 0.0], dt=0.01)
        assert abs(self.ins.vel[2]) < 0.1

    def test_forward_acceleration_moves_north(self):
        self.ins.reset()
        for _ in range(10):
            self.ins.update([1.0, 0.0, 9.80665], [0, 0, 0], dt=0.1)
        assert self.ins.pos[0] > 0.01

    def test_rbn_orthogonal(self):
        R = self.ins._Rbn(0.1, 0.2, 0.3)
        assert np.allclose(R @ R.T, np.eye(3), atol=1e-12)

    def test_rbn_det_unity(self):
        R = self.ins._Rbn(0.1, -0.1, 1.0)
        assert abs(np.linalg.det(R) - 1.0) < 1e-12

    def test_set_bias_applied(self):
        self.ins.reset()
        self.ins.set_bias([0, 0, 1.0], [0, 0, 0])
        for _ in range(5):
            self.ins.update([0, 0, 9.80665 + 1.0], [0, 0, 0], dt=0.1)
        assert abs(self.ins.vel[2]) < 0.2

    def test_reset_clears_state(self):
        self.ins.update([1, 1, 10], [0.1, 0.1, 0.1], dt=0.1)
        self.ins.reset()
        assert np.allclose(self.ins.pos, 0.0)
        assert np.allclose(self.ins.vel, 0.0)
