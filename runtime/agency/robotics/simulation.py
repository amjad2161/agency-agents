"""Simulation bridge for humanoid robot control.

Supports PyBullet, MuJoCo, Webots, and a zero-dependency MOCK backend
suitable for CI and unit testing.

Usage
-----
    from agency.robotics.simulation import SimulationBridge, SimulationBackend

    sim = SimulationBridge(SimulationBackend.MOCK)
    sim.load_humanoid()
    sim.set_joint_position("left_knee", 0.5)
    print(sim.get_joint_states())
    sim.step()
    sim.disconnect()
"""

from __future__ import annotations

import math
import time
from enum import Enum
from typing import Dict, Optional

from ..logging import get_logger

log = get_logger()


# ---------------------------------------------------------------------------
# Enums & Exceptions
# ---------------------------------------------------------------------------

class SimulationBackend(str, Enum):
    PYBULLET = "pybullet"
    MUJOCO   = "mujoco"
    WEBOTS   = "webots"
    MOCK     = "mock"


class SimulationError(RuntimeError):
    """Raised on critical simulation failures."""


# ---------------------------------------------------------------------------
# Humanoid joint definitions (H1-inspired, 18 joints)
# ---------------------------------------------------------------------------

HUMANOID_JOINTS = [
    # Legs
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch",
    "left_knee", "left_ankle",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch",
    "right_knee", "right_ankle",
    # Arms
    "left_shoulder_pitch", "left_shoulder_roll", "left_elbow",
    "right_shoulder_pitch", "right_shoulder_roll", "right_elbow",
    # Head
    "neck_yaw", "neck_pitch",
]

# Default neutral pose (radians)
NEUTRAL_POSE: Dict[str, float] = {j: 0.0 for j in HUMANOID_JOINTS}


# ---------------------------------------------------------------------------
# Mock Simulation (zero external deps)
# ---------------------------------------------------------------------------

class MockSimulation:
    """Pure-Python simulation for CI / unit testing.

    No physics — just stores joint state in a dict and advances a time counter.
    """

    def __init__(self) -> None:
        self._positions: Dict[str, float]   = dict(NEUTRAL_POSE)
        self._velocities: Dict[str, float]  = {j: 0.0 for j in HUMANOID_JOINTS}
        self._torques: Dict[str, float]     = {j: 0.0 for j in HUMANOID_JOINTS}
        self._time: float = 0.0
        self._dt: float   = 1.0 / 240.0   # matches pybullet default
        self._body_height: float = 1.0     # COM height (m)
        self._loaded: bool = False

    # --- loading ---

    def load_humanoid(self, urdf_path: Optional[str] = None) -> None:
        self._positions = dict(NEUTRAL_POSE)
        self._loaded = True
        log.info("MockSimulation.load_humanoid urdf=%s", urdf_path or "built-in")

    # --- joint control ---

    def set_joint_position(self, joint_name: str, angle_rad: float) -> None:
        if joint_name not in self._positions:
            raise SimulationError(f"Unknown joint: {joint_name!r}")
        self._positions[joint_name] = float(angle_rad)

    def set_joint_velocity(self, joint_name: str, vel: float) -> None:
        if joint_name not in self._velocities:
            raise SimulationError(f"Unknown joint: {joint_name!r}")
        self._velocities[joint_name] = float(vel)

    def set_joint_torque(self, joint_name: str, torque: float) -> None:
        if joint_name not in self._torques:
            raise SimulationError(f"Unknown joint: {joint_name!r}")
        self._torques[joint_name] = float(torque)

    def get_joint_states(self) -> Dict[str, float]:
        return dict(self._positions)

    # --- simulation control ---

    def step(self) -> None:
        self._time += self._dt
        # Naive integration: position += velocity * dt
        for j in HUMANOID_JOINTS:
            self._positions[j] += self._velocities[j] * self._dt

    def reset(self) -> None:
        self._positions  = dict(NEUTRAL_POSE)
        self._velocities = {j: 0.0 for j in HUMANOID_JOINTS}
        self._torques    = {j: 0.0 for j in HUMANOID_JOINTS}
        self._time       = 0.0
        self._body_height = 1.0

    def disconnect(self) -> None:
        self._loaded = False
        log.info("MockSimulation disconnected")

    @property
    def time(self) -> float:
        return self._time

    @property
    def body_height(self) -> float:
        return self._body_height

    @body_height.setter
    def body_height(self, v: float) -> None:
        self._body_height = float(v)


# ---------------------------------------------------------------------------
# PyBullet backend
# ---------------------------------------------------------------------------

class _PyBulletSimulation:
    """Thin wrapper around pybullet for humanoid control."""

    def __init__(self) -> None:
        try:
            import pybullet as pb          # type: ignore
            import pybullet_data           # type: ignore
        except ImportError as e:
            raise ImportError(
                "PyBullet not installed. Run: pip install pybullet"
            ) from e
        self._pb = pb
        self._data_path = pybullet_data.getDataPath()
        self._physics_client = pb.connect(pb.DIRECT)   # headless
        pb.setGravity(0, 0, -9.8, physicsClientId=self._physics_client)
        pb.setAdditionalSearchPath(self._data_path)
        self._robot_id: Optional[int] = None
        self._joint_map: Dict[str, int] = {}

    def load_humanoid(self, urdf_path: Optional[str] = None) -> None:
        pb = self._pb
        if urdf_path:
            self._robot_id = pb.loadURDF(
                urdf_path, basePosition=[0, 0, 1],
                physicsClientId=self._physics_client,
            )
        else:
            # Fall back to pybullet's built-in humanoid
            self._robot_id = pb.loadURDF(
                "humanoid/humanoid.urdf",
                basePosition=[0, 0, 1],
                physicsClientId=self._physics_client,
            )
        # Map joint names
        num_joints = pb.getNumJoints(self._robot_id, physicsClientId=self._physics_client)
        for i in range(num_joints):
            info = pb.getJointInfo(self._robot_id, i, physicsClientId=self._physics_client)
            name = info[1].decode()
            self._joint_map[name] = i

    def _joint_idx(self, joint_name: str) -> int:
        if joint_name not in self._joint_map:
            raise SimulationError(f"Unknown joint: {joint_name!r}")
        return self._joint_map[joint_name]

    def set_joint_position(self, joint_name: str, angle_rad: float) -> None:
        idx = self._joint_idx(joint_name)
        self._pb.setJointMotorControl2(
            self._robot_id, idx,
            self._pb.POSITION_CONTROL,
            targetPosition=angle_rad,
            physicsClientId=self._physics_client,
        )

    def set_joint_velocity(self, joint_name: str, vel: float) -> None:
        idx = self._joint_idx(joint_name)
        self._pb.setJointMotorControl2(
            self._robot_id, idx,
            self._pb.VELOCITY_CONTROL,
            targetVelocity=vel,
            physicsClientId=self._physics_client,
        )

    def set_joint_torque(self, joint_name: str, torque: float) -> None:
        idx = self._joint_idx(joint_name)
        self._pb.setJointMotorControl2(
            self._robot_id, idx,
            self._pb.TORQUE_CONTROL,
            force=torque,
            physicsClientId=self._physics_client,
        )

    def get_joint_states(self) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for name, idx in self._joint_map.items():
            state = self._pb.getJointState(
                self._robot_id, idx, physicsClientId=self._physics_client
            )
            result[name] = state[0]   # position
        return result

    def step(self) -> None:
        self._pb.stepSimulation(physicsClientId=self._physics_client)

    def reset(self) -> None:
        self._pb.resetSimulation(physicsClientId=self._physics_client)
        self._pb.setGravity(0, 0, -9.8, physicsClientId=self._physics_client)
        self._robot_id = None
        self._joint_map.clear()

    def disconnect(self) -> None:
        self._pb.disconnect(physicsClientId=self._physics_client)


# ---------------------------------------------------------------------------
# MuJoCo backend (stub)
# ---------------------------------------------------------------------------

class _MuJoCoSimulation:
    def __init__(self) -> None:
        try:
            import mujoco  # type: ignore  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "MuJoCo not installed. Run: pip install mujoco"
            ) from e
        self._mj = mujoco
        self._model = None
        self._data  = None
        self._positions: Dict[str, float] = dict(NEUTRAL_POSE)

    def load_humanoid(self, urdf_path: Optional[str] = None) -> None:
        # MuJoCo uses MJCF XML, not URDF — require explicit path for real use
        if urdf_path:
            self._model = self._mj.MjModel.from_xml_path(urdf_path)
            self._data  = self._mj.MjData(self._model)
        else:
            log.warning("MuJoCo: no model path provided, using MockSimulation joint map")
            self._positions = dict(NEUTRAL_POSE)

    def get_joint_states(self) -> Dict[str, float]:
        if self._data is not None:
            return {
                self._mj.mj_id2name(self._model, self._mj.mjtObj.mjOBJ_JOINT, i): float(v)
                for i, v in enumerate(self._data.qpos)
            }
        return dict(self._positions)

    def set_joint_position(self, joint_name: str, angle_rad: float) -> None:
        if self._data is not None:
            idx = self._mj.mj_name2id(
                self._model, self._mj.mjtObj.mjOBJ_JOINT, joint_name
            )
            self._data.qpos[idx] = angle_rad
        else:
            self._positions[joint_name] = angle_rad

    def set_joint_velocity(self, joint_name: str, vel: float) -> None:
        pass  # TODO: full MuJoCo velocity control

    def set_joint_torque(self, joint_name: str, torque: float) -> None:
        pass  # TODO: full MuJoCo torque control

    def step(self) -> None:
        if self._data is not None:
            self._mj.mj_step(self._model, self._data)

    def reset(self) -> None:
        if self._data is not None:
            self._mj.mj_resetData(self._model, self._data)

    def disconnect(self) -> None:
        self._model = None
        self._data  = None


# ---------------------------------------------------------------------------
# Public façade: SimulationBridge
# ---------------------------------------------------------------------------

class SimulationBridge:
    """Unified interface over multiple simulation backends.

    Auto-detects available backend if not specified; falls back to MOCK
    when nothing else is installed.

    Parameters
    ----------
    backend:
        Desired backend. If the library is not installed, MOCK is used.
    """

    def __init__(self, backend: SimulationBackend = SimulationBackend.MOCK) -> None:
        self._backend_name = backend
        self._impl = self._create_backend(backend)
        log.info("SimulationBridge backend=%s", self._backend_name)

    # --- private ---

    def _create_backend(self, backend: SimulationBackend):  # type: ignore[return]
        if backend == SimulationBackend.MOCK:
            return MockSimulation()
        if backend == SimulationBackend.PYBULLET:
            try:
                return _PyBulletSimulation()
            except ImportError as exc:
                log.warning("PyBullet unavailable (%s) — falling back to MOCK", exc)
                return MockSimulation()
        if backend == SimulationBackend.MUJOCO:
            try:
                return _MuJoCoSimulation()
            except ImportError as exc:
                log.warning("MuJoCo unavailable (%s) — falling back to MOCK", exc)
                return MockSimulation()
        # WEBOTS: controller runs in-process when launched by Webots supervisor
        log.warning("Webots backend: manual supervisor integration required. Using MOCK.")
        return MockSimulation()

    # --- public API ---

    def load_humanoid(self, urdf_path: Optional[str] = None) -> None:
        """Load the humanoid model. Uses built-in if urdf_path is None."""
        self._impl.load_humanoid(urdf_path)

    def get_joint_states(self) -> Dict[str, float]:
        """Return {joint_name: angle_rad} for all joints."""
        return self._impl.get_joint_states()

    def set_joint_position(self, joint_name: str, angle_rad: float) -> None:
        """Command a joint to a target angle in radians."""
        self._impl.set_joint_position(joint_name, angle_rad)

    def set_joint_velocity(self, joint_name: str, vel: float) -> None:
        """Command a joint velocity in rad/s."""
        self._impl.set_joint_velocity(joint_name, vel)

    def set_joint_torque(self, joint_name: str, torque: float) -> None:
        """Apply torque (Nm) to a joint."""
        self._impl.set_joint_torque(joint_name, torque)

    def step(self) -> None:
        """Advance the simulation by one timestep."""
        self._impl.step()

    def reset(self) -> None:
        """Reset simulation to neutral pose."""
        self._impl.reset()

    def disconnect(self) -> None:
        """Shut down the physics engine / connection."""
        self._impl.disconnect()

    @property
    def backend(self) -> SimulationBackend:
        return self._backend_name

    @property
    def is_mock(self) -> bool:
        return isinstance(self._impl, MockSimulation)
