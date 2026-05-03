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


# ============================================================================
# R7 — Foot-mounted IMU for high-accuracy pedestrian dead reckoning (PDR)
# ============================================================================

class FootMountedIMU:
    """Foot-mounted IMU pedestrian dead reckoning.

    Uses zero-velocity updates (ZUPT) from stance-phase detection to bound
    drift. Stride length is estimated from the peak vertical acceleration
    using Weinberg's empirical model.
    """

    def __init__(self,
                 stance_accel_var_threshold: float = 0.5,
                 stance_gyro_norm_threshold: float = 0.5,
                 stride_constant: float = 0.41,
                 default_height_m: float = 1.75):
        import numpy as _np
        self._np = _np
        self.stance_accel_var_threshold = float(stance_accel_var_threshold)
        self.stance_gyro_norm_threshold = float(stance_gyro_norm_threshold)
        self.stride_constant = float(stride_constant)
        self.default_height_m = float(default_height_m)
        self.x = 0.0
        self.y = 0.0
        self._step_count = 0

    # --- Stance phase detection ---------------------------------------------

    def detect_stance(self, accel_window, gyro_window) -> bool:
        """Detect stance phase via low accel variance and low gyro magnitude.

        Args:
            accel_window: (N, 3) array of accelerometer samples (m/s²)
            gyro_window:  (N, 3) array of gyroscope samples (rad/s)
        """
        np = self._np
        a = np.asarray(accel_window, dtype=float).reshape(-1, 3)
        g = np.asarray(gyro_window, dtype=float).reshape(-1, 3)
        if a.size == 0 or g.size == 0:
            return False
        a_mag = np.linalg.norm(a, axis=1)
        accel_var = float(np.var(a_mag))
        gyro_norm_mean = float(np.mean(np.linalg.norm(g, axis=1)))
        return (accel_var < self.stance_accel_var_threshold and
                gyro_norm_mean < self.stance_gyro_norm_threshold)

    # --- Stride length (Weinberg model) -------------------------------------

    def estimate_stride_length(self, accel_peak: float,
                               height_m: float | None = None) -> float:
        """Estimate stride length using Weinberg's empirical model.

        L = K · ⁴√(a_max - a_min) ≈ K · √(a_peak),
        scaled by user height for robustness.
        """
        h = float(height_m) if height_m is not None else self.default_height_m
        peak = max(0.0, float(accel_peak))
        # Stride scales with √peak; height factor provides individual scaling.
        scale = h / 1.75
        return float(self.stride_constant * math.sqrt(peak) * scale)

    # --- Position update -----------------------------------------------------

    def update_position(self, stance: bool, stride_length: float,
                        heading_rad: float):
        """Advance horizontal position by a stride.

        During stance phase, no displacement is added (ZUPT).
        Returns (dx, dy) added this update.
        """
        if stance:
            return (0.0, 0.0)
        L = float(stride_length)
        dx = L * math.cos(float(heading_rad))
        dy = L * math.sin(float(heading_rad))
        self.x += dx
        self.y += dy
        self._step_count += 1
        return (dx, dy)

    @property
    def position(self):
        return (self.x, self.y)

    @property
    def step_count(self) -> int:
        return self._step_count


# ============================================================================
# R9 — Altimeter / Variometer (complementary baro + accel-z fusion)
# ============================================================================

class AltimeterBaroVSI:
    """Variometric vertical-speed indicator.

    Complementary filter blends low-frequency barometric altitude with
    high-frequency accelerometer-derived vertical motion.
    Crossover frequency fixed at 0.1 Hz (configurable via tau).
    """

    GRAVITY = 9.80665  # m/s²

    def __init__(self, tau: float = 1.591549):
        # tau = 1/(2π · f_c).  At f_c = 0.1 Hz → tau ≈ 1.5915 s.
        self.tau = float(tau)
        self.alt = 0.0
        self.vz = 0.0

    def reset(self, alt_m: float):
        self.alt = float(alt_m)
        self.vz = 0.0

    def update(self, baro_alt_m: float, accel_z_m_s2: float, dt: float):
        """Single-step complementary filter update.

        Returns (filtered_alt_m, vz_m_s).
        """
        baro = float(baro_alt_m)
        a_world_z = float(accel_z_m_s2) - self.GRAVITY
        dt = float(dt)
        alpha = self.tau / (self.tau + dt)
        # Integrate acceleration into vertical velocity, blend with baro rate
        baro_rate = (baro - self.alt) / max(dt, 1e-9)
        self.vz = alpha * (self.vz + a_world_z * dt) + (1.0 - alpha) * baro_rate
        # Integrate velocity, blend with raw baro
        self.alt = alpha * (self.alt + self.vz * dt) + (1.0 - alpha) * baro
        return (self.alt, self.vz)

    @property
    def crossover_freq(self) -> float:
        return 0.1


# ============================================================================
# R10 — Crouch / activity classifier
# ============================================================================

class CrouchDetector:
    """Indoor human-activity classifier from accelerometer windows.

    Classes: stationary, walking, running, crouching.
    """

    GRAVITY = 9.80665

    def __init__(self):
        pass

    def extract_features(self, accel_window):
        """Return (mean_magnitude, magnitude_variance, vertical_ratio).

        vertical_ratio = mean(|a_z|) / mean(|a|)  (1 = pure vertical).
        """
        a = np.asarray(accel_window, dtype=float).reshape(-1, 3)
        mag = np.linalg.norm(a, axis=1)
        mean_mag = float(np.mean(mag))
        var_mag = float(np.var(mag - self.GRAVITY))
        denom = float(np.mean(np.abs(a))) + 1e-9
        vert_ratio = float(np.mean(np.abs(a[:, 2])) / denom)
        return (mean_mag, var_mag, vert_ratio)

    def classify(self, accel_window) -> str:
        _, var_mag, vert_ratio = self.extract_features(accel_window)
        # Crouching: low-mid variance + low vertical dominance (lateral motion)
        if var_mag < 2.0 and vert_ratio < 0.5:
            return "crouching"
        if var_mag < 0.1:
            return "stationary"
        if var_mag <= 2.0:
            return "walking"
        return "running"


# ============================================================================
# R11 — Elevator / multi-floor motion detector
# ============================================================================

class ElevatorDetector:
    """Detects elevator and door-jolt signatures for multi-floor indoor nav."""

    GRAVITY = 9.80665
    ACCEL_THRESHOLD = 0.5    # m/s² — sustained vertical accel for elevator
    BARO_RATE_THRESH = 0.3   # m/s — sustained altitude rate during elevator

    def __init__(self):
        self.accel_z_buf = []
        self.baro_buf = []
        self.t_buf = []

    def update(self, accel_z: float, baro_alt: float, dt: float):
        self.accel_z_buf.append(float(accel_z))
        self.baro_buf.append(float(baro_alt))
        self.t_buf.append(float(dt))
        # Keep only the last 200 samples
        if len(self.accel_z_buf) > 200:
            self.accel_z_buf = self.accel_z_buf[-200:]
            self.baro_buf = self.baro_buf[-200:]
            self.t_buf = self.t_buf[-200:]

    def detect_elevator(self, window: int = 20) -> bool:
        if len(self.accel_z_buf) < window:
            return False
        a = np.asarray(self.accel_z_buf[-window:], dtype=float) - self.GRAVITY
        b = np.asarray(self.baro_buf[-window:], dtype=float)
        if b.size < 2:
            return False
        baro_rate = (b[-1] - b[0]) / max(np.sum(self.t_buf[-window:]), 1e-9)
        return (float(np.mean(np.abs(a))) > self.ACCEL_THRESHOLD
                and abs(float(baro_rate)) > self.BARO_RATE_THRESH)

    def estimate_floor(self, alt_m: float, floor_height: float = 3.0) -> int:
        return int(round(float(alt_m) / float(floor_height)))

    def detect_door_open(self, accel_window) -> bool:
        """Door-jolt: peak >2g spike followed by sub-0.1g quiet zone."""
        a = np.asarray(accel_window, dtype=float).reshape(-1, 3)
        if a.shape[0] < 4:
            return False
        mag = np.linalg.norm(a, axis=1) - self.GRAVITY
        peak_idx = int(np.argmax(np.abs(mag)))
        if abs(mag[peak_idx]) < 2.0 * self.GRAVITY:
            return False
        # Quiet window after the peak
        tail = mag[peak_idx + 1:]
        if tail.size == 0:
            return False
        return float(np.mean(np.abs(tail))) < 0.1 * self.GRAVITY


# ============================================================================
# R12 — Gait Phase Estimator (8-phase biomechanical model)
# ============================================================================

class GaitPhaseEstimator:
    """8-phase pedestrian gait phase classifier using accel-z + gyro-y.

    Phases (0–7):
      0 heel-strike, 1 loading, 2 mid-stance, 3 terminal-stance,
      4 pre-swing,  5 initial-swing, 6 mid-swing, 7 terminal-swing.
    """

    PHASE_NAMES = (
        "heel-strike", "loading", "mid-stance", "terminal-stance",
        "pre-swing", "initial-swing", "mid-swing", "terminal-swing",
    )
    GRAVITY = 9.80665

    def detect_phases(self, accel_z, gyro_y, threshold: float = 0.5):
        """Map each sample to a phase index in [0, 7]."""
        a = np.asarray(accel_z, dtype=float).reshape(-1) - self.GRAVITY
        g = np.asarray(gyro_y, dtype=float).reshape(-1)
        n = min(a.size, g.size)
        if n == 0:
            return []
        thr = float(threshold)
        out = []
        for i in range(n):
            ai = a[i]
            gi = g[i]
            # Stance vs swing by sign of accel-z (loading -> +ve impact)
            if ai > thr:                       # impact / loading peaks
                out.append(0 if i == 0 or a[i - 1] <= thr else 1)
            elif abs(ai) <= thr:               # quiet stance / mid-swing
                if abs(gi) <= thr:
                    out.append(2)              # mid-stance
                else:
                    out.append(6)              # mid-swing
            elif ai < -thr:                    # negative accel (push-off / pre-swing)
                if gi > thr:
                    out.append(4)              # pre-swing
                elif gi < -thr:
                    out.append(7)              # terminal-swing
                else:
                    out.append(3)              # terminal-stance
            else:
                out.append(5)                  # initial-swing
        return out

    def estimate_cadence(self, phase_timestamps) -> float:
        """Steps-per-minute from the timestamps of repeated heel strikes."""
        ts = list(phase_timestamps)
        if len(ts) < 2:
            return 0.0
        intervals = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
        avg = float(np.mean(intervals))
        if avg <= 0:
            return 0.0
        return float(60.0 / avg)

    def step_length_from_frequency(self, cadence_spm: float,
                                   height_m: float) -> float:
        """Grieve linear step-length model: L = 0.35·h + 0.01·cadence."""
        return float(0.35 * float(height_m) + 0.01 * float(cadence_spm))


# ============================================================================
# R15 — Strapdown INS (NED frame, quaternion attitude)
# ============================================================================

class StrapdownINS:
    """Full 6-DOF strapdown INS in NED frame.

    State: position (3,), velocity (3,) NED, attitude quaternion (4,) [w,x,y,z].
    """

    def __init__(self, g: float = 9.80665):
        self.g = float(g)
        self.pos = np.zeros(3)
        self.vel = np.zeros(3)
        self.q = np.array([1.0, 0.0, 0.0, 0.0])

    @staticmethod
    def _quat_mult(q1, q2):
        w1, x1, y1, z1 = q1
        w2, x2, y2, z2 = q2
        return np.array([
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ])

    def _quat_norm(self):
        n = float(np.linalg.norm(self.q))
        if n > 0:
            self.q = self.q / n

    def _rot_matrix(self):
        w, x, y, z = self.q
        return np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ])

    def propagate(self, accel_body, gyro_body, dt: float):
        a = np.asarray(accel_body, dtype=float).reshape(3)
        w = np.asarray(gyro_body, dtype=float).reshape(3)
        dt = float(dt)
        # First-order quaternion update: q̇ = 0.5 · q · [0, ω]
        omega = np.array([0.0, w[0], w[1], w[2]])
        dq = 0.5 * self._quat_mult(self.q, omega) * dt
        self.q = self.q + dq
        self._quat_norm()
        # Rotate body accel into NED, subtract gravity (NED z = +g down)
        R = self._rot_matrix()
        a_ned = R @ a - np.array([0.0, 0.0, self.g])
        # Integrate (RK1)
        self.vel = self.vel + a_ned * dt
        self.pos = self.pos + self.vel * dt

    def reset(self, pos=None, vel=None, q=None):
        if pos is not None:
            self.pos = np.asarray(pos, dtype=float).reshape(3).copy()
        if vel is not None:
            self.vel = np.asarray(vel, dtype=float).reshape(3).copy()
        if q is not None:
            self.q = np.asarray(q, dtype=float).reshape(4).copy()
            self._quat_norm()

    def euler_angles(self):
        """Return [roll, pitch, yaw] in degrees."""
        w, x, y, z = self.q
        roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
        sinp = max(-1.0, min(1.0, 2 * (w * y - z * x)))
        pitch = math.asin(sinp)
        yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
        return np.degrees(np.array([roll, pitch, yaw]))


# ============================================================================
# R16 — Tilt-Compensated Compass (hard/soft iron + tilt correction)
# ============================================================================

class TiltCompensatedCompass:
    """Magnetometer calibration + accelerometer-based tilt-compensated heading."""

    def __init__(self):
        self._hard_iron = np.zeros(3)
        self._soft_iron = np.eye(3)
        self._calibrated = False

    def calibrate(self, mag_samples):
        m = np.asarray(mag_samples, dtype=float).reshape(-1, 3)
        if m.shape[0] < 6:
            return
        mins = m.min(axis=0)
        maxs = m.max(axis=0)
        self._hard_iron = (mins + maxs) / 2.0
        ranges = (maxs - mins) / 2.0
        ranges = np.where(ranges < 1e-9, 1.0, ranges)
        avg_radius = float(np.mean(ranges))
        self._soft_iron = np.diag(avg_radius / ranges)
        self._calibrated = True

    def correct(self, raw_mag):
        v = np.asarray(raw_mag, dtype=float).reshape(3)
        return self._soft_iron @ (v - self._hard_iron)

    def heading(self, mag_corrected, accel) -> float:
        m = np.asarray(mag_corrected, dtype=float).reshape(3)
        a = np.asarray(accel, dtype=float).reshape(3)
        roll = math.atan2(a[1], a[2])
        pitch = math.atan2(-a[0], math.sqrt(a[1] ** 2 + a[2] ** 2))
        Bx = (m[0] * math.cos(pitch)
              + m[1] * math.sin(roll) * math.sin(pitch)
              + m[2] * math.cos(roll) * math.sin(pitch))
        By = m[1] * math.cos(roll) - m[2] * math.sin(roll)
        h = math.degrees(math.atan2(-By, Bx))
        return float(h % 360.0)

    def declination_correct(self, heading_deg: float,
                            declination_deg: float) -> float:
        return float((float(heading_deg) + float(declination_deg)) % 360.0)


# ============================================================================
# R17 — Ackermann Steering Vehicle Odometry (with longitudinal slip)
# ============================================================================

class AckermannOdometry:
    """Differential-drive approximation for Ackermann-steered ground vehicles."""

    def __init__(self, wheelbase: float = 2.7, track_width: float = 1.5,
                 wheel_radius: float = 0.33, ticks_per_rev: int = 512):
        self.wheelbase = float(wheelbase)
        self.track_width = float(track_width)
        self.wheel_radius = float(wheel_radius)
        self.ticks_per_rev = int(ticks_per_rev)
        self._slip = 0.0
        self.pose = np.zeros(3)

    def ticks_to_distance(self, ticks: int) -> float:
        return float(ticks) * (2.0 * math.pi * self.wheel_radius) \
               / float(self.ticks_per_rev)

    def update(self, left_ticks: int, right_ticks: int, dt: float):
        d_l = self.ticks_to_distance(left_ticks) * (1.0 - self._slip)
        d_r = self.ticks_to_distance(right_ticks) * (1.0 - self._slip)
        d_c = 0.5 * (d_l + d_r)
        d_th = (d_r - d_l) / max(self.track_width, 1e-9)
        # Mid-point integration
        theta_mid = self.pose[2] + 0.5 * d_th
        self.pose = self.pose + np.array([d_c * math.cos(theta_mid),
                                          d_c * math.sin(theta_mid),
                                          d_th])
        self.pose[2] = math.atan2(math.sin(self.pose[2]),
                                  math.cos(self.pose[2]))
        return self.pose.copy()

    def set_slip(self, slip_ratio: float):
        self._slip = float(np.clip(slip_ratio, 0.0, 0.99))

    def steering_radius(self, steering_angle_rad: float) -> float:
        a = float(steering_angle_rad)
        if abs(a) < 1e-6:
            return float("inf")
        return self.wheelbase / math.tan(a)

    def reset(self):
        self.pose = np.zeros(3)


# ============================================================================
# R18 — Motion Classifier (5-state IMU activity)
# ============================================================================

class MotionClassifier:
    """Sliding-window IMU classifier — 5 motion states."""

    STATES = ("stationary", "walking", "running", "vehicle", "elevator")
    GRAVITY = 9.80665

    def __init__(self, window: int = 50, fs: float = 100.0):
        self.window = int(window)
        self.fs = float(fs)
        self._buffer = []
        self._state = "stationary"

    def push(self, accel, gyro):
        a = np.asarray(accel, dtype=float).reshape(3).copy()
        g = np.asarray(gyro, dtype=float).reshape(3).copy()
        self._buffer.append((a, g))
        if len(self._buffer) > self.window:
            self._buffer.pop(0)

    def features(self):
        if len(self._buffer) < 2:
            return np.zeros(6)
        accel = np.stack([s[0] for s in self._buffer])
        gyro = np.stack([s[1] for s in self._buffer])
        a_mag = np.linalg.norm(accel, axis=1)
        g_mag = np.linalg.norm(gyro, axis=1)
        accel_var = float(np.var(a_mag))
        accel_mean_norm = float(np.mean(a_mag))
        gyro_var = float(np.var(g_mag))
        # FFT dominant frequency in [0.5, 4] Hz
        n = a_mag.size
        if n >= 8:
            spec = np.abs(np.fft.rfft(a_mag - accel_mean_norm))
            freqs = np.fft.rfftfreq(n, d=1.0 / self.fs)
            mask = (freqs >= 0.5) & (freqs <= 4.0)
            if mask.any():
                idx = int(np.argmax(spec[mask]))
                step_freq = float(freqs[mask][idx])
            else:
                step_freq = 0.0
        else:
            step_freq = 0.0
        vert_accel_std = float(np.std(accel[:, 2]))
        jerk_rms = float(np.sqrt(np.mean(np.diff(a_mag) ** 2))) \
            if a_mag.size > 1 else 0.0
        return np.array([accel_var, accel_mean_norm, gyro_var, step_freq,
                         vert_accel_std, jerk_rms])

    def classify(self) -> str:
        f = self.features()
        accel_var, accel_mean_norm, gyro_var, step_freq, vert_std, _ = f
        if accel_var < 0.01 and gyro_var < 0.001:
            self._state = "stationary"
        elif vert_std > 0.5 and step_freq < 0.5:
            self._state = "elevator"
        elif (accel_var < 0.5 and vert_std < 0.3
              and 9.0 <= accel_mean_norm <= 11.0):
            self._state = "vehicle"
        elif 2.5 < step_freq <= 4.0 and accel_var > 5.0:
            self._state = "running"
        elif 0.5 <= step_freq <= 2.5 and 0.1 <= accel_var <= 5.0:
            self._state = "walking"
        else:
            self._state = "walking"
        return self._state

    @property
    def state(self) -> str:
        return self._state


# ============================================================================
# R23 — Wheel Encoder Odometry (differential-drive dead reckoning)
# ============================================================================

class WheelEncoderOdometry:
    """Differential-drive dead reckoning from left/right encoder ticks."""

    def __init__(self, wheel_radius_m: float, wheel_base_m: float,
                 ticks_per_rev: float):
        self.r = float(wheel_radius_m)
        self.L = float(wheel_base_m)
        self.tpr = float(ticks_per_rev)
        self.x = 0.0
        self.y = 0.0
        self.theta = 0.0
        self.total_dist = 0.0

    def ticks_to_distance(self, ticks: float) -> float:
        return float(2.0 * math.pi * self.r * (float(ticks) / self.tpr))

    def update(self, left_ticks: float, right_ticks: float):
        dl = self.ticks_to_distance(left_ticks)
        dr = self.ticks_to_distance(right_ticks)
        ds = (dl + dr) / 2.0
        dtheta = (dr - dl) / max(self.L, 1e-9)
        self.theta += dtheta
        self.x += ds * math.cos(self.theta)
        self.y += ds * math.sin(self.theta)
        self.total_dist += abs(ds)
        return np.array([self.x, self.y, self.theta])

    def pose(self):
        return np.array([self.x, self.y, self.theta])

    def reset(self, x: float = 0.0, y: float = 0.0, theta: float = 0.0):
        self.x = float(x); self.y = float(y); self.theta = float(theta)
        self.total_dist = 0.0

    def velocity_from_ticks(self, left_ticks: float, right_ticks: float,
                            dt: float):
        dl = self.ticks_to_distance(left_ticks)
        dr = self.ticks_to_distance(right_ticks)
        v_linear = (dl + dr) / (2.0 * max(float(dt), 1e-9))
        v_angular = (dr - dl) / (self.L * max(float(dt), 1e-9))
        return float(v_linear), float(v_angular)


# ============================================================================
# R24 — ZUPT Velocity Aider (zero-velocity detector + EKF velocity aiding)
# ============================================================================

class ZUPTVelocityAider:
    """Zero-velocity detector with Kalman velocity aiding for foot-mounted IMU."""

    def __init__(self, accel_threshold: float = 0.05,
                 gyro_threshold: float = 0.01, window: int = 5):
        self.accel_thr = float(accel_threshold)
        self.gyro_thr = float(gyro_threshold)
        self.window = int(window)
        self._accel_buf = []
        self._gyro_buf = []
        self.velocity = np.zeros(3)
        self.P_vel = np.eye(3) * 0.01
        self.Q_vel = np.eye(3) * 1e-4
        self.R_zupt = np.eye(3) * 1e-6

    def push_sample(self, accel, gyro):
        self._accel_buf.append(float(np.linalg.norm(
            np.asarray(accel, dtype=float).reshape(3))))
        self._gyro_buf.append(float(np.linalg.norm(
            np.asarray(gyro, dtype=float).reshape(3))))
        if len(self._accel_buf) > self.window:
            self._accel_buf.pop(0)
            self._gyro_buf.pop(0)

    def is_stationary(self) -> bool:
        if len(self._accel_buf) < self.window:
            return False
        a_var = float(np.var(self._accel_buf))
        g_var = float(np.var(self._gyro_buf))
        return a_var < self.accel_thr and g_var < self.gyro_thr

    def predict_velocity(self, accel_ned, dt: float):
        a = np.asarray(accel_ned, dtype=float).reshape(3)
        self.velocity = self.velocity + a * float(dt)
        self.P_vel = self.P_vel + self.Q_vel
        return self.velocity.copy()

    def apply_zupt(self):
        H = np.eye(3)
        S = H @ self.P_vel @ H.T + self.R_zupt
        try:
            K = self.P_vel @ H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            return self.velocity.copy()
        innov = np.zeros(3) - self.velocity
        self.velocity = self.velocity + K @ innov
        self.P_vel = (np.eye(3) - K @ H) @ self.P_vel
        return self.velocity.copy()

    def step(self, accel, gyro, accel_ned, dt: float):
        self.push_sample(accel, gyro)
        self.predict_velocity(accel_ned, dt)
        if self.is_stationary():
            self.apply_zupt()
        return self.velocity.copy(), self.is_stationary()


# ============================================================================
# R25 — Magnetic Compass Calibration (hard/soft iron + heading)
# ============================================================================

class MagneticCompassCalibration:
    """Magnetometer hard/soft iron calibration + tilt-free heading."""

    def __init__(self):
        self._samples = []
        self._centre = np.zeros(3)
        self._scale = np.ones(3)

    def add_sample(self, mag_xyz):
        self._samples.append(np.asarray(mag_xyz, dtype=float).reshape(3).copy())

    def fit_ellipsoid(self):
        if not self._samples:
            return self._centre.copy(), self._scale.copy()
        s = np.stack(self._samples)
        self._centre = s.mean(axis=0)
        self._scale = s.std(axis=0)
        # Avoid zero scale
        self._scale = np.where(self._scale < 1e-9, 1.0, self._scale)
        return self._centre.copy(), self._scale.copy()

    def calibrate(self, mag_xyz):
        v = np.asarray(mag_xyz, dtype=float).reshape(3)
        return (v - self._centre) / self._scale

    def heading(self, mag_xyz) -> float:
        c = self.calibrate(mag_xyz)
        return float(math.atan2(c[1], c[0]))

    def quality(self) -> float:
        if not self._samples:
            return 1.0
        s = np.stack(self._samples)
        std = s.std(axis=0)
        mn = float(std.min()); mx = float(std.max())
        if mx <= 1e-12:
            return 1.0
        return float(mn / mx)
