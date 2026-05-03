"""GODSKILL Navigation R28 — improvement-round tests."""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.indoor_slam import (  # noqa: E402
    WiFiRTTPositioner,
    BLEBeaconPositioner,
)
from agency.navigation.indoor_inertial import (  # noqa: E402
    PedestrianDeadReckoning,
    UWBTwoWayRanging,
)
from agency.navigation.underwater import SBLAcousticPositioner  # noqa: E402


C_LIGHT = 299792458.0


# ============================================================================
# WiFiRTTPositioner
# ============================================================================

class TestWiFiRTTPositioner:
    def setup_method(self):
        self.w = WiFiRTTPositioner()
        self.w.add_ap("A", [0, 0])
        self.w.add_ap("B", [10, 0])
        self.w.add_ap("C", [0, 10])
        self.w.add_ap("D", [10, 10])

    def test_rtt_to_range_formula(self):
        # 100 ns RTT → d = c · 100e-9 / 2 ≈ 14.99 m
        d = self.w.rtt_to_range(100.0)
        assert abs(d - C_LIGHT * 100e-9 / 2.0) < 1e-9

    def test_add_measurement_stores(self):
        self.w.add_measurement("A", 50.0)
        assert "A" in self.w._meas

    def test_locate_returns_2vec(self):
        true = np.array([3.0, 4.0])
        for ap, pos in [("A", [0, 0]), ("B", [10, 0]),
                        ("C", [0, 10]), ("D", [10, 10])]:
            d = float(np.linalg.norm(np.asarray(pos, dtype=float) - true))
            rtt = 2.0 * d / C_LIGHT * 1e9
            self.w.add_measurement(ap, rtt)
        out = self.w.locate()
        assert out.shape == (2,)

    def test_locate_accuracy(self):
        true = np.array([3.0, 4.0])
        for ap, pos in [("A", [0, 0]), ("B", [10, 0]),
                        ("C", [0, 10]), ("D", [10, 10])]:
            d = float(np.linalg.norm(np.asarray(pos, dtype=float) - true))
            rtt = 2.0 * d / C_LIGHT * 1e9
            self.w.add_measurement(ap, rtt)
        out = self.w.locate()
        assert float(np.linalg.norm(out - true)) < 0.5

    def test_locate_too_few_returns_zero(self):
        self.w.add_measurement("A", 100.0)
        out = self.w.locate()
        assert np.allclose(out, 0.0)

    def test_range_residuals_zero_at_truth(self):
        true = np.array([3.0, 4.0])
        for ap, pos in [("A", [0, 0]), ("B", [10, 0]), ("C", [0, 10])]:
            d = float(np.linalg.norm(np.asarray(pos, dtype=float) - true))
            rtt = 2.0 * d / C_LIGHT * 1e9
            self.w.add_measurement(ap, rtt)
        res = self.w.range_residuals(true)
        assert np.all(np.abs(res) < 1e-6)

    def test_clear_measurements(self):
        self.w.add_measurement("A", 100.0)
        self.w.clear_measurements()
        assert len(self.w._meas) == 0
        assert len(self.w.aps) == 4


# ============================================================================
# BLEBeaconPositioner
# ============================================================================

class TestBLEBeaconPositioner:
    def setup_method(self):
        self.b = BLEBeaconPositioner()
        for bid, pos in [("A", [0, 0]), ("B", [10, 0]),
                         ("C", [0, 10]), ("D", [10, 10])]:
            self.b.add_beacon(bid, pos, tx_power_dbm=-59.0)

    def test_rssi_to_range_at_1m(self):
        d = self.b.rssi_to_range(-59.0, -59.0)
        assert d == pytest.approx(1.0)

    def test_proximity_immediate(self):
        # very strong RSSI → immediate
        z = self.b.proximity_zone(-30.0)
        assert z == "immediate"

    def test_proximity_far(self):
        z = self.b.proximity_zone(-90.0)
        assert z == "far"

    def test_add_rssi_stores(self):
        self.b.add_rssi("A", -65.0)
        assert "A" in self.b._rssi

    def test_locate_returns_2vec(self):
        true = np.array([3.0, 4.0])
        for bid, pos in [("A", [0, 0]), ("B", [10, 0]),
                         ("C", [0, 10]), ("D", [10, 10])]:
            d = float(np.linalg.norm(np.asarray(pos, dtype=float) - true))
            rssi = -59.0 - 20.0 * math.log10(max(d, 1e-3))
            self.b.add_rssi(bid, rssi)
        out = self.b.locate()
        assert out.shape == (2,)

    def test_locate_accuracy(self):
        true = np.array([3.0, 4.0])
        for bid, pos in [("A", [0, 0]), ("B", [10, 0]),
                         ("C", [0, 10]), ("D", [10, 10])]:
            d = float(np.linalg.norm(np.asarray(pos, dtype=float) - true))
            rssi = -59.0 - 20.0 * math.log10(max(d, 1e-3))
            self.b.add_rssi(bid, rssi)
        out = self.b.locate()
        assert float(np.linalg.norm(out - true)) < 1.0

    def test_locate_too_few_returns_zero(self):
        self.b.add_rssi("A", -60.0)
        self.b.add_rssi("B", -65.0)
        out = self.b.locate()
        assert np.allclose(out, 0.0)


# ============================================================================
# PedestrianDeadReckoning
# ============================================================================

class TestPedestrianDeadReckoning:
    def setup_method(self):
        self.p = PedestrianDeadReckoning(step_length_m=0.7)

    def test_detect_step_true_for_peak(self):
        # Window with a clear peak above mean+1.2*std
        a = np.array([9.8, 9.85, 9.9, 12.0, 9.85, 9.8])
        assert self.p.detect_step(a) is True

    def test_detect_step_false_flat(self):
        a = np.full(20, 9.81)
        assert self.p.detect_step(a) is False

    def test_weinberg_step_length_positive(self):
        a = np.array([9.0, 11.0, 8.5, 10.5])
        L = self.p.weinberg_step_length(a)
        assert L > 0.0

    def test_update_heading_integrates(self):
        h = self.p.update_heading(0.0, 1.0, 0.5)
        assert h == pytest.approx(0.5)

    def test_step_position_advances(self):
        out = self.p.step_position([0.0, 0.0], 0.0, step_len=0.7)
        assert out[0] == pytest.approx(0.7)
        assert out[1] == pytest.approx(0.0, abs=1e-9)

    def test_dead_reckon_returns_array(self):
        rng = np.random.RandomState(0)
        accel_windows = [9.81 + 2.0 * np.sin(np.linspace(0, np.pi, 10))
                         for _ in range(5)]
        gyro_windows = [np.zeros(10) for _ in range(5)]
        traj = self.p.dead_reckon(accel_windows, gyro_windows,
                                  dt_s=0.1, initial_pos=[0.0, 0.0],
                                  initial_heading=0.0)
        assert traj.shape[1] == 2

    def test_dead_reckon_starts_at_initial(self):
        traj = self.p.dead_reckon([], [], dt_s=0.1,
                                  initial_pos=[5.0, -3.0],
                                  initial_heading=0.0)
        assert np.allclose(traj[0], [5.0, -3.0])


# ============================================================================
# UWBTwoWayRanging
# ============================================================================

class TestUWBTwoWayRanging:
    def setup_method(self):
        self.u = UWBTwoWayRanging()
        self.u.add_anchor("A", [0, 0, 0])
        self.u.add_anchor("B", [10, 0, 0])
        self.u.add_anchor("C", [0, 10, 0])
        self.u.add_anchor("D", [0, 0, 10])

    def test_twr_range_formula(self):
        # 100 ns ToF → d ≈ 30 m (one-way TWR after divide-by-2 = ~15m)
        # Per spec: d = C * tof_ns * 1e-9 (no /2)
        d = self.u.twr_range(100.0)
        assert d == pytest.approx(C_LIGHT * 100e-9)

    def test_twr_range_clamped_zero(self):
        d = self.u.twr_range(-1.0)
        assert d == 0.0

    def test_add_tof_stores(self):
        self.u.add_tof("A", 50.0)
        assert "A" in self.u._tof

    def test_trilaterate_3d_shape(self):
        true = np.array([3.0, 4.0, 5.0])
        for aid, pos in [("A", [0, 0, 0]), ("B", [10, 0, 0]),
                         ("C", [0, 10, 0]), ("D", [0, 0, 10])]:
            d = float(np.linalg.norm(np.asarray(pos, dtype=float) - true))
            tof = d / C_LIGHT * 1e9
            self.u.add_tof(aid, tof)
        out = self.u.trilaterate_3d()
        assert out.shape == (3,)

    def test_trilaterate_3d_accuracy(self):
        true = np.array([3.0, 4.0, 5.0])
        for aid, pos in [("A", [0, 0, 0]), ("B", [10, 0, 0]),
                         ("C", [0, 10, 0]), ("D", [0, 0, 10])]:
            d = float(np.linalg.norm(np.asarray(pos, dtype=float) - true))
            tof = d / C_LIGHT * 1e9
            self.u.add_tof(aid, tof)
        out = self.u.trilaterate_3d()
        assert float(np.linalg.norm(out - true)) < 0.5

    def test_too_few_anchors_returns_zero(self):
        self.u.add_tof("A", 50.0)
        out = self.u.trilaterate_3d()
        assert np.allclose(out, 0.0)

    def test_range_std_propagates(self):
        # 1 ns std → C * 1e-9 ≈ 0.3 m
        s = self.u.range_std(1.0)
        assert s == pytest.approx(C_LIGHT * 1e-9)


# ============================================================================
# SBLAcousticPositioner
# ============================================================================

class TestSBLAcousticPositioner:
    def setup_method(self):
        self.s = SBLAcousticPositioner()
        self.s.add_transducer("F", [0.0, 0.0, 0.0])
        self.s.add_transducer("S", [-1.0, 0.0, 0.0])
        self.s.add_transducer("P", [0.0, -1.0, 0.0])

    def test_add_transducer_stores(self):
        assert "F" in self.s._transducers

    def test_tdoa_formula(self):
        # 0.001 s · 1500 m/s = 1.5 m range diff
        v = self.s.tdoa("F", "S", 0.001)
        assert v == pytest.approx(1.5)

    def test_add_tdoa_stores(self):
        self.s.add_tdoa("F", "S", 0.0)
        assert len(self.s._tdoa) == 1

    def test_locate_returns_3vec(self):
        # Add a few zero-TDOA measurements (target equidistant from pairs)
        self.s.add_tdoa("F", "S", 0.0)
        self.s.add_tdoa("F", "P", 0.0)
        out = self.s.locate()
        assert out.shape == (3,)

    def test_bearing_in_range(self):
        b = self.s.bearing([1.0, 1.0, 5.0])
        assert -math.pi <= b <= math.pi

    def test_bearing_zero_for_pure_x(self):
        b = self.s.bearing([5.0, 0.0, 10.0])
        assert b == pytest.approx(0.0, abs=1e-9)

    def test_slant_range_correct(self):
        r = self.s.slant_range([3.0, 4.0, 0.0])
        assert r == pytest.approx(5.0)
