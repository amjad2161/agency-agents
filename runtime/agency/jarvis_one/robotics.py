"""Robotics interface — humanoid simulation glue.

Adapter for PyBullet / MuJoCo / Webots / Isaac Sim style simulators.
The real adapters are loaded lazily; otherwise a deterministic kinematics
mock keeps tests hermetic. Designed for the JARVIS One "Phases 1-8"
humanoid programme — start with the mock, swap in PyBullet later.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any


SUPPORTED_SIMULATORS: tuple[str, ...] = ("pybullet", "mujoco", "webots", "isaac", "mock")


@dataclass
class JointState:
    name: str
    angle: float = 0.0
    velocity: float = 0.0


@dataclass
class RobotPose:
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    orientation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    joints: dict[str, JointState] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "orientation": self.orientation,
            "joints": {n: j.__dict__ for n, j in self.joints.items()},
            "timestamp": self.timestamp,
        }


class HumanoidSimulator:
    """Backend-agnostic humanoid simulator facade.

    Supplies the API a PPO trainer or perception loop expects:
    :meth:`reset`, :meth:`step`, :meth:`pose`, :meth:`set_joint`,
    :meth:`detect_objects`, :meth:`vision_inference`. The mock is good
    enough for unit tests of higher layers and for offline demos.
    """

    DEFAULT_JOINTS: tuple[str, ...] = (
        "left_hip", "right_hip", "left_knee", "right_knee",
        "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
        "neck", "torso",
    )

    def __init__(self, *, simulator: str = "mock") -> None:
        if simulator not in SUPPORTED_SIMULATORS:
            raise ValueError(f"unsupported simulator: {simulator!r}; "
                             f"expected {SUPPORTED_SIMULATORS}")
        self.simulator = simulator
        self._engine = self._load(simulator)
        self._pose = RobotPose(joints={
            n: JointState(name=n) for n in self.DEFAULT_JOINTS
        })
        self._t = 0.0

    # ------------------------------------------------------------------
    def reset(self) -> RobotPose:
        self._t = 0.0
        for joint in self._pose.joints.values():
            joint.angle = 0.0
            joint.velocity = 0.0
        self._pose.position = (0.0, 0.0, 0.0)
        self._pose.orientation = (0.0, 0.0, 0.0)
        self._pose.timestamp = time.time()
        return self._pose

    def step(self, *, dt: float = 0.01) -> RobotPose:
        self._t += dt
        # Mock kinematics — sinusoidal walking pattern.
        sway = math.sin(self._t * 2 * math.pi)
        for name, joint in self._pose.joints.items():
            joint.velocity = sway * (0.5 if "knee" in name else 0.3)
            joint.angle += joint.velocity * dt
        x, y, z = self._pose.position
        self._pose.position = (x + 0.05 * dt, y, z + 0.001 * abs(sway))
        self._pose.timestamp = time.time()
        return self._pose

    def pose(self) -> RobotPose:
        return self._pose

    def set_joint(self, name: str, *, angle: float | None = None,
                  velocity: float | None = None) -> JointState:
        if name not in self._pose.joints:
            raise KeyError(f"unknown joint: {name!r}")
        joint = self._pose.joints[name]
        if angle is not None:
            joint.angle = angle
        if velocity is not None:
            joint.velocity = velocity
        return joint

    # ------------------------------------------------------------------ perception (mocks)
    def detect_objects(self) -> list[dict[str, Any]]:
        # YOLO-shaped detections.
        return [
            {"label": "person", "score": 0.92, "box": (0.10, 0.20, 0.40, 0.80)},
            {"label": "chair",  "score": 0.71, "box": (0.55, 0.40, 0.78, 0.85)},
        ]

    def vision_inference(self, frame: Any) -> dict[str, Any]:
        return {"engine": self.simulator,
                "size": len(repr(frame)),
                "detections": self.detect_objects()}

    # ------------------------------------------------------------------
    def _load(self, simulator: str) -> Any | None:
        if simulator == "mock":
            return None
        try:  # pragma: no cover — optional heavy deps
            if simulator == "pybullet":
                import pybullet as bullet  # type: ignore
                return bullet
            if simulator == "mujoco":
                import mujoco  # type: ignore
                return mujoco
        except Exception:
            return None
        return None

    def health(self) -> dict[str, Any]:
        return {
            "simulator": self.simulator,
            "engine": "real" if self._engine else "mock",
            "joints": list(self._pose.joints),
        }
