"""Simulation bridge: PyBullet, MuJoCo, Webots, or MOCK."""

from __future__ import annotations

import math
import time
from typing import Optional

# Optional heavy imports
try:
    import pybullet as _pb  # type: ignore
    import pybullet_data  # type: ignore
    _HAS_PYBULLET = True
except ImportError:
    _HAS_PYBULLET = False

try:
    import mujoco  # type: ignore  # noqa: F401
    _HAS_MUJOCO = True
except ImportError:
    _HAS_MUJOCO = False


class SimulationBridge:
    """Connects to PyBullet, MuJoCo, or MOCK simulation."""

    def __init__(self, backend: str = "mock") -> None:
        # Auto-detect if "auto" is requested
        if backend == "auto":
            if _HAS_PYBULLET:
                backend = "pybullet"
            elif _HAS_MUJOCO:
                backend = "mujoco"
            else:
                backend = "mock"
        self.backend = backend
        self.connected = False
        self._physics_client: Optional[int] = None

        # Mock state
        self._mock_joints: list[dict] = [
            {"name": f"joint_{i}", "position": 0.0, "velocity": 0.0, "torque": 0.0}
            for i in range(8)
        ]
        self._mock_base_pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._step_count = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Connect to the simulation. Returns True on success."""
        if self.backend == "pybullet" and _HAS_PYBULLET:
            try:
                self._physics_client = _pb.connect(_pb.DIRECT)
                _pb.setGravity(0, 0, -9.81, physicsClientId=self._physics_client)
                self.connected = True
                return True
            except Exception:
                pass
        elif self.backend == "mujoco" and _HAS_MUJOCO:
            self.connected = True
            return True
        # Fall back to mock
        self.backend = "mock"
        self.connected = True
        return True

    def disconnect(self) -> None:
        """Disconnect from simulation."""
        if self.backend == "pybullet" and self._physics_client is not None:
            try:
                _pb.disconnect(physicsClientId=self._physics_client)
            except Exception:
                pass
            self._physics_client = None
        self.connected = False

    # ------------------------------------------------------------------
    # Robot control
    # ------------------------------------------------------------------

    def load_robot(self, model_path: Optional[str] = None) -> bool:
        """Load a robot model. Returns True on success."""
        if not self.connected:
            return False
        if self.backend == "pybullet" and self._physics_client is not None:
            try:
                _pb.setAdditionalSearchPath(pybullet_data.getDataPath())
                path = model_path or "r2d2.urdf"
                _pb.loadURDF(path, physicsClientId=self._physics_client)
                return True
            except Exception:
                return False
        # mock
        return True

    def get_joint_states(self) -> list[dict]:
        """Return [{name, position, velocity, torque}] for all joints."""
        if self.backend == "pybullet" and self._physics_client is not None:
            try:
                n = _pb.getNumJoints(0, physicsClientId=self._physics_client)
                states = []
                for i in range(n):
                    info = _pb.getJointInfo(0, i, physicsClientId=self._physics_client)
                    js = _pb.getJointState(0, i, physicsClientId=self._physics_client)
                    states.append({
                        "name": info[1].decode("utf-8"),
                        "position": js[0],
                        "velocity": js[1],
                        "torque": js[3],
                    })
                return states
            except Exception:
                pass
        return list(self._mock_joints)

    def set_joint_position(self, joint_id: int, position: float) -> bool:
        """Command a joint to a target position."""
        if self.backend == "pybullet" and self._physics_client is not None:
            try:
                _pb.setJointMotorControl2(
                    0, joint_id, _pb.POSITION_CONTROL,
                    targetPosition=position,
                    physicsClientId=self._physics_client,
                )
                return True
            except Exception:
                return False
        # mock
        if 0 <= joint_id < len(self._mock_joints):
            self._mock_joints[joint_id]["position"] = position
            return True
        return False

    def step(self) -> None:
        """Advance simulation one step."""
        if self.backend == "pybullet" and self._physics_client is not None:
            try:
                _pb.stepSimulation(physicsClientId=self._physics_client)
                return
            except Exception:
                pass
        # mock: animate base position slightly
        self._step_count += 1
        x, y, z = self._mock_base_pos
        self._mock_base_pos = (x + 0.001, y, z)

    def get_base_position(self) -> tuple[float, float, float]:
        """Return (x, y, z) of robot base."""
        if self.backend == "pybullet" and self._physics_client is not None:
            try:
                pos, _ = _pb.getBasePositionAndOrientation(0, physicsClientId=self._physics_client)
                return tuple(pos)  # type: ignore[return-value]
            except Exception:
                pass
        return self._mock_base_pos

    def reset(self) -> None:
        """Reset the simulation to initial state."""
        if self.backend == "pybullet" and self._physics_client is not None:
            try:
                _pb.resetSimulation(physicsClientId=self._physics_client)
                _pb.setGravity(0, 0, -9.81, physicsClientId=self._physics_client)
                return
            except Exception:
                pass
        # mock reset
        self._mock_base_pos = (0.0, 0.0, 0.0)
        self._step_count = 0
        for j in self._mock_joints:
            j["position"] = 0.0
            j["velocity"] = 0.0
            j["torque"] = 0.0
