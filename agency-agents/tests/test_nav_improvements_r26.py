"""GODSKILL Navigation R26 — improvement-round tests."""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.satellite import (  # noqa: E402
    GLONASSReceiver,
    GalileoReceiver,
)
from agency.navigation.fusion import RTKProcessor  # noqa: E402
from agency.navigation.underwater import LBLAcousticPositioner  # noqa: E402
from agency.navigation.underground import CelestialNavigatorR26 as CelestialNavigator  # noqa: E402


# ============================================================================
# GLONASSReceiver
# ============================================================================

class TestGLONASSReceiver:
    def setup_method(self):
        self.r = GLONASSReceiver()
        self.r.add_satellite(1, k=0, pos_ecef=[20000e3, 0, 20000e3])
        self.r.add_satellite(2, k=3, pos_ecef=[0, 20000e3, 20000e3])
        self.r.add_satellite(3, k=-2, pos_ecef=[-20000e3, 0, 20000e3],
                             health=False)

    def test_f_l1_zero_channel(self):
        assert self.r.f_l1(0) == pytest.approx(1602e6)

    def test_f_l1_positive_channel(self):
        assert self.r.f_l1(2) == pytest.approx(1602e6 + 2 * 562.5e3)

    def test_f_l2_negative_channel(self):
        assert self.r.f_l2(-3) == pytest.approx(1246e6 - 3 * 437.5e3)

    def test_pseudorange_rate(self):
        v = self.r.pseudorange_rate(1, 100.0, 0.5)
        assert v == pytest.approx(200.0)

    def test_iono_free_l1_l2_returns_float(self):
        v = self.r.iono_free_l1_l2(1, 25e6, 25.05e6)
        assert isinstance(v, float)

    def test_visible_slots_excludes_unhealthy(self):
        v = self.r.visible_slots([0, 0, 0])
        assert 3 not in v

    def test_visible_slots_includes_healthy(self):
        v = self.r.visible_slots([0, 0, 0])
        assert 1 in v


# ============================================================================
# GalileoReceiver
# ============================================================================

class TestGalileoReceiver:
    def setup_method(self):
        self.g = GalileoReceiver()
        # Mix elevations so geometry matrix isn't rank-deficient
        for i, pos in enumerate([[20000e3, 0, 15000e3],
                                 [0, 20000e3, 25000e3],
                                 [-20000e3, 0, 18000e3],
                                 [0, -20000e3, 22000e3],
                                 [10000e3, 10000e3, 30000e3]]):
            self.g.add_satellite(i + 1, pos, health=True)
        self.g.add_satellite(99, [10000e3, 10000e3, 18000e3],
                             health=False)

    def test_iono_free_E1_E5a_float(self):
        v = self.g.iono_free_E1_E5a(25e6, 25.1e6)
        assert isinstance(v, float)

    def test_iono_free_E1_E5b_differs(self):
        a = self.g.iono_free_E1_E5a(25e6, 25.1e6)
        b = self.g.iono_free_E1_E5b(25e6, 25.1e6)
        assert a != b

    def test_cboc_chip_rate(self):
        assert self.g.cboc_code_freq() == pytest.approx(1.023e6)

    def test_elevation_mask_excludes_unhealthy(self):
        v = self.g.elevation_mask([0, 0, 0])
        assert 99 not in v

    def test_elevation_mask_includes_healthy(self):
        v = self.g.elevation_mask([0, 0, 0])
        assert 1 in v

    def test_pdop_finite(self):
        d = self.g.pdop([0, 0, 0])
        assert np.isfinite(d) and d != 999.0

    def test_pdop_999_too_few(self):
        g = GalileoReceiver()
        g.add_satellite(1, [20000e3, 0, 20000e3], health=True)
        assert g.pdop([0, 0, 0]) == 999.0


# ============================================================================
# RTKProcessor
# ============================================================================

class TestRTKProcessor:
    def setup_method(self):
        self.p = RTKProcessor()

    def test_double_difference(self):
        dd = self.p.double_difference(100.0, 105.0, 200.0, 210.0)
        # (105-100) - (210-200) = 5 - 10 = -5
        assert dd == pytest.approx(-5.0)

    def test_float_ambiguity_returns_float(self):
        n = self.p.float_ambiguity(120.5, 22.85)
        assert isinstance(n, float)

    def test_integer_ambiguity_rounds(self):
        assert self.p.integer_ambiguity(3.7) == 4
        assert self.p.integer_ambiguity(3.4) == 3

    def test_baseline_from_dd_shape(self):
        H = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1]],
                     dtype=float) / np.array([[1], [1], [1],
                                              [math.sqrt(3)]])
        b = np.array([1.0, 2.0, 3.0, 1.0])
        out = self.p.baseline_from_dd(b, H)
        assert out.shape == (3,)

    def test_position_fix_addition(self):
        ref = np.array([1000.0, 2000.0, 3000.0])
        bl = np.array([1.0, -1.0, 0.5])
        out = self.p.position_fix(ref, bl)
        assert np.allclose(out, [1001.0, 1999.0, 3000.5])

    def test_fixed_solution_rms_zero(self):
        assert self.p.fixed_solution_rms(np.zeros(5)) == pytest.approx(0.0)

    def test_lambda_l1_value(self):
        assert RTKProcessor.LAMBDA_L1 == pytest.approx(
            299792458.0 / 1575.42e6, rel=1e-9)


# ============================================================================
# LBLAcousticPositioner
# ============================================================================

class TestLBLAcousticPositioner:
    def setup_method(self):
        self.p = LBLAcousticPositioner()
        self.p.add_transponder("A", [0, 0, 0])
        self.p.add_transponder("B", [10, 0, 0])
        self.p.add_transponder("C", [0, 10, 0])
        self.p.add_transponder("D", [0, 0, 10])

    def test_add_transponder_stores(self):
        assert "A" in self.p._transponders

    def test_add_range_stores(self):
        self.p.add_range("A", 5.0)
        assert self.p._ranges["A"] == 5.0

    def test_trilaterate_returns_3vec(self):
        true = np.array([3.0, 4.0, 5.0])
        for tid, pos in [("A", [0, 0, 0]), ("B", [10, 0, 0]),
                         ("C", [0, 10, 0]), ("D", [0, 0, 10])]:
            self.p.add_range(tid, float(np.linalg.norm(np.asarray(pos)
                                                       - true)))
        out = self.p.trilaterate()
        assert out.shape == (3,)

    def test_trilaterate_accuracy(self):
        true = np.array([3.0, 4.0, 5.0])
        for tid, pos in [("A", [0, 0, 0]), ("B", [10, 0, 0]),
                         ("C", [0, 10, 0]), ("D", [0, 0, 10])]:
            self.p.add_range(tid, float(np.linalg.norm(np.asarray(pos)
                                                       - true)))
        out = self.p.trilaterate()
        assert float(np.linalg.norm(out - true)) < 1.0

    def test_range_residuals_zero_at_truth(self):
        true = np.array([3.0, 4.0, 5.0])
        for tid, pos in [("A", [0, 0, 0]), ("B", [10, 0, 0]),
                         ("C", [0, 10, 0])]:
            self.p.add_range(tid, float(np.linalg.norm(np.asarray(pos)
                                                       - true)))
        res = self.p.range_residuals(true)
        assert np.all(np.abs(res) < 1e-9)

    def test_gdop_finite_with_ranges(self):
        for tid in ("A", "B", "C", "D"):
            self.p.add_range(tid, 5.0)
        d = self.p.gdop()
        assert np.isfinite(d) and d != 999.0

    def test_gdop_999_too_few(self):
        p = LBLAcousticPositioner()
        p.add_transponder("A", [0, 0, 0])
        p.add_range("A", 5.0)
        assert p.gdop() == 999.0


# ============================================================================
# CelestialNavigator (R26 — underground.py variant)
# ============================================================================

class TestCelestialNavigator:
    def setup_method(self):
        self.c = CelestialNavigator()
        self.c.add_body("Vega", math.radians(279.0), math.radians(38.78))
        self.c.add_body("Sirius", math.radians(101.0), math.radians(-16.7))
        self.c.add_body("Polaris", math.radians(37.95), math.radians(89.26))

    def test_add_body_stores(self):
        assert len(self.c._bodies) == 3

    def test_body_los_unit_norm(self):
        v = self.c.body_los(math.radians(279.0), math.radians(38.78),
                            math.radians(45.0), math.radians(0.0),
                            math.radians(0.0))
        assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-9

    def test_altitude_in_range(self):
        a = self.c.altitude(math.radians(279.0), math.radians(38.78),
                            math.radians(45.0), math.radians(0.0),
                            math.radians(0.0))
        assert -math.pi / 2 <= a <= math.pi / 2

    def test_azimuth_in_range(self):
        z = self.c.azimuth(math.radians(279.0), math.radians(38.78),
                           math.radians(45.0), math.radians(0.0),
                           math.radians(0.0))
        assert -math.pi <= z <= math.pi

    def test_polaris_altitude_near_lat(self):
        # Polaris altitude ≈ observer latitude
        lat = math.radians(45.0)
        a = self.c.altitude(math.radians(37.95), math.radians(89.26),
                            lat, math.radians(0.0), math.radians(0.0))
        assert abs(a - lat) < math.radians(2.0)

    def test_best_pair_returns_two_names(self):
        pair = self.c.best_pair_for_fix(math.radians(45.0),
                                        math.radians(0.0),
                                        math.radians(0.0))
        assert pair is not None
        assert len(pair) == 2

    def test_best_pair_none_with_one_body(self):
        c = CelestialNavigator()
        c.add_body("A", 0.0, 0.0)
        assert c.best_pair_for_fix(0.0, 0.0, 0.0) is None
