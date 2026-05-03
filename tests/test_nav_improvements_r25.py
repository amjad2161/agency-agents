"""GODSKILL Navigation R25 — improvement-round tests."""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.satellite import BeiDouReceiver  # noqa: E402
from agency.navigation.indoor_inertial import MagneticCompassCalibration  # noqa: E402
from agency.navigation.indoor_slam import LiDARIntensityMapper  # noqa: E402
from agency.navigation.fusion import UnscentedRTS  # noqa: E402
from agency.navigation.ai_enhance import NeuralOdometryRegressor  # noqa: E402


# ============================================================================
# BeiDouReceiver
# ============================================================================

class TestBeiDouReceiver:
    def setup_method(self):
        self.r = BeiDouReceiver()
        self.r.add_satellite(1, [20000e3, 0, 20000e3], orbit_type="MEO")
        self.r.add_satellite(2, [0, 20000e3, 20000e3], orbit_type="MEO")
        self.r.add_satellite(3, [0, 0, 36000e3], orbit_type="GEO")
        self.r.add_satellite(4, [-20000e3, 0, 20000e3],
                             orbit_type="MEO", health=False)

    def test_corrected_pseudorange_no_corr(self):
        pr = self.r.corrected_pseudorange(1, 25000e3)
        assert abs(pr - 25000e3) < 1.0

    def test_bdsbas_correction_applied(self):
        self.r.bdsbas_correction(1, -3.0)
        pr = self.r.corrected_pseudorange(1, 25000e3)
        assert abs(pr - (25000e3 - 3.0)) < 1e-9

    def test_elevation_mask_excludes_unhealthy(self):
        v = self.r.elevation_mask([0, 0, 0])
        assert 4 not in v

    def test_elevation_mask_includes_healthy(self):
        v = self.r.elevation_mask([0, 0, 0])
        assert 1 in v

    def test_iono_free_combo_returns_float(self):
        v = self.r.iono_free_B1C_B2A(25000e3, 25000.1e3)
        assert isinstance(v, float)

    def test_pdop_meo_only_finite(self):
        # Add 2 more MEO sats so MEO count >= 4
        self.r.add_satellite(5, [10000e3, 10000e3, 18000e3],
                             orbit_type="MEO")
        self.r.add_satellite(6, [-10000e3, 10000e3, 18000e3],
                             orbit_type="MEO")
        dop = self.r.pdop_meo_only([0, 0, 0])
        assert np.isfinite(dop) and dop != 999.0

    def test_pdop_meo_only_returns_999_too_few(self):
        r = BeiDouReceiver()
        r.add_satellite(1, [20000e3, 0, 20000e3], orbit_type="MEO")
        r.add_satellite(2, [0, 0, 36000e3], orbit_type="GEO")
        dop = r.pdop_meo_only([0, 0, 0])
        assert dop == 999.0


# ============================================================================
# MagneticCompassCalibration
# ============================================================================

class TestMagneticCompassCalibration:
    def setup_method(self):
        self.c = MagneticCompassCalibration()

    def test_add_sample_grows(self):
        self.c.add_sample([1, 2, 3])
        assert len(self.c._samples) == 1

    def test_fit_ellipsoid_centre_at_mean(self):
        for v in [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0],
                  [0, 0, 1], [0, 0, -1]]:
            self.c.add_sample(np.array(v) + np.array([5.0, 3.0, 2.0]))
        centre, _ = self.c.fit_ellipsoid()
        assert np.allclose(centre, [5.0, 3.0, 2.0], atol=1e-9)

    def test_fit_ellipsoid_returns_pair(self):
        self.c.add_sample([1, 0, 0]); self.c.add_sample([-1, 0, 0])
        out = self.c.fit_ellipsoid()
        assert len(out) == 2

    def test_calibrate_centre_to_zero(self):
        for v in [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0],
                  [0, 0, 1], [0, 0, -1]]:
            self.c.add_sample(v)
        self.c.fit_ellipsoid()
        out = self.c.calibrate([0.0, 0.0, 0.0])
        assert np.allclose(out, 0.0, atol=1e-9)

    def test_heading_returns_float(self):
        self.c._centre = np.zeros(3)
        self.c._scale = np.ones(3)
        h = self.c.heading([1.0, 0.0, 0.0])
        assert isinstance(h, float)

    def test_heading_zero_for_x_axis(self):
        self.c._centre = np.zeros(3)
        self.c._scale = np.ones(3)
        assert abs(self.c.heading([1.0, 0.0, 0.0])) < 1e-9

    def test_quality_in_unit_interval(self):
        for v in [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0],
                  [0, 0, 1], [0, 0, -1]]:
            self.c.add_sample(v)
        q = self.c.quality()
        assert 0.0 <= q <= 1.0


# ============================================================================
# LiDARIntensityMapper
# ============================================================================

class TestLiDARIntensityMapper:
    def setup_method(self):
        self.m = LiDARIntensityMapper(intensity_threshold=50.0)
        pts = np.array([[0, 0], [1, 0], [2, 0], [3, 0]], dtype=float)
        ints = np.array([20.0, 80.0, 90.0, 30.0])
        self.m.add_scan(pts, ints)

    def test_extract_features_filters(self):
        f = self.m.extract_features(0)
        assert f.shape == (2, 2)

    def test_intensity_histogram_shape(self):
        counts, edges = self.m.intensity_histogram(0, bins=4)
        assert len(counts) == 4
        assert len(edges) == 5

    def test_match_scans_self(self):
        cnt = self.m.match_scans(0, 0)
        assert cnt == 2

    def test_match_scans_far_apart(self):
        pts2 = np.array([[100, 100], [101, 100]], dtype=float)
        ints2 = np.array([90.0, 90.0])
        self.m.add_scan(pts2, ints2)
        cnt = self.m.match_scans(0, 1)
        assert cnt == 0

    def test_dominant_intensity_positive(self):
        d = self.m.dominant_intensity(0)
        assert d > 50.0

    def test_dominant_intensity_zero_when_none(self):
        m = LiDARIntensityMapper(intensity_threshold=200.0)
        m.add_scan(np.array([[0, 0]], dtype=float), np.array([10.0]))
        assert m.dominant_intensity(0) == 0.0

    def test_add_scan_grows(self):
        before = len(self.m._scans)
        self.m.add_scan(np.array([[5, 5]], dtype=float),
                        np.array([60.0]))
        assert len(self.m._scans) == before + 1


# ============================================================================
# UnscentedRTS
# ============================================================================

class TestUnscentedRTS:
    def setup_method(self):
        self.urts = UnscentedRTS(dim=2)

    def test_sigma_points_count(self):
        sigmas = self.urts.sigma_points(np.zeros(2), np.eye(2))
        assert sigmas.shape == (5, 2)

    def test_sigma_first_point_is_mean(self):
        sigmas = self.urts.sigma_points(np.array([1.0, 2.0]), np.eye(2))
        assert np.allclose(sigmas[0], [1.0, 2.0])

    def test_predict_returns_triple(self):
        x_p, P_p, Pxy = self.urts.predict(
            np.zeros(2), np.eye(2),
            f=lambda s: s + np.array([1.0, 0.0]),
            Q=np.eye(2) * 0.1,
        )
        assert x_p.shape == (2,)
        assert P_p.shape == (2, 2)
        assert Pxy.shape == (2, 2)

    def test_predict_mean_advances(self):
        x_p, _, _ = self.urts.predict(
            np.zeros(2), np.eye(2),
            f=lambda s: s + np.array([1.0, 0.0]),
            Q=np.eye(2) * 0.01,
        )
        assert x_p[0] == pytest.approx(1.0, abs=1e-6)

    def test_gain_shape(self):
        G = self.urts.gain(np.eye(2), np.eye(2) * 2.0, np.eye(2) * 0.5)
        assert G.shape == (2, 2)

    def test_smooth_step_returns_pair(self):
        x_s, P_s = self.urts.smooth_step(
            x_s_next=np.array([1.0, 1.0]),
            P_s_next=np.eye(2),
            x_f=np.array([0.5, 0.5]),
            P_f=np.eye(2),
            x_p=np.array([0.4, 0.4]),
            P_p=np.eye(2) * 1.5,
            Pxy=np.eye(2) * 0.5,
        )
        assert x_s.shape == (2,)
        assert P_s.shape == (2, 2)

    def test_smooth_P_symmetric(self):
        _, P_s = self.urts.smooth_step(
            x_s_next=np.array([0.0, 0.0]),
            P_s_next=np.eye(2),
            x_f=np.zeros(2),
            P_f=np.eye(2),
            x_p=np.zeros(2),
            P_p=np.eye(2) * 1.5,
            Pxy=np.eye(2) * 0.3,
        )
        assert np.allclose(P_s, P_s.T, atol=1e-9)


# ============================================================================
# NeuralOdometryRegressor
# ============================================================================

class TestNeuralOdometryRegressor:
    def setup_method(self):
        self.n = NeuralOdometryRegressor(input_dim=6, hidden=8,
                                         output_dim=3)

    def test_relu_clips_negatives(self):
        out = self.n.relu(np.array([-1.0, 0.0, 2.0]))
        assert np.allclose(out, [0.0, 0.0, 2.0])

    def test_forward_returns_pair(self):
        out, h = self.n.forward(np.zeros(6))
        assert out.shape == (3,)
        assert h.shape == (8,)

    def test_predict_displacement_shape(self):
        out = self.n.predict_displacement(np.zeros(6))
        assert out.shape == (3,)

    def test_update_weights_changes_W2(self):
        before = self.n.W2.copy()
        grad_W2 = np.ones_like(self.n.W2)
        grad_b2 = np.ones_like(self.n.b2)
        self.n.update_weights(grad_W2, grad_b2, lr=0.5)
        assert not np.allclose(before, self.n.W2)

    def test_update_weights_changes_b2(self):
        before = self.n.b2.copy()
        grad_W2 = np.zeros_like(self.n.W2)
        grad_b2 = np.ones_like(self.n.b2)
        self.n.update_weights(grad_W2, grad_b2, lr=0.5)
        assert not np.allclose(before, self.n.b2)

    def test_window_norm_zero_mean(self):
        rng = np.random.RandomState(0)
        w = rng.randn(20, 6)
        n = self.n.window_norm(w)
        assert np.allclose(n.mean(axis=0), 0.0, atol=1e-9)

    def test_window_norm_unit_std(self):
        rng = np.random.RandomState(1)
        w = rng.randn(50, 6)
        n = self.n.window_norm(w)
        assert np.allclose(n.std(axis=0), 1.0, atol=1e-2)
