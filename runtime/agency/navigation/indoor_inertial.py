"""GODSKILL Nav v11 — Inertial / magnetic indoor positioning.

Magnetic field fingerprint mapping + Pedestrian Dead Reckoning with
Weinberg step-length model and complementary heading filter.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# ------------------------------------------------------------------
# Magnetic mapping
# ------------------------------------------------------------------

@dataclass
class _MagSample:
    position: np.ndarray
    reading: np.ndarray
    magnitude: float


class MagneticMapper:
    """Magnetic anomaly fingerprint database with KNN lookup."""

    def __init__(self, k: int = 1):
        self.k = max(1, int(k))
        self._samples: list[_MagSample] = []

    def record(
        self,
        position: tuple[float, float] | tuple[float, float, float],
        mag_reading: np.ndarray,
    ) -> None:
        """Store a (position, magnetic-vector) sample."""
        pos = np.asarray(position, dtype=np.float64)
        if pos.shape == (2,):
            pos = np.array([pos[0], pos[1], 0.0])
        reading = np.asarray(mag_reading, dtype=np.float64)
        if reading.shape != (3,):
            raise ValueError("mag_reading must be a 3-vector")
        self._samples.append(
            _MagSample(position=pos, reading=reading, magnitude=float(np.linalg.norm(reading)))
        )

    def lookup(self, mag_reading: np.ndarray) -> tuple[float, float]:
        """Return (x, y) of the closest matching fingerprint."""
        if not self._samples:
            raise ValueError("magnetic map is empty")
        reading = np.asarray(mag_reading, dtype=np.float64)
        target_mag = float(np.linalg.norm(reading))
        # Combined cost: vector L2 + magnitude delta
        scored: list[tuple[float, np.ndarray]] = []
        for s in self._samples:
            v_dist = float(np.linalg.norm(s.reading - reading))
            m_dist = abs(s.magnitude - target_mag)
            scored.append((v_dist + 0.5 * m_dist, s.position))
        scored.sort(key=lambda x: x[0])
        top = scored[: self.k]
        eps = 1e-6
        weights = np.array([1.0 / (d + eps) for d, _ in top])
        positions = np.stack([p for _, p in top])
        weighted = np.sum(positions[:, :2] * weights[:, None], axis=0) / np.sum(weights)
        return float(weighted[0]), float(weighted[1])

    def __len__(self) -> int:
        return len(self._samples)


# ------------------------------------------------------------------
# Pedestrian Dead Reckoning
# ------------------------------------------------------------------

@dataclass(frozen=True)
class PDRPose:
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0
    step_count: int = 0


class PDREstimator:
    """Pedestrian Dead Reckoning with Weinberg step-length model.

    Uses peak-detection on accelerometer magnitude, gyro integration with
    magnetometer correction (complementary filter), and Weinberg's step
    length: L = K * (a_max - a_min) ** 0.25.
    """

    GRAVITY = 9.81
    STEP_PEAK_THRESHOLD = 11.0  # m/s² above gravity
    STEP_VALLEY_THRESHOLD = 8.5
    MIN_STEP_INTERVAL_S = 0.25
    WEINBERG_K = 0.41
    COMPLEMENTARY_ALPHA = 0.98  # weight for gyro vs mag heading

    def __init__(self, initial_heading: float = 0.0):
        self._heading = float(initial_heading)
        self._x = 0.0
        self._y = 0.0
        self._step_count = 0
        self._above_peak = False
        self._below_valley = True
        self._last_step_time = -math.inf
        self._sim_time = 0.0
        self._a_max = -math.inf
        self._a_min = math.inf
        self._gyro_integral = 0.0

    # -------- step detection --------

    def detect_step(self, accel_magnitude: float) -> bool:
        """Peak/valley detector. Returns True on the rising edge of a step."""
        a = float(accel_magnitude)
        self._a_max = max(self._a_max, a)
        self._a_min = min(self._a_min, a)
        step = False
        if a > self.STEP_PEAK_THRESHOLD and not self._above_peak and self._below_valley:
            if (self._sim_time - self._last_step_time) >= self.MIN_STEP_INTERVAL_S:
                step = True
                self._above_peak = True
                self._below_valley = False
                self._last_step_time = self._sim_time
        elif a < self.STEP_VALLEY_THRESHOLD:
            self._above_peak = False
            self._below_valley = True
        return step

    # -------- heading --------

    def estimate_heading(
        self, gyro_z_integral: float, mag_heading: float
    ) -> float:
        """Complementary filter: trust gyro short-term, mag long-term."""
        a = self.COMPLEMENTARY_ALPHA
        gyro_h = self._wrap_pi(self._heading + float(gyro_z_integral))
        # Normalise mag delta into the same wrap as gyro
        mag = self._wrap_pi(float(mag_heading))
        delta = self._wrap_pi(mag - gyro_h)
        fused = self._wrap_pi(gyro_h + (1.0 - a) * delta)
        return fused

    @staticmethod
    def _wrap_pi(angle: float) -> float:
        while angle > math.pi:
            angle -= 2.0 * math.pi
        while angle < -math.pi:
            angle += 2.0 * math.pi
        return angle

    # -------- step length (Weinberg) --------

    def _weinberg_step_length(self) -> float:
        if self._a_max == -math.inf or self._a_min == math.inf:
            return 0.7  # fallback nominal
        delta = max(0.0, self._a_max - self._a_min)
        return float(self.WEINBERG_K * (delta ** 0.25))

    # -------- main update --------

    def update(
        self,
        accel: np.ndarray,
        gyro: np.ndarray,
        mag: np.ndarray,
        dt: float = 0.02,
    ) -> PDRPose:
        """Run one PDR step. Inputs in m/s², rad/s, µT."""
        accel = np.asarray(accel, dtype=np.float64)
        gyro = np.asarray(gyro, dtype=np.float64)
        mag = np.asarray(mag, dtype=np.float64)
        self._sim_time += float(dt)
        a_mag = float(np.linalg.norm(accel))
        # Gyro integration of yaw rate (rad)
        self._gyro_integral += float(gyro[2]) * float(dt)
        # Magnetometer heading from horizontal components
        mag_heading = math.atan2(-mag[1], mag[0])
        if self.detect_step(a_mag):
            self._heading = self.estimate_heading(
                self._gyro_integral, mag_heading
            )
            self._gyro_integral = 0.0
            length = self._weinberg_step_length()
            self._x += length * math.sin(self._heading)
            self._y += length * math.cos(self._heading)
            self._step_count += 1
            # Reset peak window for next step
            self._a_max = -math.inf
            self._a_min = math.inf
        return PDRPose(
            x=self._x, y=self._y,
            heading=self._heading, step_count=self._step_count,
        )

    def reset(self, initial_heading: float = 0.0) -> None:
        self._heading = float(initial_heading)
        self._x = 0.0
        self._y = 0.0
        self._step_count = 0
        self._above_peak = False
        self._below_valley = True
        self._last_step_time = -math.inf
        self._sim_time = 0.0
        self._a_max = -math.inf
        self._a_min = math.inf
        self._gyro_integral = 0.0

    @property
    def pose(self) -> PDRPose:
        return PDRPose(self._x, self._y, self._heading, self._step_count)


# ------------------------------------------------------------------
# Zero-velocity update (ZUPT) — SHOEstimator
# ------------------------------------------------------------------


class SHOEstimator:
    """Stance-Hypothesis Optimal Estimator (a.k.a. SHOE) — Zero-Velocity Update.

    The detector flags a stance phase when ``|a| < accel_threshold`` for
    ``min_consecutive`` consecutive samples (default 3 samples,
    threshold 0.1 m/s² above gravity-removed magnitude).  When a stance is
    detected the integrated velocity should be reset to zero by the caller.
    """

    def __init__(
        self,
        accel_threshold_mps2: float = 0.1,
        min_consecutive: int = 3,
    ) -> None:
        self.accel_threshold = float(accel_threshold_mps2)
        self.min_consecutive = max(1, int(min_consecutive))
        self._consec = 0
        self._velocity = np.zeros(3, dtype=np.float64)

    def update(self, accel_mag_residual: float, dt: float = 0.02) -> bool:
        """Push one accelerometer-magnitude residual sample and integrate.

        ``accel_mag_residual`` is |a| - g.  Returns True when ZUPT fires
        (velocity has just been reset to zero).
        """
        a = abs(float(accel_mag_residual))
        zupt = False
        if a < self.accel_threshold:
            self._consec += 1
            if self._consec >= self.min_consecutive:
                self._velocity[:] = 0.0
                zupt = True
        else:
            self._consec = 0
            # Naive 1-D integration along magnitude direction; callers may
            # replace this with a 3-axis variant.
            self._velocity[0] += float(accel_mag_residual) * float(dt)
        return zupt

    def detect_zero_velocity(self, samples: list[float]) -> bool:
        """Convenience: classify a window of accel-magnitude residuals."""
        if len(samples) < self.min_consecutive:
            return False
        tail = samples[-self.min_consecutive:]
        return all(abs(float(s)) < self.accel_threshold for s in tail)

    @property
    def velocity(self) -> np.ndarray:
        return self._velocity.copy()

    def reset(self) -> None:
        self._consec = 0
        self._velocity[:] = 0.0


# ------------------------------------------------------------------
# Heading corrector with magnetometer calibration
# ------------------------------------------------------------------


class HeadingCorrector:
    """Magnetometer soft-iron / hard-iron calibration via least-squares.

    Fits an ellipsoid to a cloud of magnetometer samples and returns
    ``(soft_iron_3x3, hard_iron_3vec)`` such that calibrated readings are::

        m_cal = soft_iron @ (m_raw - hard_iron)

    The fit is closed-form: the ellipsoid is parameterised as
    ``(m - b)^T A (m - b) = 1`` and we recover B = sqrt(A) so the calibrated
    samples lie on a unit sphere.
    """

    def __init__(self) -> None:
        self.soft_iron = np.eye(3, dtype=np.float64)
        self.hard_iron = np.zeros(3, dtype=np.float64)

    def calibrate(self, mag_samples: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        samples = np.asarray(mag_samples, dtype=np.float64)
        if samples.ndim != 2 or samples.shape[1] != 3:
            raise ValueError("mag_samples must have shape (N, 3)")
        if samples.shape[0] < 9:
            raise ValueError("need at least 9 samples for ellipsoid fit")

        # Hard-iron offset: centre of the cloud is a robust starting point.
        b = samples.mean(axis=0)
        centred = samples - b

        # Solve for symmetric A in (m - b)^T A (m - b) = 1
        # Build the design matrix on the upper-triangular elements of A.
        x, y, z = centred[:, 0], centred[:, 1], centred[:, 2]
        D = np.column_stack(
            [x * x, y * y, z * z, 2 * x * y, 2 * x * z, 2 * y * z]
        )
        rhs = np.ones(samples.shape[0], dtype=np.float64)
        coeffs, *_ = np.linalg.lstsq(D, rhs, rcond=None)
        A = np.array(
            [
                [coeffs[0], coeffs[3], coeffs[4]],
                [coeffs[3], coeffs[1], coeffs[5]],
                [coeffs[4], coeffs[5], coeffs[2]],
            ],
            dtype=np.float64,
        )
        # Ensure positive-definite, then take symmetric square root.
        evals, evecs = np.linalg.eigh(A)
        evals = np.clip(evals, 1e-12, None)
        sqrt_A = evecs @ np.diag(np.sqrt(evals)) @ evecs.T

        self.hard_iron = b
        self.soft_iron = sqrt_A
        return self.soft_iron, self.hard_iron

    def apply(self, mag_raw: np.ndarray) -> np.ndarray:
        m = np.asarray(mag_raw, dtype=np.float64)
        return self.soft_iron @ (m - self.hard_iron)


# ------------------------------------------------------------------
# Barometric altimeter
# ------------------------------------------------------------------


class BarometricAltimeter:
    """Pressure-to-altitude converter + simple floor detector.

    Uses the international barometric (hypsometric) formula::

        h = (T0 / L) * (1 - (p / p0) ** (R*L / (g*M)))

    With T0=288.15 K, L=0.0065 K/m, p0=101325 Pa,
    g=9.80665 m/s², M=0.0289644 kg/mol, R=8.31446 J/(mol·K).
    """

    T0 = 288.15
    L = 0.0065
    G = 9.80665
    M = 0.0289644
    R = 8.31446

    @classmethod
    def pressure_to_altitude(cls, p_pa: float, p0_pa: float = 101325.0) -> float:
        if p_pa <= 0 or p0_pa <= 0:
            raise ValueError("pressures must be positive Pa")
        exponent = (cls.R * cls.L) / (cls.G * cls.M)
        return float((cls.T0 / cls.L) * (1.0 - (float(p_pa) / float(p0_pa)) ** exponent))

    @staticmethod
    def floor_detector(
        alt_history: list[float],
        floor_height_m: float = 3.0,
        ground_alt_m: float = 0.0,
    ) -> int:
        """Return current floor (0 = ground) from a history of altitudes.

        Uses the median of the last 10 samples to suppress short-term noise,
        then quantises by ``floor_height_m``.
        """
        if not alt_history:
            return 0
        tail = alt_history[-10:]
        sorted_tail = sorted(tail)
        median = sorted_tail[len(sorted_tail) // 2]
        rel = median - ground_alt_m
        return int(rel // float(floor_height_m))


# ---------------------------------------------------------------------------
# IMU Preintegration (Round 4)
# ---------------------------------------------------------------------------


def _skew(v: np.ndarray) -> np.ndarray:
    """Skew-symmetric matrix of a 3-vector."""
    return np.array([
        [0.0, -v[2], v[1]],
        [v[2], 0.0, -v[0]],
        [-v[1], v[0], 0.0],
    ], dtype=float)


def _exp_so3(omega: np.ndarray) -> np.ndarray:
    """Rodriguez formula: exp of skew(omega) → 3x3 rotation."""
    theta = float(np.linalg.norm(omega))
    if theta < 1e-10:
        return np.eye(3) + _skew(omega)
    K = _skew(omega / theta)
    return (np.eye(3)
            + math.sin(theta) * K
            + (1 - math.cos(theta)) * (K @ K))


class IMUPreintegration:
    """Preintegration of IMU between keyframes (Forster et al. style).

    Accumulates body-frame ΔR (SO(3) via Rodriguez), Δv, Δp under a
    constant-bias assumption.  Stores first-order Jacobians for online
    bias correction and propagates a 9x9 covariance for fusion factors.
    """

    def __init__(
        self,
        gyro_bias: Optional[np.ndarray] = None,
        accel_bias: Optional[np.ndarray] = None,
        sigma_a: float = 0.1,
        sigma_g: float = 0.01,
        gravity: float = 9.80665,
    ) -> None:
        self.gyro_bias = (np.zeros(3, dtype=float) if gyro_bias is None
                          else np.asarray(gyro_bias, dtype=float).copy())
        self.accel_bias = (np.zeros(3, dtype=float) if accel_bias is None
                           else np.asarray(accel_bias, dtype=float).copy())
        self.sigma_a = float(sigma_a)
        self.sigma_g = float(sigma_g)
        self.g = float(gravity)
        self.reset()

    def reset(self) -> None:
        """Clear accumulated state — starts a new preintegration window."""
        self.dR = np.eye(3, dtype=float)
        self.dv = np.zeros(3, dtype=float)
        self.dp = np.zeros(3, dtype=float)
        self.dt_total = 0.0
        # Bias-correction Jacobians.
        self.J_R_bg = np.zeros((3, 3), dtype=float)
        self.J_v_ba = np.zeros((3, 3), dtype=float)
        self.J_v_bg = np.zeros((3, 3), dtype=float)
        self.J_p_ba = np.zeros((3, 3), dtype=float)
        self.J_p_bg = np.zeros((3, 3), dtype=float)
        # 9x9 covariance ordered [δθ, δv, δp].
        self.P = np.zeros((9, 9), dtype=float)

    def integrate(
        self,
        accel: np.ndarray,
        gyro: np.ndarray,
        dt: float,
    ) -> None:
        """Integrate one IMU sample (accel, gyro in body frame, dt in s)."""
        if dt <= 0.0:
            return
        a = np.asarray(accel, dtype=float).reshape(3) - self.accel_bias
        w = np.asarray(gyro, dtype=float).reshape(3) - self.gyro_bias

        dR_step = _exp_so3(w * dt)
        a_world = self.dR @ a
        self.dp = self.dp + self.dv * dt + 0.5 * a_world * dt * dt
        self.dv = self.dv + a_world * dt
        self.dR = self.dR @ dR_step

        # Bias-correction Jacobians (small-angle approximations).
        skew_a = _skew(a)
        self.J_v_ba = self.J_v_ba - self.dR * dt
        self.J_p_ba = self.J_p_ba + self.J_v_ba * dt - 0.5 * self.dR * dt * dt
        self.J_R_bg = self.J_R_bg - self.dR * dt
        self.J_v_bg = self.J_v_bg - self.dR @ skew_a * dt
        self.J_p_bg = self.J_p_bg + self.J_v_bg * dt

        # Covariance propagation.
        F = np.eye(9, dtype=float)
        F[3:6, 0:3] = -self.dR @ skew_a * dt
        F[6:9, 0:3] = -0.5 * self.dR @ skew_a * dt * dt
        F[6:9, 3:6] = np.eye(3) * dt
        Qc = np.zeros((9, 9), dtype=float)
        Qc[0:3, 0:3] = np.eye(3) * (self.sigma_g ** 2) * dt
        Qc[3:6, 3:6] = np.eye(3) * (self.sigma_a ** 2) * dt
        Qc[6:9, 6:9] = np.eye(3) * (self.sigma_a ** 2) * dt * dt * 0.25
        self.P = F @ self.P @ F.T + Qc

        self.dt_total += dt

    def bias_corrected_delta(
        self,
        bg_correction: np.ndarray,
        ba_correction: np.ndarray,
    ) -> dict:
        """Return ΔR, Δv, Δp first-order corrected for small bias deltas."""
        bg = np.asarray(bg_correction, dtype=float).reshape(3)
        ba = np.asarray(ba_correction, dtype=float).reshape(3)
        dR_corr = self.dR @ _exp_so3(self.J_R_bg @ bg)
        dv_corr = self.dv + self.J_v_ba @ ba + self.J_v_bg @ bg
        dp_corr = self.dp + self.J_p_ba @ ba + self.J_p_bg @ bg
        return {"dR": dR_corr, "dv": dv_corr, "dp": dp_corr}

    def covariance(self) -> np.ndarray:
        """Return the 9x9 covariance matrix [δθ, δv, δp]."""
        return self.P.copy()

    def create_factor(self, pose_i: dict, pose_j: dict) -> dict:
        """Build a preintegration factor between keyframes i and j.

        ``pose_i``/``pose_j`` dicts must provide ``R`` (3x3), ``v`` (3,),
        ``p`` (3,).  Returns a residual (9,) plus simple Jacobians wrt the
        j-frame state — enough for downstream factor-graph wiring.
        """
        Ri = np.asarray(pose_i["R"], dtype=float)
        Rj = np.asarray(pose_j["R"], dtype=float)
        vi = np.asarray(pose_i["v"], dtype=float).reshape(3)
        vj = np.asarray(pose_j["v"], dtype=float).reshape(3)
        pi = np.asarray(pose_i["p"], dtype=float).reshape(3)
        pj = np.asarray(pose_j["p"], dtype=float).reshape(3)
        dt = max(self.dt_total, 1e-9)
        g = np.array([0.0, 0.0, -self.g], dtype=float)
        dR_pred = Ri.T @ Rj
        dv_pred = Ri.T @ (vj - vi - g * dt)
        dp_pred = Ri.T @ (pj - pi - vi * dt - 0.5 * g * dt * dt)
        dR_err = self.dR.T @ dR_pred
        r_rot = 0.5 * np.array([
            dR_err[2, 1] - dR_err[1, 2],
            dR_err[0, 2] - dR_err[2, 0],
            dR_err[1, 0] - dR_err[0, 1],
        ], dtype=float)
        r_vel = dv_pred - self.dv
        r_pos = dp_pred - self.dp
        residual = np.concatenate([r_rot, r_vel, r_pos])
        return {
            "residual": residual,
            "J_j_R": np.eye(3),
            "J_j_v": Ri.T,
            "J_j_p": Ri.T,
            "dt": dt,
        }


# =====================================================================
# GODSKILL Nav R6 — Wheel Odometry Integrator (differential drive)
# =====================================================================

class WheelOdometryIntegrator:
    """Differential-drive wheel odometry with slip detection.

    Inputs are left/right wheel linear speeds (m/s) and elapsed time.
    Returns incremental pose (dx, dy, dtheta) in the robot body frame.
    Slip ratio (max/min wheel speed) above threshold (default 1.5)
    flags a slipping wheel.
    """

    def __init__(self, slip_threshold: float = 1.5,
                 default_wheelbase_m: float = 0.5) -> None:
        self.slip_threshold = float(slip_threshold)
        self.default_wheelbase = float(default_wheelbase_m)
        self.last_slip_ratio: float = 1.0
        self.last_slip_detected: bool = False
        # Cumulative pose for convenience
        self.x_total: float = 0.0
        self.y_total: float = 0.0
        self.theta_total: float = 0.0

    def estimate_slip(self, v_left: float, v_right: float) -> float:
        """Slip ratio = max(|v|) / max(min(|v|), eps).

        Symmetrical motion (|v_l|≈|v_r|) → ratio≈1.0.
        Slipping wheel → ratio >> 1.
        """
        a = abs(float(v_left))
        b = abs(float(v_right))
        lo = min(a, b)
        hi = max(a, b)
        if lo < 1e-6:
            ratio = float("inf") if hi > 1e-6 else 1.0
        else:
            ratio = hi / lo
        self.last_slip_ratio = ratio
        self.last_slip_detected = ratio > self.slip_threshold
        return ratio

    def integrate(self, v_left: float, v_right: float, dt: float,
                  wheelbase: Optional[float] = None) -> tuple:
        """Integrate one step.

        Returns (dx, dy, dtheta) in body frame.
        """
        vL = float(v_left)
        vR = float(v_right)
        dt = float(dt)
        if dt <= 0.0:
            return (0.0, 0.0, 0.0)
        b = float(wheelbase) if wheelbase is not None else self.default_wheelbase
        if b <= 0.0:
            raise ValueError("wheelbase must be positive")
        v = 0.5 * (vR + vL)
        omega = (vR - vL) / b
        # Slip update
        self.estimate_slip(vL, vR)
        if abs(omega) < 1e-9:
            dx = v * dt
            dy = 0.0
            dtheta = 0.0
        else:
            dtheta = omega * dt
            R_curve = v / omega
            dx = R_curve * math.sin(dtheta)
            dy = R_curve * (1.0 - math.cos(dtheta))
        # Update cumulative pose in world frame
        c = math.cos(self.theta_total)
        s = math.sin(self.theta_total)
        self.x_total += c * dx - s * dy
        self.y_total += s * dx + c * dy
        self.theta_total += dtheta
        return (float(dx), float(dy), float(dtheta))


__all__ = [
    "MagneticMapper",
    "PDREstimator",
    "PDRPose",
    "SHOEstimator",
    "HeadingCorrector",
    "BarometricAltimeter",
    "IMUPreintegration",
    "WheelOdometryIntegrator",
]
