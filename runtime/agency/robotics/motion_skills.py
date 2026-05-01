"""12 motion skills and MotionController for robot actuation."""

from __future__ import annotations

import math
import time

from .simulation import SimulationBridge


def _result(action: str, duration_s: float, status: str = "ok", **extra) -> dict:
    return {"action": action, "status": status, "duration_s": duration_s, **extra}


class MotionController:
    """High-level motion interface backed by a SimulationBridge."""

    def __init__(self, sim: SimulationBridge) -> None:
        self.sim = sim

    # ------------------------------------------------------------------
    # 12 motion skills
    # ------------------------------------------------------------------

    def walk_forward(self, distance: float, speed: float = 0.5) -> dict:
        """Walk forward by `distance` metres at `speed` m/s."""
        duration = abs(distance) / max(speed, 0.01)
        steps = max(1, int(duration * 10))
        for _ in range(steps):
            self.sim.step()
        status = "mock" if self.sim.backend == "mock" else "ok"
        return _result("walk_forward", round(duration, 3), status, distance=distance, speed=speed)

    def walk_backward(self, distance: float, speed: float = 0.3) -> dict:
        """Walk backward by `distance` metres."""
        duration = abs(distance) / max(speed, 0.01)
        steps = max(1, int(duration * 10))
        for _ in range(steps):
            self.sim.step()
        status = "mock" if self.sim.backend == "mock" else "ok"
        return _result("walk_backward", round(duration, 3), status, distance=distance, speed=speed)

    def turn(self, angle_degrees: float) -> dict:
        """Rotate by `angle_degrees` (positive = left, negative = right)."""
        duration = abs(angle_degrees) / 90.0  # 90°/s nominal
        steps = max(1, int(duration * 10))
        for _ in range(steps):
            self.sim.step()
        status = "mock" if self.sim.backend == "mock" else "ok"
        return _result("turn", round(duration, 3), status, angle_degrees=angle_degrees)

    def sit(self) -> dict:
        """Move robot to sitting pose."""
        self.sim.set_joint_position(0, -1.2)
        self.sim.set_joint_position(1, -1.2)
        self.sim.step()
        status = "mock" if self.sim.backend == "mock" else "ok"
        return _result("sit", 1.5, status)

    def stand(self) -> dict:
        """Move robot to standing pose."""
        self.sim.set_joint_position(0, 0.0)
        self.sim.set_joint_position(1, 0.0)
        self.sim.step()
        status = "mock" if self.sim.backend == "mock" else "ok"
        return _result("stand", 1.0, status)

    def wave(self) -> dict:
        """Wave with the right arm (3 oscillations)."""
        for angle in [0.8, -0.8, 0.8, -0.8, 0.8, 0.0]:
            self.sim.set_joint_position(4, angle)
            self.sim.step()
        status = "mock" if self.sim.backend == "mock" else "ok"
        return _result("wave", 2.0, status)

    def grasp(self, object_name: str = "object") -> dict:
        """Close gripper to grasp an object."""
        self.sim.set_joint_position(6, 0.5)
        self.sim.step()
        status = "mock" if self.sim.backend == "mock" else "ok"
        return _result("grasp", 0.8, status, object=object_name)

    def release(self) -> dict:
        """Open gripper to release object."""
        self.sim.set_joint_position(6, 0.0)
        self.sim.step()
        status = "mock" if self.sim.backend == "mock" else "ok"
        return _result("release", 0.5, status)

    def nod(self) -> dict:
        """Nod head up and down twice."""
        for angle in [0.3, -0.1, 0.3, 0.0]:
            self.sim.set_joint_position(2, angle)
            self.sim.step()
        status = "mock" if self.sim.backend == "mock" else "ok"
        return _result("nod", 1.2, status)

    def shake_head(self) -> dict:
        """Shake head left-right twice (negative gesture)."""
        for angle in [0.4, -0.4, 0.4, -0.4, 0.0]:
            self.sim.set_joint_position(3, angle)
            self.sim.step()
        status = "mock" if self.sim.backend == "mock" else "ok"
        return _result("shake_head", 1.5, status)

    def raise_arm(self, arm: str = "right") -> dict:
        """Raise the specified arm."""
        joint = 4 if arm == "right" else 5
        self.sim.set_joint_position(joint, 1.57)  # 90 degrees
        self.sim.step()
        status = "mock" if self.sim.backend == "mock" else "ok"
        return _result("raise_arm", 1.0, status, arm=arm)

    def lower_arm(self, arm: str = "right") -> dict:
        """Lower the specified arm."""
        joint = 4 if arm == "right" else 5
        self.sim.set_joint_position(joint, 0.0)
        self.sim.step()
        status = "mock" if self.sim.backend == "mock" else "ok"
        return _result("lower_arm", 0.8, status, arm=arm)
