"""GODSKILL Navigation R21 — improvement-round tests."""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.underground import (  # noqa: E402
    RadarAltimeterNav,
    GeomagneticAnomalyNav,
)
from agency.navigation.indoor_slam import CellularTowerPositioning  # noqa: E402
from agency.navigation.fusion import AdaptivePredictiveFilter  # noqa: E402
from agency.navigation.ai_enhance import TransferLearningNavigator  # noqa: E402


# ============================================================================
# RadarAltimeterNav
# ============================================================================

class TestRadarAltimeterNav:
    def setup_method(self):
        self.nav = RadarAltimeterNav(map_resolution_m=1.0)

    def test_measure_height_returns_float(self):
        h = self.nav.measure_height(15.3)
        assert abs(h - 15.3) < 1e-9

    def test_load_dem_populates_map(self):
        grid = np.array([[10.0, 12.0], [11.0, 13.0]])
        self.nav.load_dem(grid, (0, 0))
        assert len(self.nav.dem_map) == 4

    def test_terrain_height_at_exact_grid(self):
        grid = np.array([[5.0, 7.0], [6.0, 8.0]])
        self.nav.load_dem(grid, (0, 0))
        h = self.nav.terrain_height_at((0, 0))
        assert abs(h - 5.0) < 1e-6

    def test_terrain_height_interpolation(self):
        grid = np.array([[0.0, 4.0], [0.0, 4.0]])
        self.nav.load_dem(grid, (0, 0))
        h = self.nav.terrain_height_at((0.5, 0.0))
        assert abs(h - 2.0) < 1e-6

    def test_correlate_returns_best_position(self):
        grid = np.array([[5.0, 10.0, 15.0]])
        self.nav.load_dem(grid, (0, 0))
        candidates = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)]
        best, err = self.nav.correlate_position(10.0, candidates)
        assert best == (1.0, 0.0)
        assert err < 1e-6

    def test_correlate_error_is_nonneg(self):
        grid = np.array([[3.0, 8.0]])
        self.nav.load_dem(grid, (0, 0))
        _, err = self.nav.correlate_position(8.0,
                                              [(0.0, 0.0), (1.0, 0.0)])
        assert err >= 0

    def test_altitude_accuracy_increases_with_range(self):
        acc1 = self.nav.altitude_accuracy(10.0)
        acc2 = self.nav.altitude_accuracy(100.0)
        assert acc2 > acc1


# ============================================================================
# GeomagneticAnomalyNav
# ============================================================================

class TestGeomagneticAnomalyNav:
    def setup_method(self):
        self.nav = GeomagneticAnomalyNav(map_resolution_m=2.0)

    def test_anomaly_subtracts_reference(self):
        measured = self.nav.reference_field + np.array([100.0, 50.0, -30.0])
        anom = self.nav.anomaly(measured)
        assert np.allclose(anom, [100.0, 50.0, -30.0])

    def test_load_map_stores_entries(self):
        positions = [(0, 0), (2, 0), (4, 0)]
        fields = [self.nav.reference_field] * 3
        self.nav.load_map(positions, fields)
        assert len(self.nav.mag_map) == 3

    def test_match_position_exact(self):
        pos = [(0, 0), (2, 0), (4, 0)]
        bvec_target = self.nav.reference_field + np.array([100.0, 0.0, 0.0])
        fields = [self.nav.reference_field, bvec_target,
                  self.nav.reference_field]
        self.nav.load_map(pos, fields)
        meas = self.nav.reference_field + np.array([100.0, 0.0, 0.0])
        key, dist = self.nav.match_position(meas)
        assert key == (1, 0)
        assert dist < 1e-6

    def test_match_position_returns_tuple(self):
        self.nav.load_map([(0, 0)], [self.nav.reference_field])
        key, dist = self.nav.match_position(self.nav.reference_field)
        assert isinstance(key, tuple)
        assert isinstance(dist, float)

    def test_position_from_key_scales_correctly(self):
        x, y = self.nav.position_from_key((3, 5))
        assert abs(x - 6.0) < 1e-9
        assert abs(y - 10.0) < 1e-9

    def test_update_map_overwrites(self):
        self.nav.update_map((0, 0), [1.0, 2.0, 3.0])
        self.nav.update_map((0, 0), [4.0, 5.0, 6.0])
        np.testing.assert_allclose(self.nav.mag_map[(0, 0)], [4.0, 5.0, 6.0])

    def test_anomaly_zero_at_reference(self):
        anom = self.nav.anomaly(self.nav.reference_field)
        assert np.allclose(anom, 0.0)


# ============================================================================
# CellularTowerPositioning
# ============================================================================

class TestCellularTowerPositioning:
    def setup_method(self):
        self.cp = CellularTowerPositioning(path_loss_exp=2.0,
                                           ref_rssi_dbm=-40.0,
                                           ref_dist_m=1.0)

    def test_rssi_to_distance_at_ref(self):
        d = self.cp.rssi_to_distance(-40.0)
        assert abs(d - 1.0) < 1e-9

    def test_rssi_to_distance_weaker_signal_farther(self):
        d1 = self.cp.rssi_to_distance(-40.0)
        d2 = self.cp.rssi_to_distance(-60.0)
        assert d2 > d1

    def test_add_tower_stores(self):
        self.cp.add_tower("A", [0, 0, 0])
        assert "A" in self.cp.tower_db

    def test_trilaterate_returns_none_if_too_few(self):
        self.cp.add_tower("A", [0, 0, 0])
        self.cp.add_tower("B", [10, 0, 0])
        result = self.cp.trilaterate([("A", -50.0), ("B", -55.0)])
        assert result is None

    def test_trilaterate_with_three_towers(self):
        self.cp.add_tower("A", [0, 0, 0])
        self.cp.add_tower("B", [20, 0, 0])
        self.cp.add_tower("C", [10, 20, 0])
        result = self.cp.trilaterate([("A", -40.0), ("B", -40.0),
                                      ("C", -50.0)])
        assert result is not None
        assert result.shape == (2,)

    def test_unknown_tower_skipped(self):
        self.cp.add_tower("A", [0, 0, 0])
        self.cp.add_tower("B", [10, 0, 0])
        self.cp.add_tower("C", [5, 10, 0])
        result = self.cp.trilaterate([("A", -40.0), ("B", -40.0),
                                      ("C", -40.0), ("X", -30.0)])
        assert result is not None

    def test_error_bound_decreases_with_more_towers(self):
        e1 = self.cp.positioning_error_bound(1, 50.0)
        e4 = self.cp.positioning_error_bound(4, 50.0)
        assert e4 < e1


# ============================================================================
# AdaptivePredictiveFilter
# ============================================================================

class TestAdaptivePredictiveFilter:
    def setup_method(self):
        self.filt = AdaptivePredictiveFilter(dim=3, horizon=4)

    def test_predict_returns_state(self):
        x = self.filt.predict()
        assert x.shape == (3,)

    def test_update_changes_state(self):
        z = np.array([1.0, 2.0, 3.0])
        x = self.filt.update(z)
        assert not np.allclose(x, 0.0)

    def test_predict_horizon_length(self):
        states = self.filt.predict_horizon()
        assert len(states) == 4

    def test_predict_horizon_shapes(self):
        states = self.filt.predict_horizon()
        assert all(s.shape == (3,) for s in states)

    def test_adaptive_Q_updates(self):
        for _ in range(6):
            self.filt.update(np.ones(3) * 5.0)
        Q1 = self.filt.adaptive_Q()
        assert Q1.shape == (3, 3)

    def test_innovation_history_grows(self):
        self.filt.update(np.array([1., 0., 0.]))
        self.filt.update(np.array([2., 0., 0.]))
        assert len(self.filt.innovation_history) == 2

    def test_covariance_positive_definite(self):
        self.filt.update(np.array([1., 1., 1.]))
        eigvals = np.linalg.eigvalsh(self.filt.P)
        assert np.all(eigvals > 0)


# ============================================================================
# TransferLearningNavigator
# ============================================================================

class TestTransferLearningNavigator:
    def setup_method(self):
        self.tln = TransferLearningNavigator(feature_dim=4)

    def test_fit_source_sets_mean(self):
        data = np.random.randn(20, 4) + 3.0
        self.tln.fit_source(data)
        assert self.tln.source_mean.shape == (4,)

    def test_fit_target_sets_std(self):
        data = np.random.randn(20, 4) * 2.0
        self.tln.fit_target(data)
        assert np.all(self.tln.target_std > 0)

    def test_adapt_output_shape(self):
        f = np.array([1.0, 2.0, 3.0, 4.0])
        out = self.tln.adapt(f)
        assert out.shape == (4,)

    def test_compute_transform_identity_when_same_domain(self):
        data = np.random.randn(30, 4) + 5.0
        self.tln.fit_source(data)
        self.tln.fit_target(data)
        self.tln.compute_transform()
        f = np.array([1.0, 2.0, 3.0, 4.0])
        adapted = self.tln.adapt(f)
        np.testing.assert_allclose(adapted, f, atol=1e-6)

    def test_adapt_shifts_distribution(self):
        src = np.random.randn(50, 4)
        tgt = np.random.randn(50, 4) + 10.0
        self.tln.fit_source(src)
        self.tln.fit_target(tgt)
        self.tln.compute_transform()
        adapted = self.tln.adapt(np.zeros(4))
        assert np.mean(adapted) > 5.0

    def test_domain_gap_zero_same_domain(self):
        data = np.random.randn(40, 4)
        self.tln.fit_source(data)
        self.tln.fit_target(data)
        self.tln.compute_transform()
        gap = self.tln.domain_gap()
        assert gap < 1.0

    def test_domain_gap_large_for_shifted(self):
        src = np.random.randn(40, 4)
        tgt = np.random.randn(40, 4) + 20.0
        self.tln.fit_source(src)
        self.tln.fit_target(tgt)
        self.tln.compute_transform()
        gap = self.tln.domain_gap()
        assert gap > 10.0
