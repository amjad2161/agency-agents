"""GODSKILL Navigation R12 — improvement-round tests.

Covers:
- GNSSClockSteeringLoop
- AsynchronousMultiSensorFusion
- GaitPhaseEstimator
- RadioSLAM
- ContinualLearningNavigator
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.satellite import GNSSClockSteeringLoop  # noqa: E402
from agency.navigation.fusion import (  # noqa: E402
    AsynchronousMultiSensorFusion,
)
from agency.navigation.indoor_inertial import GaitPhaseEstimator  # noqa: E402
from agency.navigation.indoor_slam import RadioSLAM  # noqa: E402
from agency.navigation.ai_enhance import ContinualLearningNavigator  # noqa: E402


# ============================================================================
# GNSSClockSteeringLoop
# ============================================================================

class TestGNSSClockSteeringLoop:
    def test_init(self):
        loop = GNSSClockSteeringLoop()
        assert loop.phase == 0.0
        assert loop.freq == 0.0

    def test_pll_near_zero_for_in_phase(self):
        loop = GNSSClockSteeringLoop()
        # In-phase (Q=0) → atan2(0, +I) = 0
        assert loop.discriminator_pll(1.0, 0.0) == pytest.approx(0.0)

    def test_pll_near_pi_over_two_for_quadrature(self):
        loop = GNSSClockSteeringLoop()
        assert loop.discriminator_pll(0.0, 1.0) == pytest.approx(math.pi / 2)

    def test_fll_near_zero_for_static(self):
        loop = GNSSClockSteeringLoop()
        # Same I, Q over time → no rotation → 0 Hz
        f = loop.discriminator_fll(1.0, 0.0, 1.0, 0.0, dt=0.001)
        assert abs(f) < 1e-6

    def test_cli_above_085_for_locked(self):
        loop = GNSSClockSteeringLoop()
        # Strong I, weak Q → CLI close to 1
        I = np.full(50, 1.0)
        Q = np.full(50, 0.05)
        assert loop.carrier_lock_indicator(I, Q) > 0.85

    def test_cli_negative_for_quadrature(self):
        loop = GNSSClockSteeringLoop()
        I = np.full(50, 0.05)
        Q = np.full(50, 1.0)
        assert loop.carrier_lock_indicator(I, Q) < 0.0

    def test_update_nco_returns_tuple(self):
        loop = GNSSClockSteeringLoop()
        out = loop.update_nco(0.1, 0.0, dt=0.001, bandwidth_hz=10.0)
        assert len(out) == 2


# ============================================================================
# AsynchronousMultiSensorFusion
# ============================================================================

class TestAsynchronousMultiSensorFusion:
    def test_init(self):
        f = AsynchronousMultiSensorFusion()
        assert f.x.shape == (6,)

    def test_add_measurement(self):
        f = AsynchronousMultiSensorFusion()
        f.add_measurement(0.0, "gps", np.array([1.0, 2.0, 3.0]))
        assert len(f._queue) == 1

    def test_process_until_returns_list(self):
        f = AsynchronousMultiSensorFusion()
        f.add_measurement(0.0, "gps", np.array([1.0, 2.0, 3.0]))
        f.add_measurement(0.5, "imu", np.array([0.1, 0.0, 0.0]))
        out = f.process_until(1.0)
        assert isinstance(out, list)
        assert len(out) == 2

    def test_propagate_to_returns_state(self):
        f = AsynchronousMultiSensorFusion()
        x = f.propagate_to(1.0)
        assert x.shape == (6,)

    def test_out_of_sequence_update_runs(self):
        f = AsynchronousMultiSensorFusion()
        f.add_measurement(0.0, "gps", np.array([1.0, 2.0, 3.0]))
        f.process_until(1.0)
        H = np.zeros((3, 6)); H[0, 0] = H[1, 1] = H[2, 2] = 1.0
        out = f.out_of_sequence_update(0.0, np.array([5.0, 5.0, 5.0]),
                                       H, np.eye(3) * 4.0)
        assert out.shape == (6,)

    def test_queue_ordered_by_time(self):
        f = AsynchronousMultiSensorFusion()
        f.add_measurement(2.0, "imu", np.zeros(3))
        f.add_measurement(0.5, "imu", np.zeros(3))
        f.add_measurement(1.0, "imu", np.zeros(3))
        out = f.process_until(3.0)
        times = [t for t, _ in out]
        assert times == sorted(times)

    def test_multi_sensor_processing(self):
        f = AsynchronousMultiSensorFusion()
        for k in range(5):
            f.add_measurement(k * 0.1, "imu", np.array([0.5, 0.0, 9.81]))
        f.add_measurement(0.5, "gps", np.array([0.05, 0.0, 0.0]))
        f.add_measurement(0.7, "baro", np.array([0.0]))
        f.process_until(1.0)
        assert np.all(np.isfinite(f.x))


# ============================================================================
# GaitPhaseEstimator
# ============================================================================

class TestGaitPhaseEstimator:
    def test_init(self):
        g = GaitPhaseEstimator()
        assert len(g.PHASE_NAMES) == 8

    def test_detect_phases_returns_list(self):
        g = GaitPhaseEstimator()
        a = np.array([10.0, 9.81, 9.5, 9.81, 10.5, 9.5, 9.81])
        gy = np.zeros_like(a)
        out = g.detect_phases(a, gy)
        assert isinstance(out, list)
        assert len(out) == a.size

    def test_cadence_positive(self):
        g = GaitPhaseEstimator()
        ts = [0.0, 0.5, 1.0, 1.5, 2.0]
        c = g.estimate_cadence(ts)
        assert c > 0.0

    def test_step_length_positive(self):
        g = GaitPhaseEstimator()
        L = g.step_length_from_frequency(120.0, 1.75)
        assert L > 0.0

    def test_step_length_scales_with_height(self):
        g = GaitPhaseEstimator()
        L_short = g.step_length_from_frequency(120.0, 1.50)
        L_tall = g.step_length_from_frequency(120.0, 2.00)
        assert L_tall > L_short

    def test_step_length_scales_with_cadence(self):
        g = GaitPhaseEstimator()
        L_slow = g.step_length_from_frequency(60.0, 1.75)
        L_fast = g.step_length_from_frequency(180.0, 1.75)
        assert L_fast > L_slow

    def test_phases_in_valid_range(self):
        g = GaitPhaseEstimator()
        rng = np.random.RandomState(0)
        a = rng.normal(9.81, 1.0, 100)
        gy = rng.normal(0.0, 1.0, 100)
        out = g.detect_phases(a, gy)
        assert all(0 <= p <= 7 for p in out)


# ============================================================================
# RadioSLAM
# ============================================================================

class TestRadioSLAM:
    def test_init(self):
        s = RadioSLAM()
        assert s.observations == {}

    def test_observe_stores(self):
        s = RadioSLAM()
        s.observe("AP1", -65.0, (0.0, 0.0))
        assert "AP1" in s.observations

    def test_estimate_ap_position_returns_2d(self):
        s = RadioSLAM()
        s.observe("AP1", -60.0, (1.0, 1.0))
        s.observe("AP1", -65.0, (2.0, 2.0))
        p = s.estimate_ap_position("AP1")
        assert p.shape == (2,)

    def test_estimate_with_one_obs_equals_pos(self):
        s = RadioSLAM()
        s.observe("AP1", -60.0, (3.0, 4.0))
        p = s.estimate_ap_position("AP1")
        assert np.allclose(p, [3.0, 4.0])

    def test_map_uncertainty_shape(self):
        s = RadioSLAM()
        s.observe("AP1", -60.0, (0.0, 0.0))
        s.observe("AP1", -65.0, (1.0, 0.0))
        s.observe("AP1", -55.0, (0.0, 1.0))
        cov = s.map_uncertainty("AP1")
        assert cov.shape == (2, 2)

    def test_update_position_returns_2d(self):
        s = RadioSLAM()
        # Build a mini-map of three APs at known anchor positions
        for ap_id, pos in [("A", (0.0, 0.0)), ("B", (10.0, 0.0)),
                           ("C", (0.0, 10.0))]:
            s.observe(ap_id, -50.0, pos)
        out = s.update_position_from_map(
            (1.0, 1.0),
            [("A", -60.0), ("B", -70.0), ("C", -70.0)],
        )
        assert out.shape == (2,)

    def test_multi_ap_update(self):
        s = RadioSLAM()
        anchors = [("A", (0.0, 0.0)), ("B", (10.0, 0.0)),
                   ("C", (0.0, 10.0)), ("D", (10.0, 10.0))]
        for ap_id, pos in anchors:
            s.observe(ap_id, -50.0, pos)
        out = s.update_position_from_map(
            (5.0, 5.0),
            [("A", -65.0), ("B", -65.0), ("C", -65.0), ("D", -65.0)],
        )
        assert np.all(np.isfinite(out))


# ============================================================================
# ContinualLearningNavigator
# ============================================================================

class TestContinualLearningNavigator:
    def test_init(self):
        n = ContinualLearningNavigator()
        assert "W" in n.weights

    def test_compute_fisher_returns_dict(self):
        n = ContinualLearningNavigator()
        rng = np.random.RandomState(0)
        loader = [(rng.randn(16, 8), rng.randn(16, 4)) for _ in range(3)]
        f = n.compute_fisher_diagonal(loader)
        assert "W" in f
        assert f["W"].shape == n.weights["W"].shape

    def test_ewc_loss_positive(self):
        n = ContinualLearningNavigator()
        rng = np.random.RandomState(0)
        cur = {"W": rng.randn(8, 4)}
        old = {"W": np.zeros((8, 4))}
        fish = {"W": np.ones((8, 4))}
        loss = ContinualLearningNavigator.ewc_loss(cur, old, fish, 100.0)
        assert loss > 0.0

    def test_ewc_loss_zero_when_unchanged(self):
        n = ContinualLearningNavigator()
        cur = {"W": np.ones((8, 4))}
        old = {"W": np.ones((8, 4))}
        fish = {"W": np.ones((8, 4))}
        loss = ContinualLearningNavigator.ewc_loss(cur, old, fish, 100.0)
        assert loss == pytest.approx(0.0)

    def test_train_returns_weights(self):
        n = ContinualLearningNavigator()
        rng = np.random.RandomState(0)
        X = rng.randn(32, 8)
        Y = rng.randn(32, 4)
        out = n.train_with_ewc(X, Y, lr=0.001, epochs=2)
        assert "W" in out
        assert out["W"].shape == n.weights["W"].shape

    def test_consolidate_updates_fisher(self):
        n = ContinualLearningNavigator()
        rng = np.random.RandomState(0)
        loader = [(rng.randn(16, 8), rng.randn(16, 4)) for _ in range(3)]
        before = n.fisher["W"].copy()
        n.consolidate(loader)
        assert not np.allclose(before, n.fisher["W"])

    def test_lambda_scales_loss(self):
        cur = {"W": np.ones((8, 4))}
        old = {"W": np.zeros((8, 4))}
        fish = {"W": np.ones((8, 4))}
        l1 = ContinualLearningNavigator.ewc_loss(cur, old, fish, 1.0)
        l100 = ContinualLearningNavigator.ewc_loss(cur, old, fish, 100.0)
        assert l100 == pytest.approx(100.0 * l1)
