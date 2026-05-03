"""GODSKILL Navigation R27 — improvement-round tests."""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.underground import (  # noqa: E402
    RadioBeaconTriangulator,
    GravityAnomalyNavigator,
)
from agency.navigation.indoor_slam import PoseGraphSLAM  # noqa: E402
from agency.navigation.ai_enhance import TrajectoryLSTMPredictor  # noqa: E402
from agency.navigation.fusion import UncertaintyQuantifier  # noqa: E402


# ============================================================================
# RadioBeaconTriangulator
# ============================================================================

class TestRadioBeaconTriangulator:
    def setup_method(self):
        self.t = RadioBeaconTriangulator()
        self.t.add_beacon("A", [0, 0], 433e6, power_dbm=20.0)
        self.t.add_beacon("B", [10, 0], 433e6, power_dbm=20.0)
        self.t.add_beacon("C", [0, 10], 433e6, power_dbm=20.0)
        self.t.add_beacon("D", [10, 10], 433e6, power_dbm=20.0)

    def test_rssi_to_range_at_ref(self):
        d = self.t.rssi_to_range(20.0, "A")
        assert d == pytest.approx(1.0)

    def test_rssi_to_range_weaker_signal_farther(self):
        d1 = self.t.rssi_to_range(0.0, "A")
        d2 = self.t.rssi_to_range(-20.0, "A")
        assert d2 > d1

    def test_add_rssi_stores(self):
        self.t.add_rssi("A", -50.0)
        assert "A" in self.t._rssi

    def test_triangulate_returns_2vec(self):
        true = np.array([3.0, 4.0])
        for bid, pos in [("A", [0, 0]), ("B", [10, 0]),
                         ("C", [0, 10]), ("D", [10, 10])]:
            d = float(np.linalg.norm(np.asarray(pos, dtype=float) - true))
            # Invert path-loss to RSSI for n=2: rssi = power - 20*log10(d)
            rssi = 20.0 - 20.0 * math.log10(max(d, 1e-3))
            self.t.add_rssi(bid, rssi)
        out = self.t.triangulate()
        assert out.shape == (2,)

    def test_triangulate_accuracy(self):
        true = np.array([3.0, 4.0])
        for bid, pos in [("A", [0, 0]), ("B", [10, 0]),
                         ("C", [0, 10]), ("D", [10, 10])]:
            d = float(np.linalg.norm(np.asarray(pos, dtype=float) - true))
            rssi = 20.0 - 20.0 * math.log10(max(d, 1e-3))
            self.t.add_rssi(bid, rssi)
        out = self.t.triangulate()
        assert float(np.linalg.norm(out - true)) < 0.5

    def test_range_residuals_zero_at_truth(self):
        true = np.array([3.0, 4.0])
        for bid, pos in [("A", [0, 0]), ("B", [10, 0]),
                         ("C", [0, 10])]:
            d = float(np.linalg.norm(np.asarray(pos, dtype=float) - true))
            rssi = 20.0 - 20.0 * math.log10(max(d, 1e-3))
            self.t.add_rssi(bid, rssi)
        res = self.t.range_residuals(true)
        assert np.all(np.abs(res) < 1e-6)

    def test_clear_measurements_keeps_beacons(self):
        self.t.add_rssi("A", -50.0)
        self.t.clear_measurements()
        assert len(self.t._rssi) == 0
        assert len(self.t._beacons) == 4


# ============================================================================
# GravityAnomalyNavigator
# ============================================================================

def _gnav():
    lat = np.linspace(0.0, 1.0, 11)
    lon = np.linspace(0.0, 1.0, 11)
    L, O = np.meshgrid(lat, lon, indexing="ij")
    g_map = 9.80 + 0.001 * L + 0.002 * O
    return GravityAnomalyNavigator(lat, lon, g_map)


class TestGravityAnomalyNavigator:
    def test_reference_gravity_returns_float(self):
        n = _gnav()
        g = n.reference_gravity(0.5, 0.5)
        assert isinstance(g, float)

    def test_reference_gravity_in_range(self):
        n = _gnav()
        g = n.reference_gravity(0.5, 0.5)
        assert 9.79 <= g <= 9.81

    def test_anomaly_zero_at_reference(self):
        n = _gnav()
        ref = n.reference_gravity(0.3, 0.7)
        a = n.anomaly(ref, 0.3, 0.7)
        assert abs(a) < 1e-9

    def test_map_match_returns_index(self):
        n = _gnav()
        cands = [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)]
        seq = [n.reference_gravity(0.5, 0.5)]
        idx = n.map_match(seq, cands)
        assert idx == 1

    def test_gravity_gradient_shape(self):
        n = _gnav()
        g = n.gravity_gradient(0.5, 0.5)
        assert g.shape == (2,)

    def test_position_update_shape(self):
        n = _gnav()
        out = n.position_update(0.5, 0.5, 9.805)
        assert out.shape == (2,)

    def test_position_update_returns_floats(self):
        n = _gnav()
        out = n.position_update(0.5, 0.5, 9.81)
        assert all(isinstance(v, float) for v in out.tolist())


# ============================================================================
# PoseGraphSLAM
# ============================================================================

class TestPoseGraphSLAM:
    def setup_method(self):
        self.g = PoseGraphSLAM()
        self.g.add_node(0, [0.0, 0.0, 0.0])
        self.g.add_node(1, [1.0, 0.0, 0.0])
        self.g.add_node(2, [2.0, 0.0, 0.0])

    def test_add_node_stores(self):
        assert 1 in self.g.nodes

    def test_add_edge_grows(self):
        self.g.add_edge(0, 1, [1.0, 0.0, 0.0])
        assert len(self.g.edges) == 1

    def test_linearise_edge_zero_residual(self):
        e = self.g.linearise_edge(0, 1, [1.0, 0.0, 0.0])
        assert np.allclose(e, 0.0)

    def test_linearise_edge_nonzero(self):
        e = self.g.linearise_edge(0, 1, [2.0, 0.0, 0.0])
        assert abs(e[0]) > 0.5

    def test_optimise_runs(self):
        self.g.add_edge(0, 1, [1.0, 0.0, 0.0])
        self.g.add_edge(1, 2, [1.0, 0.0, 0.0])
        before = self.g.nodes[2].copy()
        self.g.nodes[2] = np.array([2.5, 0.1, 0.0])
        self.g.optimise(n_iter=5)
        assert float(np.linalg.norm(self.g.nodes[2] - before)) < 0.1

    def test_marginal_covariance_shape(self):
        self.g.add_edge(0, 1, [1.0, 0.0, 0.0])
        self.g.add_edge(1, 2, [1.0, 0.0, 0.0])
        self.g.optimise(n_iter=1)
        cov = self.g.marginal_covariance(1)
        assert cov.shape == (3, 3)

    def test_anchor_node_unchanged(self):
        self.g.add_edge(0, 1, [1.0, 0.0, 0.0])
        before = self.g.nodes[0].copy()
        self.g.optimise(n_iter=3)
        assert np.allclose(self.g.nodes[0], before)


# ============================================================================
# TrajectoryLSTMPredictor
# ============================================================================

class TestTrajectoryLSTMPredictor:
    def setup_method(self):
        self.lstm = TrajectoryLSTMPredictor(input_dim=3, hidden_dim=8,
                                            output_dim=3)

    def test_sigmoid_zero_returns_half(self):
        v = self.lstm.sigmoid(0.0)
        assert abs(float(v) - 0.5) < 1e-9

    def test_sigmoid_in_unit_interval(self):
        v = self.lstm.sigmoid(np.array([-5.0, 0.0, 5.0]))
        assert np.all((v >= 0.0) & (v <= 1.0))

    def test_lstm_step_returns_pair(self):
        h, c = self.lstm.lstm_step(np.zeros(3), np.zeros(8), np.zeros(8))
        assert h.shape == (8,)
        assert c.shape == (8,)

    def test_predict_next_shape(self):
        seq = np.zeros((10, 3))
        out = self.lstm.predict_next(seq)
        assert out.shape == (3,)

    def test_predict_next_finite(self):
        seq = np.random.RandomState(0).randn(20, 3)
        out = self.lstm.predict_next(seq)
        assert np.all(np.isfinite(out))

    def test_reset_state_zeros(self):
        self.lstm.h = np.ones(8); self.lstm.c = np.ones(8)
        self.lstm.reset_state()
        assert np.allclose(self.lstm.h, 0.0)
        assert np.allclose(self.lstm.c, 0.0)

    def test_state_carries_within_predict(self):
        # Different sequences → different outputs
        seq1 = np.ones((5, 3))
        seq2 = -np.ones((5, 3))
        o1 = self.lstm.predict_next(seq1)
        o2 = self.lstm.predict_next(seq2)
        assert not np.allclose(o1, o2)


# ============================================================================
# UncertaintyQuantifier
# ============================================================================

class TestUncertaintyQuantifier:
    def setup_method(self):
        self.q = UncertaintyQuantifier(n_samples=200, seed=42)

    def test_monte_carlo_returns_pair(self):
        mu, cov = self.q.monte_carlo_propagate(
            np.zeros(2), np.eye(2), f=lambda x: 2.0 * x)
        assert mu.shape == (2,)
        assert cov.shape == (2, 2)

    def test_credible_interval_shape(self):
        rng = np.random.RandomState(0)
        s = rng.randn(500, 3)
        lo, hi = self.q.credible_interval(s, alpha=0.95)
        assert lo.shape == (3,)
        assert hi.shape == (3,)
        assert np.all(hi >= lo)

    def test_entropy_returns_float(self):
        h = self.q.entropy(np.eye(3))
        assert isinstance(h, float)

    def test_entropy_grows_with_cov(self):
        h_small = self.q.entropy(np.eye(2) * 0.1)
        h_big = self.q.entropy(np.eye(2) * 10.0)
        assert h_big > h_small

    def test_kl_divergence_zero_for_same(self):
        mu = np.array([1.0, 2.0])
        C = np.eye(2) * 1.0
        kl = self.q.kl_divergence(mu, C, mu, C)
        assert abs(kl) < 1e-9

    def test_kl_divergence_positive_for_different(self):
        kl = self.q.kl_divergence(np.array([0.0, 0.0]), np.eye(2),
                                   np.array([5.0, 0.0]), np.eye(2))
        assert kl > 0.0

    def test_nees_nonneg(self):
        n = self.q.nees(np.array([0.5, -0.3]), np.eye(2))
        assert n >= 0.0
