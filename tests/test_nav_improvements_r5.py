"""GODSKILL Nav v11 — Round 5 improvement tests.

Covers:
  * VisualPlaceRecognition:  BoW build, descriptor extraction, query rank,
                             loop-closure threshold filter, vocab refine stub.
  * TightlyCoupledGNSSIMU:   17-state predict, pseudorange + Doppler updates,
                             RAIM-like integrity check, state extraction.
  * AcousticModemNav:        TWTT slant range, TDOA fix convergence on a
                             4-hydrophone star, Doppler radial velocity sign,
                             multipath median+sigma rejection.
  * MagnetometerSLAM:        record + IDW build, localize returns nearby pos,
                             update_map blending, online append.
"""

from __future__ import annotations

import math
import os
import sys

_THIS = os.path.abspath(os.path.dirname(__file__))
_RUNTIME = os.path.abspath(os.path.join(_THIS, "..", "runtime"))
if _RUNTIME not in sys.path:
    sys.path.insert(0, _RUNTIME)

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from agency.navigation.indoor_slam import VisualPlaceRecognition  # noqa: E402
from agency.navigation.satellite import TightlyCoupledGNSSIMU  # noqa: E402
from agency.navigation.underwater import AcousticModemNav  # noqa: E402
from agency.navigation.underground import MagnetometerSLAM  # noqa: E402


# ---------------------------------------------------------------------------
# VisualPlaceRecognition
# ---------------------------------------------------------------------------


def _synthetic_image(seed: int, size: int = 64) -> np.ndarray:
    """Deterministic synthetic 2-D grayscale image for VPR tests."""
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 256, size=(size, size), dtype=np.uint8)
    # Add a few sharp corners to make FAST happy.
    img[8:12, 8:12] = 240
    img[40:44, 40:44] = 20
    return img


def test_vpr_construct_default_dims():
    vpr = VisualPlaceRecognition()
    assert vpr.vocab_size == 256
    assert vpr._vocab.shape == (256, 64)


def test_vpr_extract_descriptor_returns_histogram():
    vpr = VisualPlaceRecognition(vocab_size=64, seed=0)
    img = _synthetic_image(seed=1)
    bow = vpr.extract_descriptor(img)
    assert bow.shape == (64,)
    # L1 norm = 1 (or 0 if no features were detected — empty image).
    s = float(bow.sum())
    assert s == pytest.approx(1.0, abs=1e-6) or s == 0.0


def test_vpr_add_to_database_grows():
    vpr = VisualPlaceRecognition(vocab_size=64, seed=0)
    vpr.add_to_database("a", _synthetic_image(seed=1))
    vpr.add_to_database("b", _synthetic_image(seed=2))
    assert vpr.db_size == 2


def test_vpr_query_returns_top_k():
    vpr = VisualPlaceRecognition(vocab_size=64, seed=0)
    for k in range(4):
        vpr.add_to_database(k, _synthetic_image(seed=k))
    res = vpr.query(_synthetic_image(seed=0), top_k=3)
    assert len(res) == 3
    # Scores should be sorted descending.
    scores = [s for _, s in res]
    assert scores == sorted(scores, reverse=True)


def test_vpr_query_self_match_top_score_is_highest():
    vpr = VisualPlaceRecognition(vocab_size=64, seed=0)
    vpr.add_to_database("self", _synthetic_image(seed=42))
    vpr.add_to_database("other", _synthetic_image(seed=99))
    res = vpr.query(_synthetic_image(seed=42), top_k=2)
    assert res[0][0] == "self"


def test_vpr_loop_closure_threshold_filters():
    vpr = VisualPlaceRecognition(vocab_size=64, seed=0)
    vpr.add_to_database("self", _synthetic_image(seed=42))
    out = vpr.loop_closure_candidates(_synthetic_image(seed=42),
                                      threshold=0.99)
    # All retained candidates must be >= threshold (or list is empty).
    for _, s in out:
        assert s >= 0.99


def test_vpr_query_empty_db_returns_empty():
    vpr = VisualPlaceRecognition()
    assert vpr.query(_synthetic_image(seed=1), top_k=3) == []


def test_vpr_refine_vocabulary_no_op_on_empty():
    vpr = VisualPlaceRecognition(vocab_size=8, seed=0)
    snapshot = vpr._vocab.copy()
    vpr.refine_vocabulary(np.zeros((0, 64), dtype=np.uint8))
    assert np.array_equal(vpr._vocab, snapshot)


# ---------------------------------------------------------------------------
# TightlyCoupledGNSSIMU
# ---------------------------------------------------------------------------


def test_tc_initial_state_zeros():
    tc = TightlyCoupledGNSSIMU()
    assert tc.x.shape == (17,)
    assert np.allclose(tc.x, 0.0)
    assert tc.P.shape == (17, 17)


def test_tc_predict_zero_input_only_gravity_drift():
    tc = TightlyCoupledGNSSIMU()
    tc.predict(np.zeros(3), np.zeros(3), 1.0)
    # Gravity adds +9.80665 m/s velocity along z, position 0.5*g.
    assert tc.x[5] == pytest.approx(9.80665, rel=1e-6)
    assert tc.x[2] == pytest.approx(0.5 * 9.80665, rel=1e-6)


def test_tc_pseudorange_update_reduces_clock_bias_residual():
    tc = TightlyCoupledGNSSIMU()
    sv = np.array([10_000.0, 0.0, 0.0])
    rho = float(np.linalg.norm(sv))  # zero clock bias prediction
    out = tc.update_pseudorange(sv, rho, sv_clock_bias=0.0, sigma=2.0)
    assert out["accepted"] is True
    assert abs(out["residual"]) < 1.0


def test_tc_pseudorange_with_clock_bias_nonzero_residual():
    tc = TightlyCoupledGNSSIMU()
    sv = np.array([10_000.0, 0.0, 0.0])
    out = tc.update_pseudorange(sv, 10_500.0, sv_clock_bias=0.0, sigma=2.0)
    assert out["accepted"] is True
    # State clock bias should have shifted toward the observed offset.
    assert abs(tc.x[15]) > 0.0


def test_tc_doppler_update_changes_clock_drift():
    tc = TightlyCoupledGNSSIMU()
    tc.x[3:6] = np.array([10.0, 0.0, 0.0])  # nonzero velocity
    snap = tc.x[16]
    out = tc.update_doppler(np.array([20.0, 0.0, 0.0]),
                            doppler_hz=1000.0, freq_hz=1_575_420_000.0)
    assert out["accepted"] is True
    assert tc.x[16] != snap


def test_tc_integrity_check_no_residuals():
    tc = TightlyCoupledGNSSIMU()
    out = tc.integrity_check()
    assert out["integrity_ok"] is True
    assert out["n_residuals"] == 0


def test_tc_integrity_check_after_updates():
    tc = TightlyCoupledGNSSIMU()
    sv = np.array([10_000.0, 0.0, 0.0])
    for _ in range(5):
        tc.update_pseudorange(sv, 10_001.0, sv_clock_bias=0.0, sigma=2.0)
    out = tc.integrity_check()
    assert out["n_residuals"] >= 1
    assert out["rms"] >= 0.0


def test_tc_state_dict_contains_all_blocks():
    tc = TightlyCoupledGNSSIMU()
    s = tc.state()
    for k in ("position", "velocity", "attitude", "accel_bias",
              "gyro_bias", "clock_bias_m", "clock_drift_mps"):
        assert k in s


# ---------------------------------------------------------------------------
# AcousticModemNav
# ---------------------------------------------------------------------------


def test_acoustic_two_way_ranging_basic():
    r = AcousticModemNav.two_way_ranging(0.0, 1.0, sound_speed=1500.0)
    assert r == pytest.approx(750.0, rel=1e-9)


def test_acoustic_two_way_ranging_negative_dt_returns_zero():
    r = AcousticModemNav.two_way_ranging(2.0, 1.0)
    assert r == 0.0


def test_acoustic_tdoa_fix_converges_with_4_hydrophones():
    hp = np.array([
        [0.0, 0.0, 0.0],
        [100.0, 0.0, 0.0],
        [0.0, 100.0, 0.0],
        [0.0, 0.0, 100.0],
    ])
    true_pos = np.array([30.0, 40.0, 5.0])
    c = 1500.0
    t0 = 1.0
    arrivals = np.array([
        t0 + np.linalg.norm(hp[i] - true_pos) / c for i in range(4)
    ])
    out = AcousticModemNav.tdoa_fix(hp, arrivals, sound_speed=c)
    err = float(np.linalg.norm(out["position"] - true_pos))
    assert err < 0.5
    assert out["converged"] is True


def test_acoustic_tdoa_fix_too_few_hydrophones():
    hp = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]])
    out = AcousticModemNav.tdoa_fix(hp, np.array([0.0, 1.0]))
    assert out["converged"] is False


def test_acoustic_doppler_velocity_zero_when_freqs_match():
    v = AcousticModemNav.doppler_velocity(10_000.0, 10_000.0, 1500.0)
    assert v == pytest.approx(0.0, abs=1e-9)


def test_acoustic_doppler_velocity_sign_when_freq_drops():
    # f_obs < f_carrier → positive (moving away).
    v = AcousticModemNav.doppler_velocity(10_000.0, 9_900.0, 1500.0)
    assert v > 0.0


def test_acoustic_multipath_filter_replaces_outlier():
    arr = np.array([10.0, 10.1, 9.9, 100.0, 10.0, 9.95])
    out = AcousticModemNav.multipath_filter(arr, window=5,
                                            sigma_threshold=2.0)
    # Outlier should be pulled toward the local median.
    assert out[3] < 50.0


# ---------------------------------------------------------------------------
# MagnetometerSLAM
# ---------------------------------------------------------------------------


def test_mag_slam_record_grows_count():
    ms = MagnetometerSLAM()
    ms.record_measurement([0.0, 0.0], [100.0, 0.0, 0.0])
    ms.record_measurement([1.0, 0.0], [110.0, 0.0, 0.0])
    assert ms.n_samples == 2


def test_mag_slam_build_anomaly_map_shape():
    ms = MagnetometerSLAM()
    for x in range(0, 5):
        for y in range(0, 5):
            ms.record_measurement([float(x), float(y)],
                                  [50.0 + x * 10.0, 0.0, 0.0])
    grid = ms.build_anomaly_map(grid_resolution=1.0)
    assert grid.ndim == 2
    assert grid.shape[0] >= 5 and grid.shape[1] >= 5


def test_mag_slam_localize_returns_nearby_position():
    ms = MagnetometerSLAM()
    for x in range(0, 10):
        ms.record_measurement([float(x), 0.0], [50.0 + x * 5.0, 0.0, 0.0])
    ms.build_anomaly_map(grid_resolution=1.0)
    out = ms.localize([75.0, 0.0, 0.0], search_radius=5.0)
    assert out["matched"] is True
    # 75 nT corresponds to x=5 in our linear ramp.
    assert abs(out["position"][0] - 5.0) < 2.5


def test_mag_slam_update_map_blends_close_sample():
    ms = MagnetometerSLAM()
    ms.record_measurement([0.0, 0.0], [100.0, 0.0, 0.0])
    ms.update_map([0.1, 0.0], [200.0, 0.0, 0.0], learning_rate=0.5)
    # No new sample appended — close enough to existing.
    assert ms.n_samples == 1
    # Magnitude blended between 100 and 200.
    blended = ms._samples[0]["magnitude"]
    assert 100.0 < blended < 200.0


def test_mag_slam_update_map_appends_far_sample():
    ms = MagnetometerSLAM()
    ms.record_measurement([0.0, 0.0], [100.0, 0.0, 0.0])
    ms.update_map([10.0, 0.0], [200.0, 0.0, 0.0], learning_rate=0.5)
    assert ms.n_samples == 2


def test_mag_slam_localize_empty_returns_unmatched():
    ms = MagnetometerSLAM()
    out = ms.localize([1.0, 0.0, 0.0])
    assert out["matched"] is False
