"""ROS2 Bridge — Pass 21.

Optional bridge to ROS2 (rclpy). When ROS2 is not installed the module
falls back to ``MockROS2Bridge`` transparently, so CI and unit tests work
without any ROS2 installation.

Classes
-------
    ROS2Bridge        — real rclpy bridge (lazy import)
    MockROS2Bridge    — pure-Python stub that logs calls

Factory
-------
    get_ros2_bridge() — returns ROS2Bridge if available, MockROS2Bridge otherwise

CLI
---
    agency robotics ros2-status

Usage (library)
---------------
    from agency.robotics.ros2_bridge import get_ros2_bridge

    bridge = get_ros2_bridge()
    if bridge.is_available():
        bridge.publish_joint_command("left_knee", 0.5)
    else:
        print("ROS2 not available — using mock")
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..logging import get_logger

log = get_logger()


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class JointCommand:
    """A single joint position / velocity / torque command."""
    joint_name: str
    value: float
    control_type: str = "position"   # "position" | "velocity" | "torque"
    timestamp: float = field(default_factory=time.time)


@dataclass
class JointState:
    """State snapshot for a single joint."""
    joint_name: str
    position: float = 0.0
    velocity: float = 0.0
    effort: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class TwistCommand:
    """Velocity command for base navigation."""
    linear_x: float = 0.0
    linear_y: float = 0.0
    angular_z: float = 0.0
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Mock bridge (zero deps — used in CI and when rclpy absent)
# ---------------------------------------------------------------------------

class MockROS2Bridge:
    """Pure-Python stub bridge — logs all calls, needs no ROS2 installation."""

    def __init__(self) -> None:
        self._joint_commands: List[JointCommand] = []
        self._velocity_commands: List[TwistCommand] = []
        self._joint_state_callbacks: List[Callable] = []
        self._mock_states: Dict[str, JointState] = {}
        self._node_name: str = "jarvis_mock_node"
        log.debug("MockROS2Bridge initialised — no ROS2 runtime needed.")

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        return False

    # ------------------------------------------------------------------
    # Publishers
    # ------------------------------------------------------------------

    def publish_joint_command(
        self,
        joint_name: str,
        value: float,
        control_type: str = "position",
    ) -> None:
        """Log a joint command without actually publishing to ROS2."""
        cmd = JointCommand(
            joint_name=joint_name,
            value=value,
            control_type=control_type,
        )
        self._joint_commands.append(cmd)
        log.debug(
            "MockROS2: publish /joint_commands %s=%s (%s)",
            joint_name, value, control_type,
        )

    def publish_velocity(self, linear_x: float, angular_z: float) -> None:
        """Log a Twist command to /cmd_vel."""
        cmd = TwistCommand(linear_x=linear_x, angular_z=angular_z)
        self._velocity_commands.append(cmd)
        log.debug(
            "MockROS2: publish /cmd_vel linear_x=%s angular_z=%s",
            linear_x, angular_z,
        )

    # ------------------------------------------------------------------
    # Subscribers
    # ------------------------------------------------------------------

    def subscribe_joint_states(self, callback: Callable[[JointState], None]) -> None:
        """Register a callback for /joint_states (mock — callback stored)."""
        self._joint_state_callbacks.append(callback)
        log.debug("MockROS2: subscribed to /joint_states")

    # ------------------------------------------------------------------
    # Simulation helpers (mock-only)
    # ------------------------------------------------------------------

    def inject_joint_state(self, state: JointState) -> None:
        """Inject a fake joint state and fire registered callbacks."""
        self._mock_states[state.joint_name] = state
        for cb in self._joint_state_callbacks:
            try:
                cb(state)
            except Exception as exc:
                log.warning("MockROS2: callback error %s", exc)

    def get_published_commands(self) -> List[JointCommand]:
        return list(self._joint_commands)

    def get_published_velocities(self) -> List[TwistCommand]:
        return list(self._velocity_commands)

    def clear(self) -> None:
        self._joint_commands.clear()
        self._velocity_commands.clear()
        self._joint_state_callbacks.clear()
        self._mock_states.clear()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        return {
            "available": False,
            "backend": "mock",
            "node_name": self._node_name,
            "commands_published": len(self._joint_commands),
            "velocities_published": len(self._velocity_commands),
            "subscribers": len(self._joint_state_callbacks),
        }


# ---------------------------------------------------------------------------
# Real ROS2 bridge (lazy — only instantiated if rclpy is importable)
# ---------------------------------------------------------------------------

class ROS2Bridge:
    """Real rclpy bridge.

    Lazily imports rclpy so the module stays importable without ROS2.
    All methods fall back to mock behaviour if rclpy is not installed.
    """

    def __init__(self, node_name: str = "jarvis_ros2_node") -> None:
        self._node_name = node_name
        self._rclpy: Any = None
        self._node: Any = None
        self._joint_pub: Any = None
        self._vel_pub: Any = None
        self._joint_sub: Any = None
        self._mock = MockROS2Bridge()   # fallback
        self._initialized = False
        self._try_init()

    def _try_init(self) -> None:
        try:
            import rclpy  # type: ignore
            from rclpy.node import Node  # type: ignore
            self._rclpy = rclpy
            if not rclpy.ok():
                rclpy.init()
            self._node = Node(self._node_name)
            self._initialized = True
            log.info("ROS2Bridge: node '%s' created.", self._node_name)
        except ImportError:
            log.debug("ROS2Bridge: rclpy not available — using mock fallback.")
        except Exception as exc:
            log.warning("ROS2Bridge: init failed (%s) — using mock.", exc)

    def is_available(self) -> bool:
        return self._initialized and self._rclpy is not None

    def publish_joint_command(
        self,
        joint_name: str,
        value: float,
        control_type: str = "position",
    ) -> None:
        if not self.is_available():
            self._mock.publish_joint_command(joint_name, value, control_type)
            return
        # Real ROS2: build Float64MultiArray or JointTrajectory message
        # (minimal implementation — actual message type depends on robot driver)
        try:
            from std_msgs.msg import Float64  # type: ignore
            if self._joint_pub is None:
                self._joint_pub = self._node.create_publisher(
                    Float64, f"/joint_commands/{joint_name}", 10
                )
            msg = Float64()
            msg.data = float(value)
            self._joint_pub.publish(msg)
        except Exception as exc:
            log.warning("ROS2Bridge.publish_joint_command failed: %s", exc)
            self._mock.publish_joint_command(joint_name, value, control_type)

    def subscribe_joint_states(self, callback: Callable[[JointState], None]) -> None:
        if not self.is_available():
            self._mock.subscribe_joint_states(callback)
            return
        try:
            from sensor_msgs.msg import JointState as ROS2JointState  # type: ignore

            def _ros_cb(msg: Any) -> None:
                for name, pos, vel, eff in zip(
                    msg.name, msg.position, msg.velocity, msg.effort
                ):
                    callback(JointState(
                        joint_name=name,
                        position=float(pos),
                        velocity=float(vel),
                        effort=float(eff),
                    ))

            self._joint_sub = self._node.create_subscription(
                ROS2JointState, "/joint_states", _ros_cb, 10
            )
        except Exception as exc:
            log.warning("ROS2Bridge.subscribe_joint_states failed: %s", exc)
            self._mock.subscribe_joint_states(callback)

    def publish_velocity(self, linear_x: float, angular_z: float) -> None:
        if not self.is_available():
            self._mock.publish_velocity(linear_x, angular_z)
            return
        try:
            from geometry_msgs.msg import Twist  # type: ignore
            if self._vel_pub is None:
                self._vel_pub = self._node.create_publisher(Twist, "/cmd_vel", 10)
            msg = Twist()
            msg.linear.x = float(linear_x)
            msg.angular.z = float(angular_z)
            self._vel_pub.publish(msg)
        except Exception as exc:
            log.warning("ROS2Bridge.publish_velocity failed: %s", exc)
            self._mock.publish_velocity(linear_x, angular_z)

    def status(self) -> Dict[str, Any]:
        return {
            "available": self.is_available(),
            "backend": "rclpy" if self.is_available() else "mock_fallback",
            "node_name": self._node_name,
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_ros2_bridge() -> "ROS2Bridge | MockROS2Bridge":
    """Return a ROS2Bridge if rclpy is installed, else a MockROS2Bridge."""
    bridge = ROS2Bridge()
    if bridge.is_available():
        return bridge
    return bridge._mock  # return the already-created mock
