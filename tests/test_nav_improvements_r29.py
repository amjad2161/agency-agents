"""GODSKILL Navigation R29 — final spec round tests."""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.underwater import BathymetricMapMatcher  # noqa: E402
from agency.navigation.underground import TerrainReferencingNavigator  # noqa: E402
from agency.navigation.fusion import TimeAlignmentFilter, JPDATracker  # noqa: E402
from agency.navigation.ai_enhance import RadioMapLocaliser  # noqa: E402


# ============================================================================
# BathymetricMapMatcher
# ============================================================================

def _bath():
    lat = np.linspace(0.0, 1.0, 11)
    lon = np.linspace(0.0, 1.0, 11)
    L, O = np.meshgrid(lat, lon, indexing="ij")
    depth = 100.0 + 50.0 * L + 30.0 * O
    return BathymetricMapMatcher(lat, lon, depth)


class TestBathymetricMapMatcher:
    def test_reference_depth_returns_float(self):
        b = _bath()
        d = b.reference_depth(0.5, 0.5)
        assert isinstance(d, float)

    def test_reference_depth_in_range(self):
        b = _bath()
        d = b.reference_depth(0.5, 0.5)
        assert 100.0 <= d <= 200.0

    def test_depth_residual_zero_at_reference(self):
        b = _bath()
        ref = b.reference_depth(0.3, 0.7)
        r = b.depth_residual(ref, 0.3, 0.7)
        assert abs(r) < 1e-9

    def test_match_sequence_returns_index(self):
        b = _bath()
        traj_correct = [(0.5, 0.5), (0.6, 0.5)]
        seq = [b.reference_depth(*p) for p in traj_correct]
        cands = [
            [(0.0, 0.0), (0.0, 0.0)],
            traj_correct,
            [(1.0, 1.0), (1.0, 1.0)],
        ]
        idx = b.match_sequence(seq, cands)
        assert idx == 1

    def test_gradient_shape(self):
        b = _bath()
        g = b.gradient(0.5, 0.5)
        assert g.shape == (2,)

    def test_position_update_shape(self):
        b = _bath()
        out = b.position_update(0.5, 0.5, 130.0, step=0.001)
        assert out.shape == (2,)

    def test_position_update_returns_floats(self):
        b = _bath()
        out = b.position_update(0.5, 0.5, 145.0)
        assert all(isinstance(v, float) for v in out.tolist())


# ============================================================================
# TerrainReferencingNavigator
# ============================================================================

def _trn():
    lat = np.linspace(0.0, 1.0, 11)
    lon = np.linspace(0.0, 1.0, 11)
    L, O = np.meshgrid(lat, lon, indexing="ij")
    elev = 200.0 + 100.0 * L + 50.0 * O
    return TerrainReferencingNavigator(lat, lon, elev)


class TestTerrainReferencingNavigator:
    def test_terrain_elevation_returns_float(self):
        t = _trn()
        e = t.terrain_elevation(0.5, 0.5)
        assert isinstance(e, float)

    def test_altitude_residual_zero_at_terrain(self):
        t = _trn()
        e = t.terrain_elevation(0.4, 0.6)
        r = t.altitude_residual(e, 0.4, 0.6)
        assert abs(r) < 1e-9

    def test_match_profile_returns_index(self):
        t = _trn()
        true_traj = [(0.5, 0.5), (0.6, 0.5), (0.7, 0.5)]
        seq = [t.terrain_elevation(*p) for p in true_traj]
        cands = [
            [(0.0, 0.0), (0.0, 0.0), (0.0, 0.0)],
            true_traj,
            [(1.0, 1.0), (1.0, 1.0), (1.0, 1.0)],
        ]
        idx = t.match_profile(seq, cands)
        assert idx == 1

    def test_gradient_step_shape(self):
        t = _trn()
        out = t.gradient_step(0.5, 0.5, 280.0)
        assert out.shape == (2,)

    def test_correlation_score_in_range(self):
        t = _trn()
        traj = [(0.0, 0.0), (0.5, 0.0), (1.0, 0.0)]
        seq = [t.terrain_elevation(*p) for p in traj]
        c = t.correlation_score(seq, traj)
        assert -1.0 <= c <= 1.0

    def test_correlation_high_for_matching(self):
        t = _trn()
        traj = [(0.0, 0.0), (0.5, 0.0), (1.0, 0.0)]
        seq = [t.terrain_elevation(*p) for p in traj]
        c = t.correlation_score(seq, traj)
        assert c > 0.9

    def test_terrain_elevation_corner_exact(self):
        t = _trn()
        e = t.terrain_elevation(0.0, 0.0)
        assert e == pytest.approx(200.0, abs=1e-6)


# ============================================================================
# TimeAlignmentFilter
# ============================================================================

class TestTimeAlignmentFilter:
    def setup_method(self):
        self.f = TimeAlignmentFilter()
        for k in range(5):
            self.f.add_sample("imu", float(k), float(k * 2))

    def test_add_sample_stores(self):
        assert "imu" in self.f._samples
        assert len(self.f._samples["imu"]) == 5

    def test_interpolate_at_known_time(self):
        v = self.f.interpolate("imu", 2.0)
        assert float(v) == pytest.approx(4.0)

    def test_interpolate_between(self):
        v = self.f.interpolate("imu", 2.5)
        assert float(v) == pytest.approx(5.0)

    def test_interpolate_clamps_below(self):
        v = self.f.interpolate("imu", -10.0)
        assert float(v) == pytest.approx(0.0)

    def test_align_to_timeline_shape(self):
        out = self.f.align_to_timeline([0.5, 1.5, 2.5], "imu")
        assert out.shape[0] == 3

    def test_lag_zero_for_same_sensor(self):
        for k in range(5):
            self.f.add_sample("gps", float(k), float(k))
        lag = self.f.lag("imu", "gps")
        assert abs(lag) < 1e-9

    def test_sync_offset_shifts(self):
        self.f.sync_offset("imu", 10.0)
        ts = [t for t, _ in self.f._samples["imu"]]
        assert min(ts) == pytest.approx(10.0)


# ============================================================================
# JPDATracker
# ============================================================================

class TestJPDATracker:
    def setup_method(self):
        self.j = JPDATracker(gate_chi2=9.21)
        self.j.add_track(1, np.array([0.0, 0.0]), np.eye(2))

    def test_mahalanobis_zero_at_state(self):
        d = self.j.mahalanobis(1, np.array([0.0, 0.0]), np.eye(2))
        assert d == pytest.approx(0.0)

    def test_mahalanobis_positive(self):
        d = self.j.mahalanobis(1, np.array([1.0, 1.0]), np.eye(2))
        assert d > 0.0

    def test_gate_true_close(self):
        assert self.j.gate(1, np.array([0.5, 0.5]), np.eye(2)) is True

    def test_gate_false_far(self):
        assert self.j.gate(1, np.array([20.0, 20.0]), np.eye(2)) is False

    def test_association_probs_sum_to_one(self):
        meas = [np.array([0.1, 0.0]), np.array([0.0, 0.2]),
                np.array([5.0, 5.0])]
        beta = self.j.association_probs(1, meas, np.eye(2))
        assert beta.shape == (4,)
        assert abs(float(beta.sum()) - 1.0) < 1e-9

    def test_update_track_returns_pair(self):
        meas = [np.array([0.5, 0.5])]
        x, P = self.j.update_track(1, meas, np.eye(2))
        assert x.shape == (2,)
        assert P.shape == (2, 2)

    def test_update_moves_state(self):
        before = self.j._tracks[1][0].copy()
        meas = [np.array([2.0, 0.0])]
        x_new, _ = self.j.update_track(1, meas, np.eye(2) * 0.1)
        assert not np.allclose(x_new, before)


# ============================================================================
# RadioMapLocaliser
# ============================================================================

class TestRadioMapLocaliser:
    def setup_method(self):
        self.r = RadioMapLocaliser(feature_dim=4)
        self.r.add_fingerprint([0.0, 0.0], [1, 0, 0, 0])
        self.r.add_fingerprint([1.0, 0.0], [0, 1, 0, 0])
        self.r.add_fingerprint([0.0, 1.0], [0, 0, 1, 0])
        self.r.add_fingerprint([1.0, 1.0], [0, 0, 0, 1])

    def test_add_fingerprint_grows(self):
        assert len(self.r._db) == 4

    def test_knn_locate_returns_2vec(self):
        out = self.r.knn_locate([1, 0, 0, 0], k=1)
        assert out.shape == (2,)

    def test_knn_locate_top1_correct(self):
        out = self.r.knn_locate([1, 0, 0, 0], k=1)
        assert np.allclose(out, [0.0, 0.0])

    def test_train_radio_map_returns_W_b(self):
        feats = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        ps = [[0, 0], [1, 0], [0, 1], [1, 1]]
        W, b = self.r.train_radio_map(feats, ps, epochs=200, lr=0.05)
        assert W.shape == (2, 4)
        assert b.shape == (2,)

    def test_predict_position_shape(self):
        out = self.r.predict_position([1, 0, 0, 0])
        assert out.shape == (2,)

    def test_predict_position_after_training(self):
        feats = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
        ps = [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
        self.r.train_radio_map(feats, ps, epochs=500, lr=0.05)
        out = self.r.predict_position([1, 0, 0, 0])
        assert float(np.linalg.norm(out - np.array([0.0, 0.0]))) < 0.5

    def test_fingerprint_similarity_unit(self):
        s = RadioMapLocaliser.fingerprint_similarity([1, 0, 0],
                                                     [1, 0, 0])
        assert s == pytest.approx(1.0)
