"""Advanced Balance Controller — Pass 21.

Implements a PID-based balance controller for the JARVIS humanoid robot.
Integrates with SimulationBridge (Pass 19) via the MOCK backend so it runs
fully offline.

Classes
-------
    Vector3            — (x, y, z) vector dataclass
    CoMEstimator       — Centre of Mass estimator from joint positions
    ZMPCalculator      — Zero Moment Point calculator
    PIDController      — Generic single-axis PID controller
    ControlAction      — Output of a single stabilization step
    JointTrajectory    — Trajectory for one joint (timestamps + positions)
    BalanceController  — Full balance + gait controller

Factory
-------
    get_balance_controller() — creates a BalanceController with MOCK sim

CLI
---
    agency robotics walk --gait dynamic --steps 4

Usage (library)
---------------
    from agency.robotics.balance import BalanceController, get_balance_controller

    ctrl = get_balance_controller()
    action = ctrl.stabilize()
    trajectories = ctrl.walking_pattern_generator(n_steps=4)
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..logging import get_logger
from .simulation import SimulationBackend, SimulationBridge

log = get_logger()


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

@dataclass
class Vector3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, other: "Vector3") -> "Vector3":
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __mul__(self, scalar: float) -> "Vector3":
        return Vector3(self.x * scalar, self.y * scalar, self.z * scalar)

    def norm(self) -> float:
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)

    def to_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)


# ---------------------------------------------------------------------------
# Centre of Mass estimator
# ---------------------------------------------------------------------------

# Approximate link masses (kg) for a 60 kg humanoid
_LINK_MASSES: Dict[str, float] = {
    "left_hip_yaw":    3.0,
    "left_hip_roll":   2.5,
    "left_hip_pitch":  2.5,
    "left_knee":       2.0,
    "left_ankle":      1.0,
    "right_hip_yaw":   3.0,
    "right_hip_roll":  2.5,
    "right_hip_pitch": 2.5,
    "right_knee":      2.0,
    "right_ankle":     1.0,
    "left_shoulder_pitch":  1.5,
    "left_shoulder_roll":   1.5,
    "left_elbow":           1.0,
    "right_shoulder_pitch": 1.5,
    "right_shoulder_roll":  1.5,
    "right_elbow":          1.0,
    "neck_yaw":   0.5,
    "neck_pitch": 0.5,
}

# Approximate link lengths (m) — used to estimate link endpoint positions
_LINK_LENGTHS: Dict[str, float] = {
    "left_hip_yaw":    0.05,
    "left_hip_roll":   0.05,
    "left_hip_pitch":  0.40,
    "left_knee":       0.38,
    "left_ankle":      0.07,
    "right_hip_yaw":   0.05,
    "right_hip_roll":  0.05,
    "right_hip_pitch": 0.40,
    "right_knee":      0.38,
    "right_ankle":     0.07,
    "left_shoulder_pitch":  0.05,
    "left_shoulder_roll":   0.28,
    "left_elbow":           0.26,
    "right_shoulder_pitch": 0.05,
    "right_shoulder_roll":  0.28,
    "right_elbow":          0.26,
    "neck_yaw":   0.05,
    "neck_pitch": 0.05,
}

_TOTAL_MASS = sum(_LINK_MASSES.values())


class CoMEstimator:
    """Estimates Centre of Mass from joint angles (simplified 2D sagittal plane)."""

    def estimate(self, joint_positions: Dict[str, float]) -> Vector3:
        """Return estimated CoM position in world frame (metres).

        Uses a simplified forward-kinematics approach where each link
        contributes a mass-weighted offset from the nominal upright pose.
        """
        weighted_x = 0.0
        weighted_z = 0.0
        total_mass = 0.0

        # Standing height estimate: pelvis at ~1.0 m
        base_z = 1.0

        for joint, mass in _LINK_MASSES.items():
            angle = joint_positions.get(joint, 0.0)
            length = _LINK_LENGTHS.get(joint, 0.1)
            # Project link contribution onto sagittal plane (x-z)
            dx = length * math.sin(angle)
            dz = -length * (1.0 - math.cos(angle))  # negative = lower
            weighted_x += mass * dx
            weighted_z += mass * dz
            total_mass += mass

        com_x = weighted_x / total_mass if total_mass > 0 else 0.0
        com_z = base_z + (weighted_z / total_mass if total_mass > 0 else 0.0)
        return Vector3(x=com_x, y=0.0, z=com_z)


# ---------------------------------------------------------------------------
# Zero Moment Point calculator
# ---------------------------------------------------------------------------

class ZMPCalculator:
    """Zero Moment Point (ZMP) calculator.

    Given CoM position and acceleration, computes the ZMP on the ground plane.
    Uses the simplified ZMP formula:
        zmp_x = com_x - com_z * (ddot_com_x / (g + ddot_com_z))
    """

    GRAVITY = 9.81  # m/s²

    def calculate(
        self,
        com: Vector3,
        com_accel: Vector3 = Vector3(0, 0, 0),
    ) -> Vector3:
        """Return ZMP position (z=0, ground plane)."""
        denom = self.GRAVITY + com_accel.z
        if abs(denom) < 1e-6:
            return Vector3(x=com.x, y=0.0, z=0.0)
        zmp_x = com.x - com.z * (com_accel.x / denom)
        zmp_y = com.y - com.z * (com_accel.y / denom)
        return Vector3(x=zmp_x, y=zmp_y, z=0.0)


# ---------------------------------------------------------------------------
# PID Controller
# ---------------------------------------------------------------------------

@dataclass
class PIDController:
    """Single-axis discrete PID controller."""

    kp: float = 1.0
    ki: float = 0.0
    kd: float = 0.0
    output_min: float = -float("inf")
    output_max: float = float("inf")

    _integral: float = field(default=0.0, init=False, repr=False)
    _prev_error: float = field(default=0.0, init=False, repr=False)
    _last_time: float = field(default_factory=time.monotonic, init=False, repr=False)

    def compute(self, error: float, dt: float = 0.01) -> float:
        """Compute PID output for *error* over time-step *dt*."""
        self._integral += error * dt
        derivative = (error - self._prev_error) / dt if dt > 0 else 0.0
        output = self.kp * error + self.ki * self._integral + self.kd * derivative
        self._prev_error = error
        return max(self.output_min, min(self.output_max, output))

    def reset(self) -> None:
        self._integral = 0.0
        self._prev_error = 0.0


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ControlAction:
    """Output of one stabilization step."""

    joint_deltas: Dict[str, float] = field(default_factory=dict)
    com: Vector3 = field(default_factory=Vector3)
    zmp: Vector3 = field(default_factory=Vector3)
    balance_error: float = 0.0
    dt: float = 0.01
    timestamp: float = field(default_factory=time.time)


@dataclass
class JointTrajectory:
    """Trajectory for a single joint — timestamps (s) and positions (rad)."""

    joint_name: str
    timestamps: List[float] = field(default_factory=list)
    positions: List[float] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.timestamps)


# ---------------------------------------------------------------------------
# Support polygon
# ---------------------------------------------------------------------------

def _point_in_support_polygon(px: float, py: float, support_half_width: float = 0.05) -> bool:
    """Return True if (px, py) lies within the simplified rectangular support polygon."""
    # Simplified: assume feet at ±y_offset, support polygon ±support_half_width in x
    return abs(px) <= support_half_width and abs(py) <= 0.10


# ---------------------------------------------------------------------------
# Balance Controller
# ---------------------------------------------------------------------------

class BalanceController:
    """PID-based balance and gait controller for the JARVIS humanoid.

    Parameters
    ----------
    sim:
        SimulationBridge to query / command joints.
    dt:
        Control loop timestep (seconds).
    """

    def __init__(
        self,
        sim: Optional[SimulationBridge] = None,
        dt: float = 0.01,
    ) -> None:
        self.sim = sim or SimulationBridge(SimulationBackend.MOCK)
        self.dt = dt
        self._com_estimator = CoMEstimator()
        self._zmp_calc = ZMPCalculator()
        # Separate PIDs for x and y balance axes
        self._pid_x = PIDController(kp=2.0, ki=0.1, kd=0.5,
                                    output_min=-0.3, output_max=0.3)
        self._pid_y = PIDController(kp=1.5, ki=0.05, kd=0.3,
                                    output_min=-0.2, output_max=0.2)

    # ------------------------------------------------------------------
    # Stabilization
    # ------------------------------------------------------------------

    def stabilize(self, sim: Optional[SimulationBridge] = None) -> ControlAction:
        """Run one balance correction step.

        Queries joint states from *sim* (or self.sim), estimates CoM and ZMP,
        then computes ankle corrections to keep the CoM over the support polygon.

        Returns a :class:`ControlAction` describing the corrections.
        """
        active_sim = sim or self.sim
        states = active_sim.get_joint_states()
        # get_joint_states() returns Dict[str, float] (joint → position)
        positions: Dict[str, float] = dict(states)

        com = self._com_estimator.estimate(positions)
        zmp = self._zmp_calc.calculate(com)

        # Balance error = ZMP displacement from support polygon centre
        error_x = zmp.x      # desired ZMP_x = 0 (over centre of feet)
        error_y = zmp.y

        balance_error = math.sqrt(error_x**2 + error_y**2)

        # PID corrections for ankle joints
        correction_x = self._pid_x.compute(error_x, self.dt)
        correction_y = self._pid_y.compute(error_y, self.dt)

        joint_deltas: Dict[str, float] = {}
        if abs(correction_x) > 1e-4:
            # Apply sagittal correction via ankle pitch joints
            joint_deltas["left_ankle"] = -correction_x
            joint_deltas["right_ankle"] = -correction_x
        if abs(correction_y) > 1e-4:
            # Apply frontal correction via hip roll joints
            joint_deltas["left_hip_roll"] = correction_y
            joint_deltas["right_hip_roll"] = -correction_y

        # Send corrections to sim
        for joint, delta in joint_deltas.items():
            current = positions.get(joint, 0.0)
            active_sim.set_joint_position(joint, current + delta)

        return ControlAction(
            joint_deltas=joint_deltas,
            com=com,
            zmp=zmp,
            balance_error=balance_error,
            dt=self.dt,
        )

    # ------------------------------------------------------------------
    # Gait generator
    # ------------------------------------------------------------------

    def walking_pattern_generator(
        self,
        step_length: float = 0.3,
        step_height: float = 0.05,
        n_steps: int = 4,
        step_duration: float = 0.6,
    ) -> List[JointTrajectory]:
        """Generate a simple sinusoidal walking gait trajectory.

        Parameters
        ----------
        step_length:
            Forward displacement per step (metres). Used to scale hip pitch.
        step_height:
            Foot clearance per step (metres). Used to scale knee / ankle.
        n_steps:
            Number of steps to generate.
        step_duration:
            Duration of one step in seconds.

        Returns list of :class:`JointTrajectory` objects (one per active joint).
        """
        dt = self.dt
        n_samples = int(step_duration / dt)
        total_samples = n_samples * n_steps

        # Build time axis
        timestamps = [i * dt for i in range(total_samples)]

        # Trajectories for major leg joints
        joint_names = [
            "left_hip_pitch", "right_hip_pitch",
            "left_knee", "right_knee",
            "left_ankle", "right_ankle",
        ]
        trajectories: Dict[str, JointTrajectory] = {
            j: JointTrajectory(joint_name=j, timestamps=list(timestamps))
            for j in joint_names
        }

        # Hip pitch amplitude determined by step_length
        hip_amp = step_length * 0.8          # rad ≈ 0.24 rad for 0.3 m step
        # Knee flexion during swing phase
        knee_amp = step_height * 2.5         # rad ≈ 0.125 rad for 0.05 m height
        # Ankle counter-rotation to keep foot flat
        ankle_amp = hip_amp * 0.4

        for i, t in enumerate(timestamps):
            phase = (t % step_duration) / step_duration   # [0, 1)
            omega = 2 * math.pi * phase

            # Left leg leads on even steps, right on odd
            step_num = int(t / step_duration)
            left_leads = (step_num % 2 == 0)

            if left_leads:
                left_phase  = omega
                right_phase = omega + math.pi
            else:
                left_phase  = omega + math.pi
                right_phase = omega

            lhp = hip_amp * math.sin(left_phase)
            rhp = hip_amp * math.sin(right_phase)

            # Knee flexion: positive during swing (swing phase ≈ 0.4 of cycle)
            lk = knee_amp * max(0.0, math.sin(left_phase))
            rk = knee_amp * max(0.0, math.sin(right_phase))

            la = -ankle_amp * math.sin(left_phase)
            ra = -ankle_amp * math.sin(right_phase)

            trajectories["left_hip_pitch"].positions.append(lhp)
            trajectories["right_hip_pitch"].positions.append(rhp)
            trajectories["left_knee"].positions.append(lk)
            trajectories["right_knee"].positions.append(rk)
            trajectories["left_ankle"].positions.append(la)
            trajectories["right_ankle"].positions.append(ra)

        return list(trajectories.values())

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, object]:
        states = self.sim.get_joint_states()
        positions: Dict[str, float] = dict(states)
        com = self._com_estimator.estimate(positions)
        zmp = self._zmp_calc.calculate(com)
        stable = _point_in_support_polygon(zmp.x, zmp.y)
        return {
            "com": com.to_tuple(),
            "zmp": zmp.to_tuple(),
            "stable": stable,
            "balance_error": math.sqrt(zmp.x**2 + zmp.y**2),
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_balance_controller(
    backend: SimulationBackend = SimulationBackend.MOCK,
    dt: float = 0.01,
) -> BalanceController:
    """Create a BalanceController with the specified simulation backend."""
    sim = SimulationBridge(backend)
    sim.load_humanoid()
    return BalanceController(sim=sim, dt=dt)
    return BalanceController(sim=sim, dt=dt)
