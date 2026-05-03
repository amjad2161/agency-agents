"""GODSKILL Navigation R9 — improvement-round tests.

Covers:
- MultiPathMitigator
- DualRateKalmanFilter
- AltimeterBaroVSI
- BLEProximityMapper
- TemporalConvOdometry
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.satellite import MultiPathMitigator  # noqa: E402
from agency.navigation.fusion import DualRateKalmanFilter  # noqa: E402
from agency.navigation.indoor_inertial import AltimeterBaroVSI  # noqa: E402
from agency.navigation.indoor_slam import BLEProximityMapper  # noqa: E402
from agency.navigation.ai_enhance import TemporalConvOdometry  # noqa: E402


# ============================================================================
# MultiPathMitigator
# ============================================================================

class TestMultiPathMitigator:
    def test_init(self):
        m = MultiPathMitigator()
        assert m.NARROW_SPACING_CHIPS == pytest.approx(0.1)

    def test_indicator_high_for_large_difference(self):
        m = MultiPathMitigator()
        assert m.compute_multipath_indicator(0.5, 1.0) > 0.15

    def test_indicator_low_for_small_difference(self):
        m = MultiPathMitigator()
        assert m.compute_multipath_indicator(0.95, 1.0) < 0.15

    def test_smooth_pseudorange_length(self):
        m = MultiPathMitigator()
        P = np.array([100.0, 100.5, 101.0, 101.5, 102.0])
        Phi = np.array([0.0, 0.5, 1.0, 1.5, 2.0])
        out = m.smooth_pseudorange(P, Phi, n=5)
        assert out.shape == P.shape

    def test_hatch_filter_smooths_noise(self):
        m = MultiPathMitigator()
        rng = np.random.RandomState(0)
        true = np.linspace(100.0, 110.0, 50)
        P = true + rng.normal(0, 1.0, 50)
        Phi = true - 100.0
        out = m.smooth_pseudorange(P, Phi, n=10)
        # Smoothed series should have lower residual variance vs raw
        var_raw = float(np.var(P[5:] - true[5:]))
        var_smooth = float(np.var(out[5:] - true[5:]))
        assert var_smooth < var_raw

    def test_cycle_slip_detects_jump(self):
        m = MultiPathMitigator()
        diffs = np.array([0.01, 0.02, 0.5, 0.01])
        flags = m.detect_cycle_slip(diffs, threshold=0.1)
        assert bool(flags[2]) is True

    def test_no_slip_for_smooth_phase(self):
        m = MultiPathMitigator()
        diffs = np.array([0.01, 0.02, 0.03, 0.01])
        flags = m.detect_cycle_slip(diffs, threshold=0.1)
        assert not flags.any()


# ============================================================================
# DualRateKalmanFilter
# ============================================================================

class TestDualRateKalmanFilter:
    def test_init(self):
        kf = DualRateKalmanFilter(fast_hz=10, slow_hz=1)
        assert kf.x.shape == (6,)
        assert kf.dt_fast == pytest.approx(0.1)
        assert kf.dt_slow == pytest.approx(1.0)

    def test_fast_predict_returns_6state(self):
        kf = DualRateKalmanFilter()
        x = kf.fast_predict(np.array([1.0, 0.0, 9.81]),
                            np.array([0.0, 0.0, 0.0]))
        assert x.shape == (6,)

    def test_slow_update_returns_6state(self):
        kf = DualRateKalmanFilter()
        x = kf.slow_update(np.array([10.0, 5.0, 0.0]))
        assert x.shape == (6,)

    def test_fast_predict_changes_velocity(self):
        kf = DualRateKalmanFilter()
        kf.fast_predict(np.array([2.0, 0.0, 9.81]),
                        np.array([0.0, 0.0, 0.0]), dt=0.1)
        # vx should be > 0 after positive accel applied
        assert kf.x[3] > 0.0

    def test_slow_update_pulls_toward_gps(self):
        kf = DualRateKalmanFilter()
        # Predict drifts state away
        for _ in range(5):
            kf.fast_predict(np.array([0.0, 0.0, 9.81]),
                            np.array([0.0, 0.0, 0.0]))
        before = kf.x[:3].copy()
        target = np.array([100.0, 100.0, 100.0])
        kf.slow_update(target)
        after = kf.x[:3]
        # Distance to target should shrink
        assert float(np.linalg.norm(after - target)) < \
               float(np.linalg.norm(before - target))

    def test_state_shape_consistent(self):
        kf = DualRateKalmanFilter()
        for _ in range(5):
            kf.fast_predict(np.zeros(3), np.zeros(3))
            assert kf.x.shape == (6,)

    def test_multistep_consistency(self):
        kf = DualRateKalmanFilter()
        # 10 fast predicts + 1 slow update
        for _ in range(10):
            kf.fast_predict(np.array([0.5, 0.0, 9.81]),
                            np.zeros(3))
        kf.slow_update(np.array([1.0, 0.0, 0.0]))
        assert np.all(np.isfinite(kf.x))


# ============================================================================
# AltimeterBaroVSI
# ============================================================================

class TestAltimeterBaroVSI:
    def test_init(self):
        vsi = AltimeterBaroVSI()
        assert vsi.alt == pytest.approx(0.0)
        assert vsi.vz == pytest.approx(0.0)

    def test_update_returns_tuple_of_two(self):
        vsi = AltimeterBaroVSI()
        out = vsi.update(baro_alt_m=10.0, accel_z_m_s2=9.80665, dt=0.1)
        assert len(out) == 2

    def test_filtered_alt_near_baro_for_slow_motion(self):
        vsi = AltimeterBaroVSI()
        vsi.reset(0.0)
        # Step baro to 50 m, gravity-cancelling accel, run many slow updates
        for _ in range(200):
            alt, _ = vsi.update(baro_alt_m=50.0, accel_z_m_s2=9.80665, dt=0.5)
        assert abs(alt - 50.0) < 5.0

    def test_vz_near_zero_for_stationary(self):
        vsi = AltimeterBaroVSI()
        vsi.reset(100.0)
        for _ in range(100):
            _, vz = vsi.update(baro_alt_m=100.0,
                               accel_z_m_s2=9.80665, dt=0.1)
        assert abs(vz) < 0.5

    def test_reset_changes_state(self):
        vsi = AltimeterBaroVSI()
        vsi.update(50.0, 0.0, 0.1)
        vsi.reset(123.0)
        assert vsi.alt == pytest.approx(123.0)
        assert vsi.vz == pytest.approx(0.0)

    def test_crossover_freq_property(self):
        vsi = AltimeterBaroVSI()
        assert vsi.crossover_freq == pytest.approx(0.1)

    def test_complementary_integrates_accel(self):
        vsi = AltimeterBaroVSI()
        vsi.reset(0.0)
        # +1 m/s² up accel for 1 second → vz should grow
        for _ in range(10):
            _, vz = vsi.update(baro_alt_m=0.0,
                               accel_z_m_s2=9.80665 + 1.0, dt=0.1)
        assert vz > 0.0


# ============================================================================
# BLEProximityMapper
# ============================================================================

class TestBLEProximityMapper:
    def test_init(self):
        m = BLEProximityMapper()
        assert m.beacons == []

    def test_rssi_to_dist_positive(self):
        m = BLEProximityMapper()
        assert m.rssi_to_distance(-65.0) > 0.0

    def test_dist_decreases_as_rssi_increases(self):
        m = BLEProximityMapper()
        d_far = m.rssi_to_distance(-90.0)
        d_near = m.rssi_to_distance(-50.0)
        assert d_near < d_far

    def test_add_beacon_stores(self):
        m = BLEProximityMapper()
        m.add_beacon("B1", (0.0, 0.0), -65.0)
        assert len(m.beacons) == 1

    def test_under_three_beacons_returns_none(self):
        m = BLEProximityMapper()
        m.add_beacon("B1", (0.0, 0.0), -65.0)
        m.add_beacon("B2", (5.0, 0.0), -65.0)
        assert m.trilaterate_position() is None

    def test_three_beacons_returns_tuple(self):
        m = BLEProximityMapper()
        m.add_beacon("B1", (0.0, 0.0), -65.0)
        m.add_beacon("B2", (5.0, 0.0), -65.0)
        m.add_beacon("B3", (0.0, 5.0), -65.0)
        out = m.trilaterate_position()
        assert isinstance(out, tuple)
        assert len(out) == 2

    def test_position_within_5m_for_ideal_grid(self):
        m = BLEProximityMapper()
        true = np.array([3.0, 4.0])
        anchors = [(0.0, 0.0), (10.0, 0.0), (0.0, 10.0), (10.0, 10.0)]
        for i, pos in enumerate(anchors):
            d = float(np.linalg.norm(np.asarray(pos) - true))
            # Invert path-loss model to produce matching RSSI
            rssi = -59.0 - 10.0 * 2.0 * math.log10(max(d, 1e-3))
            m.add_beacon(f"B{i}", pos, rssi)
        x, y = m.trilaterate_position()
        err = math.hypot(x - 3.0, y - 4.0)
        assert err < 5.0


# ============================================================================
# TemporalConvOdometry
# ============================================================================

class TestTemporalConvOdometry:
    def test_init(self):
        m = TemporalConvOdometry()
        assert m.seq_len == 16
        assert m.in_features == 6
        assert m.out_features == 3

    def test_causal_conv1d_output_shape(self):
        m = TemporalConvOdometry(in_features=6, hidden=8)
        x = np.random.RandomState(0).randn(16, 6)
        out = m.causal_conv1d(x, m.W1_a, m.W1_b, dilation=1)
        assert out.shape == (16, 8)

    def test_causal_property_no_future(self):
        # Modify a future timestep, output at t=0 must be unchanged
        m = TemporalConvOdometry(in_features=6, hidden=8, seed=1)
        x1 = np.random.RandomState(0).randn(16, 6)
        x2 = x1.copy()
        x2[10:] += 100.0
        o1 = m.causal_conv1d(x1, m.W1_a, m.W1_b, dilation=1)
        o2 = m.causal_conv1d(x2, m.W1_a, m.W1_b, dilation=1)
        assert np.allclose(o1[:10], o2[:10])

    def test_forward_returns_shape(self):
        m = TemporalConvOdometry()
        seq = np.random.RandomState(0).randn(16, 6)
        y = m.forward(seq)
        assert y.shape == (3,)

    def test_train_step_returns_scalar(self):
        m = TemporalConvOdometry()
        seq = np.random.RandomState(0).randn(16, 6)
        loss = m.train_step(seq, np.array([0.1, 0.2, 0.3]))
        assert isinstance(loss, float)

    def test_loss_decreases_after_training(self):
        m = TemporalConvOdometry(seed=42)
        rng = np.random.RandomState(0)
        seq = rng.randn(16, 6)
        target = np.array([0.5, -0.3, 0.1])
        loss0 = m.train_step(seq, target, lr=0.0)  # measure baseline
        for _ in range(50):
            m.train_step(seq, target, lr=0.05)
        loss1 = m.train_step(seq, target, lr=0.0)
        assert loss1 < loss0

    def test_causal_zero_pad_at_start(self):
        # At t=0 with dilation>=1, the prev tap is zero-padded
        m = TemporalConvOdometry(in_features=2, hidden=2, seed=0)
        # Build inputs where x[0] = 0 → output at t=0 should be tanh(0) = 0
        x = np.zeros((4, 2))
        out = m.causal_conv1d(x, m.W1_a[:2, :2], m.W1_b[:2, :2], dilation=1)
        assert np.allclose(out[0], 0.0)
