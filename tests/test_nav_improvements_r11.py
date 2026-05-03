"""GODSKILL Navigation R11 — improvement-round tests.

Covers:
- IonosphericStormDetector
- InformationFilter
- ElevatorDetector
- TidalCurrentCompensator
- AdaptiveMapMatcher
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.satellite import IonosphericStormDetector  # noqa: E402
from agency.navigation.fusion import InformationFilter  # noqa: E402
from agency.navigation.indoor_inertial import ElevatorDetector  # noqa: E402
from agency.navigation.underwater import TidalCurrentCompensator  # noqa: E402
from agency.navigation.ai_enhance import AdaptiveMapMatcher  # noqa: E402


# ============================================================================
# IonosphericStormDetector
# ============================================================================

class TestIonosphericStormDetector:
    def test_init(self):
        d = IonosphericStormDetector()
        assert d is not None

    def test_roti_positive(self):
        d = IonosphericStormDetector()
        rng = np.random.RandomState(0)
        diffs = rng.normal(0, 1.0, 50)
        roti = d.compute_roti(diffs, dt=30.0)
        assert roti > 0.0

    def test_storm_detected_when_roti_high(self):
        d = IonosphericStormDetector()
        assert d.detect_storm(1.0, threshold=0.5) is True

    def test_no_storm_when_roti_low(self):
        d = IonosphericStormDetector()
        assert d.detect_storm(0.1, threshold=0.5) is False

    def test_klobuchar_returns_float(self):
        d = IonosphericStormDetector()
        alpha = [1.0e-8, 0.0, 0.0, 0.0]
        beta = [88000.0, 0.0, 0.0, 0.0]
        v = d.klobuchar_correction(alpha, beta,
                                   elevation_deg=45.0, azimuth_deg=90.0,
                                   lat_rad=math.radians(35.0),
                                   lon_rad=math.radians(139.0))
        assert isinstance(v, float)

    def test_klobuchar_delay_positive(self):
        d = IonosphericStormDetector()
        alpha = [2.0e-8, 1.0e-9, 0.0, 0.0]
        beta = [110000.0, 0.0, 0.0, 0.0]
        v = d.klobuchar_correction(alpha, beta, 30.0, 0.0,
                                   math.radians(0.0), math.radians(0.0))
        assert v > 0.0

    def test_storm_scale_factor_clamps(self):
        d = IonosphericStormDetector()
        assert d.storm_scale_factor(0) == pytest.approx(1.0)
        assert d.storm_scale_factor(20) == pytest.approx(2.5)
        assert d.storm_scale_factor(5) == pytest.approx(1.2)


# ============================================================================
# InformationFilter
# ============================================================================

class TestInformationFilter:
    def test_init_y_and_Y(self):
        f = InformationFilter(dim=6)
        assert f.y.shape == (6,)
        assert f.Y.shape == (6, 6)

    def test_predict_changes_Y(self):
        f = InformationFilter(dim=6)
        before = f.Y.copy()
        F = np.eye(6); F[0, 3] = 1.0
        Q = np.eye(6) * 0.1
        f.predict(F, Q)
        assert not np.allclose(before, f.Y)

    def test_update_increases_information(self):
        f = InformationFilter(dim=3)
        before_trace = float(np.trace(f.Y))
        H = np.eye(3)
        R = np.eye(3) * 4.0
        f.update(H, R, np.array([1.0, 2.0, 3.0]))
        after_trace = float(np.trace(f.Y))
        assert after_trace > before_trace

    def test_get_state_returns_pair(self):
        f = InformationFilter(dim=3)
        f.update(np.eye(3), np.eye(3), np.array([1.0, 2.0, 3.0]))
        x, P = f.get_state()
        assert x.shape == (3,)
        assert P.shape == (3, 3)

    def test_P_symmetric(self):
        f = InformationFilter(dim=3)
        f.update(np.eye(3), np.eye(3), np.array([1.0, 2.0, 3.0]))
        _, P = f.get_state()
        assert np.allclose(P, P.T, atol=1e-9)

    def test_merge_sums_information(self):
        f1 = InformationFilter(dim=3)
        f2 = InformationFilter(dim=3)
        f1.update(np.eye(3), np.eye(3), np.array([1.0, 0.0, 0.0]))
        f2.update(np.eye(3), np.eye(3), np.array([0.0, 1.0, 0.0]))
        merged = f1.merge(f2)
        assert np.allclose(merged.Y, f1.Y + f2.Y)
        assert np.allclose(merged.y, f1.y + f2.y)

    def test_merged_state_between_two(self):
        f1 = InformationFilter(dim=2)
        f2 = InformationFilter(dim=2)
        H = np.eye(2); R = np.eye(2)
        f1.update(H, R, np.array([0.0, 0.0]))
        f2.update(H, R, np.array([10.0, 10.0]))
        merged = f1.merge(f2)
        x, _ = merged.get_state()
        assert 0.0 <= x[0] <= 10.0


# ============================================================================
# ElevatorDetector
# ============================================================================

class TestElevatorDetector:
    def test_init(self):
        d = ElevatorDetector()
        assert d.accel_z_buf == []

    def test_floor_zero_at_alt_zero(self):
        d = ElevatorDetector()
        assert d.estimate_floor(0.0) == 0

    def test_floor_one_at_3m(self):
        d = ElevatorDetector()
        assert d.estimate_floor(3.0) == 1

    def test_floor_two_at_6m(self):
        d = ElevatorDetector()
        assert d.estimate_floor(6.0) == 2

    def test_detect_elevator_returns_bool(self):
        d = ElevatorDetector()
        # Inject elevator-like motion: sustained accel-z and rising baro
        for k in range(30):
            d.update(accel_z=9.80665 + 1.0,
                     baro_alt=k * 0.5, dt=0.1)
        out = d.detect_elevator(window=20)
        assert isinstance(out, bool)

    def test_detect_door_open_returns_bool(self):
        d = ElevatorDetector()
        # Synthesize jolt then quiet
        a = np.zeros((30, 3))
        a[:, 2] = 9.80665
        a[5, 2] = 9.80665 + 25.0   # >2g spike on top of gravity
        out = d.detect_door_open(a)
        assert isinstance(out, bool)

    def test_update_adds_to_buffer(self):
        d = ElevatorDetector()
        d.update(9.81, 1.0, 0.1)
        d.update(9.82, 1.1, 0.1)
        assert len(d.accel_z_buf) == 2


# ============================================================================
# TidalCurrentCompensator
# ============================================================================

class TestTidalCurrentCompensator:
    def test_init(self):
        c = TidalCurrentCompensator()
        assert c is not None

    def test_predict_current_returns_pair(self):
        c = TidalCurrentCompensator()
        out = c.predict_current(t=0.0, A=1.0, T=600.0, phi=0.0)
        assert len(out) == 2

    def test_compensate_changes_velocity(self):
        c = TidalCurrentCompensator()
        v = np.array([1.0, 0.0])
        out = c.compensate(v, t=150.0, A=0.5, T=600.0, phi=0.0)
        assert not np.allclose(out, v)

    def test_fit_tidal_model_returns_three(self):
        c = TidalCurrentCompensator()
        t = np.linspace(0, 1200, 60)
        v = 0.5 * np.sin(2 * math.pi * t / 600.0 + 0.7)
        A, T, phi = c.fit_tidal_model(t, v)
        assert isinstance(A, float)
        assert isinstance(T, float)
        assert isinstance(phi, float)

    def test_A_positive(self):
        c = TidalCurrentCompensator()
        t = np.linspace(0, 1200, 60)
        v = 0.5 * np.sin(2 * math.pi * t / 600.0)
        A, _, _ = c.fit_tidal_model(t, v)
        assert A > 0.0

    def test_T_positive(self):
        c = TidalCurrentCompensator()
        t = np.linspace(0, 1200, 60)
        v = 0.5 * np.sin(2 * math.pi * t / 600.0)
        _, T, _ = c.fit_tidal_model(t, v)
        assert T > 0.0

    def test_estimate_drift_returns_2vector(self):
        c = TidalCurrentCompensator()
        positions = [(0.0, 0.0), (1.0, 0.5), (2.0, 1.0)]
        times = [0.0, 1.0, 2.0]
        d = c.estimate_drift(positions, times)
        assert d.shape == (2,)


# ============================================================================
# AdaptiveMapMatcher
# ============================================================================

class TestAdaptiveMapMatcher:
    def test_init(self):
        m = AdaptiveMapMatcher()
        assert m.segments == {}

    def test_add_segment(self):
        m = AdaptiveMapMatcher()
        m.add_segment("S1", (0.0, 0.0), (10.0, 0.0))
        assert "S1" in m.segments

    def test_point_to_segment_dist_positive(self):
        m = AdaptiveMapMatcher()
        d = m.point_to_segment_dist((5.0, 3.0), (0.0, 0.0), (10.0, 0.0))
        assert d == pytest.approx(3.0)

    def test_dist_zero_for_point_on_segment(self):
        m = AdaptiveMapMatcher()
        d = m.point_to_segment_dist((5.0, 0.0), (0.0, 0.0), (10.0, 0.0))
        assert d == pytest.approx(0.0)

    def test_viterbi_returns_list(self):
        m = AdaptiveMapMatcher()
        m.add_segment("S1", (0.0, 0.0), (10.0, 0.0))
        m.add_segment("S2", (10.0, 0.0), (20.0, 0.0))
        path = m.viterbi([(5.0, 0.5), (15.0, 0.3)])
        assert isinstance(path, list)

    def test_viterbi_length_matches_obs(self):
        m = AdaptiveMapMatcher()
        m.add_segment("S1", (0.0, 0.0), (10.0, 0.0))
        m.add_segment("S2", (10.0, 0.0), (20.0, 0.0))
        obs = [(5.0, 0.5), (15.0, 0.3), (8.0, 0.0)]
        path = m.viterbi(obs)
        assert len(path) == len(obs)

    def test_emission_higher_for_close_point(self):
        m = AdaptiveMapMatcher()
        m.add_segment("S1", (0.0, 0.0), (10.0, 0.0))
        e_close = m._emission_logprob((5.0, 0.1), "S1")
        e_far = m._emission_logprob((5.0, 50.0), "S1")
        assert e_close > e_far
