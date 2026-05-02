"""GODSKILL Nav v11 — Round 1 improvement tests.

Covers:
  * RTKCorrector: correction application, double-difference math,
    ambiguity resolution stub, SNR-drop spoofing, position-jump spoofing.
  * AdaptiveEKF: innovation tracking, Sage-Husa noise adaptation,
    χ² outlier rejection, RAIM HPL/integrity flag.
"""
from __future__ import annotations

import os
import sys

# Add runtime/ to sys.path so `agency.*` is importable when this file is
# invoked from the worktree root (where `agency` is not a top-level package).
_THIS = os.path.abspath(os.path.dirname(__file__))
_RUNTIME = os.path.abspath(os.path.join(_THIS, "..", "runtime"))
if _RUNTIME not in sys.path:
    sys.path.insert(0, _RUNTIME)

import pytest  # noqa: E402

from agency.navigation.satellite import (  # noqa: E402
    FIX_GPS,
    FIX_RTK_FIXED,
    FIX_RTK_FLOAT,
    RTKCorrection,
    RTKCorrector,
)
from agency.navigation.fusion import (  # noqa: E402
    CHI2_3_95,
    AdaptiveEKF,
    RAIMResult,
)


# ---------------------------------------------------------------------------
# RTKCorrector
# ---------------------------------------------------------------------------

def _rover_obs(n_sats: int = 4, snr: float = 40.0,
               lat: float = 37.0, lon: float = -122.0, alt: float = 10.0) -> dict:
    return {
        "lat": lat,
        "lon": lon,
        "alt": alt,
        "satellites": [
            {"id": f"G{i:02d}", "snr_db": snr, "phase": float(i)}
            for i in range(1, n_sats + 1)
        ],
    }


class TestRTKCorrector:

    def test_apply_corrections_returns_rtk_fixed_with_4_sats(self) -> None:
        rtk = RTKCorrector()
        result = rtk.apply_rtk_corrections(
            (37.001, -122.001, 11.0),
            _rover_obs(n_sats=4),
            t_now=1000.0,
        )
        assert isinstance(result, RTKCorrection)
        assert result.fix_quality == FIX_RTK_FIXED
        assert result.horizontal_m <= 0.02 + 1e-6  # ±2 cm
        assert result.is_spoofed is False

    def test_apply_corrections_returns_rtk_float_with_3_sats(self) -> None:
        rtk = RTKCorrector()
        result = rtk.apply_rtk_corrections(
            (37.0, -122.0, 0.0),
            _rover_obs(n_sats=3),
            t_now=1000.0,
        )
        assert result.fix_quality == FIX_RTK_FLOAT
        assert 0.05 < result.horizontal_m < 1.0

    def test_apply_corrections_falls_back_to_gps_with_too_few_sats(self) -> None:
        rtk = RTKCorrector()
        result = rtk.apply_rtk_corrections(
            (37.0, -122.0, 0.0),
            _rover_obs(n_sats=2),
            t_now=1000.0,
        )
        assert result.fix_quality == FIX_GPS
        assert result.horizontal_m > 0.5

    def test_double_difference_cancels_clock_biases(self) -> None:
        # If both base and rover have a common clock bias on each sat, DD
        # should still produce the true geometric component.
        # Synthetic numbers: rover_a=10, base_a=2 → SD_a=8
        #                   rover_b=4,  base_b=1 → SD_b=3
        # DD = 8 - 3 = 5
        dd = RTKCorrector.double_difference(2.0, 1.0, 10.0, 4.0)
        assert dd == pytest.approx(5.0, abs=1e-9)

    def test_resolve_ambiguity_lambda_rounds_to_integer(self) -> None:
        assert RTKCorrector.resolve_ambiguity_lambda(3.49) == 3
        assert RTKCorrector.resolve_ambiguity_lambda(3.51) == 4
        assert RTKCorrector.resolve_ambiguity_lambda(-2.4) == -2
        # The result type must be exactly int, not numpy or float.
        assert isinstance(RTKCorrector.resolve_ambiguity_lambda(0.0), int)

    def test_snr_drop_flags_spoofing(self) -> None:
        rtk = RTKCorrector()
        # First epoch establishes baseline at 45 dB.
        rtk.apply_rtk_corrections(
            (37.0, -122.0, 0.0),
            _rover_obs(n_sats=4, snr=45.0),
            t_now=1000.0,
        )
        # Next epoch drops to 25 dB on every sat → 20 dB drop > 15 dB.
        result = rtk.apply_rtk_corrections(
            (37.0, -122.0, 0.0),
            _rover_obs(n_sats=4, snr=25.0),
            t_now=1000.5,
        )
        assert result.is_spoofed is True
        assert "snr drop" in result.spoof_reason

    def test_position_jump_flags_spoofing(self) -> None:
        rtk = RTKCorrector()
        rtk.apply_rtk_corrections(
            (37.0, -122.0, 0.0),
            _rover_obs(n_sats=4, lat=37.0, lon=-122.0),
            t_now=1000.0,
        )
        # Jump ~111 m north (~0.001 deg lat) within 0.5 s → > 50 m/1 s.
        result = rtk.apply_rtk_corrections(
            (37.0, -122.0, 0.0),
            _rover_obs(n_sats=4, lat=37.001, lon=-122.0),
            t_now=1000.5,
        )
        assert result.is_spoofed is True
        assert "position jump" in result.spoof_reason

    def test_spoofed_result_does_not_apply_rtk_correction(self) -> None:
        rtk = RTKCorrector()
        rtk.apply_rtk_corrections(
            (37.0, -122.0, 0.0),
            _rover_obs(n_sats=4, snr=45.0),
            t_now=1000.0,
        )
        result = rtk.apply_rtk_corrections(
            (37.0, -122.0, 0.0),
            _rover_obs(n_sats=4, snr=25.0),
            t_now=1000.5,
        )
        # Even though we have 4 sats, the spoofed path returns FIX_GPS,
        # not FIX_RTK_FIXED, so downstream consumers see degraded accuracy.
        assert result.fix_quality == FIX_GPS
        assert result.horizontal_m > 1.0


# ---------------------------------------------------------------------------
# AdaptiveEKF
# ---------------------------------------------------------------------------

class TestAdaptiveEKF:

    def test_construct_initialises_diagonals_and_counters(self) -> None:
        ekf = AdaptiveEKF(q=2.0, r=4.0)
        assert ekf._R_diag == [4.0, 4.0, 4.0]
        assert ekf.outliers_rejected == 0
        assert ekf.updates_accepted == 0

    def test_reasonable_innovation_is_accepted(self) -> None:
        ekf = AdaptiveEKF(q=1.0, r=5.0)
        ekf.predict(1.0)
        accepted = ekf.update([0.5, 0.5, 0.0])
        assert accepted is True
        assert ekf.updates_accepted == 1
        assert ekf.outliers_rejected == 0
        # Innovation sequence should be tracked for adaptation.
        assert ekf.last_innovation is not None
        assert len(ekf.last_innovation) == 3

    def test_outlier_innovation_is_rejected_by_chi_square(self) -> None:
        ekf = AdaptiveEKF(q=1.0, r=5.0)
        ekf.predict(1.0)
        # Hugely off-axis measurement → ts >> 7.815.
        rejected = ekf.update([1000.0, 0.0, 0.0])
        assert rejected is False
        assert ekf.outliers_rejected == 1
        assert ekf.updates_accepted == 0
        assert ekf.last_test_statistic > CHI2_3_95

    def test_chi_square_threshold_constant_value(self) -> None:
        # Sanity-check: χ²(3, 0.95) = 7.815 (from standard tables).
        assert CHI2_3_95 == pytest.approx(7.815, abs=1e-3)

    def test_innovation_sequence_drives_r_adaptation(self) -> None:
        ekf = AdaptiveEKF(q=1.0, r=5.0, forgetting=0.5)
        baseline = list(ekf._R_diag)
        ekf.predict(1.0)
        # Several consistent ~2.0 innovations should pull R upward
        # (squared innov = 4.0) toward something larger than the baseline.
        for _ in range(10):
            ekf.predict(0.1)
            ekf.update([2.0, 2.0, 2.0])
        # At least one diagonal must have moved off the initial value.
        assert ekf._R_diag != baseline

    def test_raim_returns_structured_result(self) -> None:
        ekf = AdaptiveEKF()
        ekf.predict(1.0)
        ekf.update([0.1, 0.1, 0.0])
        result = ekf.raim(hal_m=50.0)
        assert isinstance(result, RAIMResult)
        assert result.threshold == CHI2_3_95
        assert result.horizontal_protection_level_m >= 0.0

    def test_raim_integrity_passes_below_alarm_limit(self) -> None:
        ekf = AdaptiveEKF()
        # Squeeze covariance down so HPL stays small.
        for i in range(6):
            ekf.P[i][i] = 0.01
        result = ekf.raim(hal_m=50.0)
        assert result.integrity_ok is True
        assert result.horizontal_protection_level_m < 50.0

    def test_raim_integrity_fails_when_covariance_exceeds_limit(self) -> None:
        ekf = AdaptiveEKF()
        # Inflate covariance way past the 50 m alarm limit.
        ekf.P[0][0] = 1000.0
        ekf.P[1][1] = 1000.0
        result = ekf.raim(hal_m=50.0)
        assert result.integrity_ok is False
        assert result.horizontal_protection_level_m > 50.0
