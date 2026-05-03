"""GODSKILL Nav v11 — Round 2 improvement tests.

Covers:
  * ParticleFilter:  adaptive resampling, roughening, convergence metric,
    MapMatchingParticle map-matching constraints.
  * Indoor PDR:      SHOEstimator zero-velocity update detection,
                     BarometricAltimeter pressure→altitude + floor detection.
  * HeadingCorrector calibration via least-squares ellipsoid fit.
"""

from __future__ import annotations

import math
import os
import random
import sys

# Add runtime/ to sys.path so `agency.*` is importable when this file is run
# from the worktree root (where `agency` is not a top-level package).
_THIS = os.path.abspath(os.path.dirname(__file__))
_RUNTIME = os.path.abspath(os.path.join(_THIS, "..", "runtime"))
if _RUNTIME not in sys.path:
    sys.path.insert(0, _RUNTIME)

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from agency.navigation.fusion import (  # noqa: E402
    MapMatchingParticle,
    ParticleFilter,
)
from agency.navigation.indoor_inertial import (  # noqa: E402
    BarometricAltimeter,
    HeadingCorrector,
    SHOEstimator,
)


# ---------------------------------------------------------------------------
# ParticleFilter — adaptive resampling
# ---------------------------------------------------------------------------


class TestParticleFilterAdaptiveResampling:
    def setup_method(self) -> None:
        random.seed(42)

    def test_neff_uniform_weights_equals_N(self) -> None:
        pf = ParticleFilter(n_particles=100, x0=0.0, y0=0.0)
        assert pf.neff() == pytest.approx(100.0, rel=1e-9)

    def test_adaptive_skips_resample_when_weights_are_uniform(self) -> None:
        pf = ParticleFilter(n_particles=200)
        # No reweight; weights remain 1/N => Neff = N => above threshold
        did = pf.adaptive_resampling(threshold_ratio=0.5)
        assert did is False

    def test_adaptive_triggers_resample_when_neff_drops(self) -> None:
        pf = ParticleFilter(n_particles=200, x0=0.0, y0=0.0)
        # Spread particles in x, place observation far from the mean so
        # very few particles get high weight => Neff collapses.
        for i, p in enumerate(pf._particles):  # type: ignore[attr-defined]
            p[0] = float(i) * 0.1
        did = pf.adaptive_resampling(z=[0.0, 0.0], sigma_obs=0.5, threshold_ratio=0.5)
        assert did is True
        # After resampling weights must be uniform.
        ws = pf._weights  # type: ignore[attr-defined]
        assert all(abs(w - 1.0 / len(ws)) < 1e-9 for w in ws)

    def test_adaptive_resample_is_systematic_no_dup_explosion(self) -> None:
        pf = ParticleFilter(n_particles=200)
        for i, p in enumerate(pf._particles):  # type: ignore[attr-defined]
            p[0] = float(i)
        pf.adaptive_resampling(z=[100.0, 0.0], sigma_obs=10.0, threshold_ratio=0.5)
        xs = [p[0] for p in pf._particles]  # type: ignore[attr-defined]
        # Mean of resampled cloud should be biased toward the observation.
        assert sum(xs) / len(xs) > 50.0


# ---------------------------------------------------------------------------
# ParticleFilter — roughening
# ---------------------------------------------------------------------------


class TestParticleFilterRoughening:
    def setup_method(self) -> None:
        random.seed(7)

    def test_roughening_increases_state_variance(self) -> None:
        pf = ParticleFilter(n_particles=100, x0=0.0, y0=0.0)
        # Force all particles to be identical (post-resample collapse).
        for p in pf._particles:  # type: ignore[attr-defined]
            p[0] = 1.0
            p[1] = 2.0
            p[2] = 0.0
        pf.roughening(K=0.5)
        xs = [p[0] for p in pf._particles]  # type: ignore[attr-defined]
        ys = [p[1] for p in pf._particles]  # type: ignore[attr-defined]
        # Identical particles have zero range, so roughening adds zero noise
        # — make sure first we add a tiny range, then the test makes sense.
        # So inject manual diversity, re-test:
        for i, p in enumerate(pf._particles):  # type: ignore[attr-defined]
            p[0] = float(i) * 0.01
        before = [p[0] for p in pf._particles]  # type: ignore[attr-defined]
        pf.roughening(K=0.5)
        after = [p[0] for p in pf._particles]  # type: ignore[attr-defined]
        assert any(abs(a - b) > 1e-9 for a, b in zip(before, after))

    def test_roughening_no_op_on_zero_range(self) -> None:
        pf = ParticleFilter(n_particles=50, x0=5.0, y0=5.0)
        for p in pf._particles:  # type: ignore[attr-defined]
            p[0] = 5.0
            p[1] = 5.0
            p[2] = 0.0
        pf.roughening(K=0.5)
        # Zero range => zero sigma => no change.
        for p in pf._particles:  # type: ignore[attr-defined]
            assert p[0] == 5.0 and p[1] == 5.0 and p[2] == 0.0


# ---------------------------------------------------------------------------
# ParticleFilter — convergence metric
# ---------------------------------------------------------------------------


class TestParticleFilterConvergence:
    def setup_method(self) -> None:
        random.seed(0)

    def test_convergence_metric_keys(self) -> None:
        pf = ParticleFilter(n_particles=20)
        m = pf.convergence_metric()
        assert set(m.keys()) == {"neff", "entropy", "max_weight"}

    def test_convergence_uniform_weights_max_entropy(self) -> None:
        pf = ParticleFilter(n_particles=10)
        m = pf.convergence_metric()
        # Uniform weights => entropy = ln(N)
        assert m["entropy"] == pytest.approx(math.log(10), rel=1e-6)
        assert m["neff"] == pytest.approx(10.0)
        assert m["max_weight"] == pytest.approx(1.0 / 10.0)

    def test_convergence_collapsed_weights_low_entropy(self) -> None:
        pf = ParticleFilter(n_particles=10)
        # Force weights into a single particle.
        pf._weights = [0.0] * 10  # type: ignore[attr-defined]
        pf._weights[3] = 1.0  # type: ignore[attr-defined]
        m = pf.convergence_metric()
        assert m["max_weight"] == pytest.approx(1.0)
        assert m["neff"] == pytest.approx(1.0, rel=1e-3)
        assert m["entropy"] < 1e-6


# ---------------------------------------------------------------------------
# MapMatchingParticle
# ---------------------------------------------------------------------------


class _FakeMapStore:
    """Minimal map-store stub: snaps to a fixed line y=0."""

    def __init__(self, line_y: float = 0.0) -> None:
        self.line_y = line_y

    def nearest_point(self, x: float, y: float):
        # Snap to nearest point on horizontal line y = self.line_y.
        return (x, self.line_y, abs(y - self.line_y))


class TestMapMatchingParticle:
    def setup_method(self) -> None:
        random.seed(123)

    def test_snaps_particles_within_radius(self) -> None:
        mm = MapMatchingParticle(n_particles=50, x0=0.0, y0=0.0, snap_radius_m=5.0)
        for i, p in enumerate(mm._particles):  # type: ignore[attr-defined]
            p[0] = float(i)
            p[1] = 2.0  # within 5 m of y=0
        store = _FakeMapStore(line_y=0.0)
        snapped = mm.update_with_map(store)
        assert snapped == 50
        for p in mm._particles:  # type: ignore[attr-defined]
            assert p[1] == 0.0

    def test_does_not_snap_particles_outside_radius(self) -> None:
        mm = MapMatchingParticle(n_particles=10, snap_radius_m=5.0)
        for i, p in enumerate(mm._particles):  # type: ignore[attr-defined]
            p[1] = 50.0  # far outside radius
        store = _FakeMapStore(line_y=0.0)
        snapped = mm.update_with_map(store)
        assert snapped == 0

    def test_handles_store_exceptions_gracefully(self) -> None:
        class BadStore:
            def nearest_point(self, x, y):
                raise RuntimeError("offline tile")

        mm = MapMatchingParticle(n_particles=5)
        snapped = mm.update_with_map(BadStore())
        assert snapped == 0


# ---------------------------------------------------------------------------
# SHOEstimator — Zero-velocity update
# ---------------------------------------------------------------------------


class TestSHOEstimator:
    def test_zupt_fires_after_three_quiet_samples(self) -> None:
        sh = SHOEstimator(accel_threshold_mps2=0.1, min_consecutive=3)
        assert sh.update(0.05) is False  # 1
        assert sh.update(0.05) is False  # 2
        assert sh.update(0.05) is True   # 3 -> ZUPT

    def test_zupt_resets_velocity_to_zero(self) -> None:
        sh = SHOEstimator(accel_threshold_mps2=0.1, min_consecutive=3)
        # Inject motion first
        sh.update(2.0, dt=1.0)
        sh.update(1.5, dt=1.0)
        assert np.linalg.norm(sh.velocity) > 0
        # Now go quiet for 3 samples
        sh.update(0.01)
        sh.update(0.01)
        fired = sh.update(0.01)
        assert fired is True
        assert np.allclose(sh.velocity, 0.0)

    def test_zupt_does_not_fire_when_motion_breaks_window(self) -> None:
        sh = SHOEstimator(accel_threshold_mps2=0.1, min_consecutive=3)
        sh.update(0.05)
        sh.update(0.5)  # break the streak
        assert sh.update(0.05) is False

    def test_detect_zero_velocity_from_window(self) -> None:
        sh = SHOEstimator(accel_threshold_mps2=0.1, min_consecutive=3)
        assert sh.detect_zero_velocity([0.05, 0.05, 0.05]) is True
        assert sh.detect_zero_velocity([0.05, 0.5, 0.05]) is False
        assert sh.detect_zero_velocity([0.05]) is False  # too short


# ---------------------------------------------------------------------------
# HeadingCorrector — magnetometer calibration
# ---------------------------------------------------------------------------


class TestHeadingCorrector:
    def _synth_ellipsoid(
        self,
        soft: np.ndarray,
        hard: np.ndarray,
        n: int = 200,
    ) -> np.ndarray:
        """Generate samples on a unit sphere then distort by an ellipsoid."""
        rng = np.random.default_rng(42)
        u = rng.normal(size=(n, 3))
        u /= np.linalg.norm(u, axis=1, keepdims=True)
        # raw = soft^-1 @ unit + hard  (so calibrated = soft @ (raw-hard) on unit sphere)
        soft_inv = np.linalg.inv(soft)
        raw = (soft_inv @ u.T).T + hard
        return raw

    def test_calibration_recovers_unit_sphere(self) -> None:
        soft = np.diag([1.5, 0.8, 1.2])
        hard = np.array([0.3, -0.2, 0.5])
        samples = self._synth_ellipsoid(soft, hard, n=300)

        hc = HeadingCorrector()
        soft_fit, hard_fit = hc.calibrate(samples)
        cal = np.array([hc.apply(m) for m in samples])
        norms = np.linalg.norm(cal, axis=1)
        # Calibrated points should land near a unit sphere.
        assert np.median(norms) == pytest.approx(1.0, abs=0.05)
        assert soft_fit.shape == (3, 3)
        assert hard_fit.shape == (3,)

    def test_calibration_rejects_bad_shape(self) -> None:
        hc = HeadingCorrector()
        with pytest.raises(ValueError):
            hc.calibrate(np.zeros((5, 2)))

    def test_calibration_requires_minimum_samples(self) -> None:
        hc = HeadingCorrector()
        with pytest.raises(ValueError):
            hc.calibrate(np.zeros((4, 3)))


# ---------------------------------------------------------------------------
# BarometricAltimeter
# ---------------------------------------------------------------------------


class TestBarometricAltimeter:
    def test_altitude_zero_at_sea_level_pressure(self) -> None:
        alt = BarometricAltimeter.pressure_to_altitude(101325.0, 101325.0)
        assert alt == pytest.approx(0.0, abs=1e-6)

    def test_altitude_increases_with_lower_pressure(self) -> None:
        sea = BarometricAltimeter.pressure_to_altitude(101325.0, 101325.0)
        higher = BarometricAltimeter.pressure_to_altitude(89875.0, 101325.0)  # ~1000 m
        assert higher > sea
        assert 900.0 < higher < 1100.0

    def test_invalid_pressure_raises(self) -> None:
        with pytest.raises(ValueError):
            BarometricAltimeter.pressure_to_altitude(0.0)
        with pytest.raises(ValueError):
            BarometricAltimeter.pressure_to_altitude(101325.0, 0.0)

    def test_floor_detector_ground_floor(self) -> None:
        history = [0.1, -0.05, 0.2, 0.0, -0.1] * 3
        floor = BarometricAltimeter.floor_detector(history, floor_height_m=3.0)
        assert floor == 0

    def test_floor_detector_higher_floor(self) -> None:
        history = [9.0, 9.1, 8.9, 9.05, 9.0] * 3  # 3rd floor (≈9 m / 3 m)
        floor = BarometricAltimeter.floor_detector(history, floor_height_m=3.0)
        assert floor == 3

    def test_floor_detector_uses_recent_samples(self) -> None:
        # First 50 samples at 0 m, last 10 samples at 6 m → floor 2
        history = [0.0] * 50 + [6.0] * 10
        floor = BarometricAltimeter.floor_detector(history, floor_height_m=3.0)
        assert floor == 2

    def test_floor_detector_empty_history(self) -> None:
        assert BarometricAltimeter.floor_detector([], floor_height_m=3.0) == 0
