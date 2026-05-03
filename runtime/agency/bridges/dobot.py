"""DOBOT robot arm bridge.

Wraps the DOBOT Magician / M1 USB serial protocol. Three backends are
attempted, in order:

1. ``pydobot`` (preferred — high-level Python wrapper).
2. ``pyserial`` direct protocol (raw frame builder, used when ``pydobot``
   is missing but a serial port is reachable).
3. Pure-Python *simulation* fallback that maintains a virtual pose so
   callers can exercise the full API on a machine with no hardware.

The bridge is intentionally side-effect free at import time — connecting
to the device only happens inside :meth:`DobotBridge.connect`.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..logging import get_logger

log = get_logger()


# ---------------------------------------------------------------------------
# Optional backend detection (cheap — only checks importability)
# ---------------------------------------------------------------------------

def _has_pydobot() -> bool:
    try:
        import pydobot  # noqa: F401
        return True
    except Exception:
        return False


def _has_pyserial() -> bool:
    try:
        import serial  # noqa: F401
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Pose:
    """Cartesian pose + four joint angles, matching the DOBOT report frame."""

    x: float = 200.0
    y: float = 0.0
    z: float = 0.0
    r: float = 0.0
    joint1: float = 0.0
    joint2: float = 0.0
    joint3: float = 0.0
    joint4: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "r": self.r,
            "joint1": self.joint1,
            "joint2": self.joint2,
            "joint3": self.joint3,
            "joint4": self.joint4,
        }


@dataclass(frozen=True)
class _Step:
    """One entry in :meth:`DobotBridge.run_program`."""

    action: str
    kwargs: Dict[str, Any] = field(default_factory=dict)


_HOME_POSE = Pose(x=200.0, y=0.0, z=50.0, r=0.0)
_VALID_MODES = {"MOVJ", "MOVL", "JUMP"}


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------

class DobotBridge:
    """Hardware-safe wrapper around the DOBOT serial protocol.

    The bridge does *not* open a connection until :meth:`connect` is called.
    Once a connection attempt has been made, ``hardware_available`` reflects
    whether a real backend is bound; otherwise the bridge stays in
    deterministic simulation mode.
    """

    def __init__(self) -> None:
        self._backend: str = "simulation"
        self._device: Any = None  # pydobot.Dobot or serial.Serial when bound
        self._port: Optional[str] = None
        self._connected: bool = False
        self._velocity: float = 100.0
        self._acceleration: float = 100.0
        self._gripper_open: bool = True
        self._pose: Pose = _HOME_POSE
        self._command_log: List[Dict[str, Any]] = []
        self._homed: bool = False

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def hardware_available(self) -> bool:
        """True iff a real backend (pydobot or serial) is currently bound."""
        return self._connected and self._backend in {"pydobot", "serial"}

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def is_connected(self) -> bool:
        return self._connected

    def status(self) -> Dict[str, Any]:
        return {
            "connected": self._connected,
            "hardware_available": self.hardware_available,
            "backend": self._backend,
            "port": self._port,
            "homed": self._homed,
            "velocity": self._velocity,
            "acceleration": self._acceleration,
            "gripper_open": self._gripper_open,
            "pose": self._pose.to_dict(),
            "commands_executed": len(self._command_log),
        }

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self, port: str = "COM3") -> bool:
        """Attempt to bind a real backend on ``port``; fall back to simulation.

        Returns True when *any* backend (including simulation) is ready.
        Use ``hardware_available`` to discover whether a real device is bound.
        """
        self._port = port
        self._backend = "simulation"
        self._device = None

        # Try pydobot first (preferred high-level wrapper).
        if _has_pydobot():
            try:
                import pydobot  # type: ignore

                self._device = pydobot.Dobot(port=port, verbose=False)
                self._backend = "pydobot"
                self._connected = True
                log.info("DobotBridge: connected via pydobot on %s", port)
                self._refresh_pose_from_device()
                return True
            except Exception as exc:
                log.warning("DobotBridge: pydobot connect failed (%s)", exc)

        # Then raw pyserial.
        if _has_pyserial():
            try:
                import serial  # type: ignore

                self._device = serial.Serial(port=port, baudrate=115200, timeout=1)
                self._backend = "serial"
                self._connected = True
                log.info("DobotBridge: connected via raw serial on %s", port)
                return True
            except Exception as exc:
                log.warning("DobotBridge: serial connect failed (%s)", exc)

        # Pure simulation.
        self._connected = True
        log.info(
            "DobotBridge: no hardware backend available — simulation mode on %s",
            port,
        )
        return True

    def disconnect(self) -> None:
        if self._device is not None:
            try:
                close = getattr(self._device, "close", None)
                if callable(close):
                    close()
            except Exception as exc:
                log.warning("DobotBridge: disconnect error (%s)", exc)
        self._device = None
        self._connected = False
        self._backend = "simulation"

    # ------------------------------------------------------------------
    # Pose
    # ------------------------------------------------------------------

    def get_pose(self) -> Dict[str, float]:
        """Return the current Cartesian + joint pose as a plain dict."""
        if self._backend == "pydobot" and self._device is not None:
            self._refresh_pose_from_device()
        return self._pose.to_dict()

    def _refresh_pose_from_device(self) -> None:
        try:
            x, y, z, r, j1, j2, j3, j4 = self._device.pose()  # type: ignore[attr-defined]
            self._pose = Pose(
                x=float(x), y=float(y), z=float(z), r=float(r),
                joint1=float(j1), joint2=float(j2),
                joint3=float(j3), joint4=float(j4),
            )
        except Exception as exc:
            log.debug("DobotBridge: pose() unsupported on backend (%s)", exc)

    def move_to(
        self,
        x: float,
        y: float,
        z: float,
        r: float = 0.0,
        mode: str = "MOVJ",
    ) -> Dict[str, Any]:
        """Move the end-effector to ``(x, y, z, r)`` and wait for completion."""
        if mode not in _VALID_MODES:
            raise ValueError(f"unknown mode {mode!r} — expected one of {_VALID_MODES}")

        target = Pose(
            x=float(x), y=float(y), z=float(z), r=float(r),
            joint1=self._pose.joint1, joint2=self._pose.joint2,
            joint3=self._pose.joint3, joint4=self._pose.joint4,
        )
        self._record("move_to", x=x, y=y, z=z, r=r, mode=mode)

        if self._backend == "pydobot" and self._device is not None:
            try:
                if mode == "MOVL":
                    self._device.move_to(x, y, z, r, wait=True)  # type: ignore[attr-defined]
                else:
                    self._device.move_to(x, y, z, r, wait=True)  # type: ignore[attr-defined]
                self._refresh_pose_from_device()
                return {"ok": True, "mode": mode, "pose": self._pose.to_dict()}
            except Exception as exc:
                log.warning("DobotBridge: pydobot move_to failed (%s)", exc)

        if self._backend == "serial" and self._device is not None:
            self._send_serial_frame(_build_movj_frame(x, y, z, r, mode))

        # Simulation: derive plausible joint angles from inverse-kinematics-lite.
        self._pose = _simulate_pose(target)
        return {"ok": True, "mode": mode, "pose": self._pose.to_dict()}

    # ------------------------------------------------------------------
    # Speed / gripper / home
    # ------------------------------------------------------------------

    def set_speed(self, velocity: float, acceleration: float) -> Dict[str, Any]:
        """Set joint velocity and acceleration as percentages of maximum."""
        velocity = max(1.0, min(200.0, float(velocity)))
        acceleration = max(1.0, min(200.0, float(acceleration)))
        self._velocity = velocity
        self._acceleration = acceleration
        self._record("set_speed", velocity=velocity, acceleration=acceleration)

        if self._backend == "pydobot" and self._device is not None:
            try:
                self._device.speed(velocity, acceleration)  # type: ignore[attr-defined]
            except Exception as exc:
                log.warning("DobotBridge: pydobot speed failed (%s)", exc)

        return {"ok": True, "velocity": velocity, "acceleration": acceleration}

    def gripper_open(self) -> Dict[str, Any]:
        return self._gripper(open_=True)

    def gripper_close(self) -> Dict[str, Any]:
        return self._gripper(open_=False)

    def _gripper(self, *, open_: bool) -> Dict[str, Any]:
        self._gripper_open = open_
        self._record("gripper_open" if open_ else "gripper_close")

        if self._backend == "pydobot" and self._device is not None:
            try:
                # pydobot uses suck() / grip(); fall through silently if absent.
                fn = getattr(self._device, "grip", None)
                if callable(fn):
                    fn(not open_)
            except Exception as exc:
                log.warning("DobotBridge: pydobot gripper failed (%s)", exc)

        return {"ok": True, "open": open_}

    def home(self) -> Dict[str, Any]:
        """Reset the arm to its mechanical home pose."""
        self._record("home")
        if self._backend == "pydobot" and self._device is not None:
            try:
                fn = getattr(self._device, "home", None)
                if callable(fn):
                    fn()
            except Exception as exc:
                log.warning("DobotBridge: pydobot home failed (%s)", exc)

        self._pose = _HOME_POSE
        self._homed = True
        return {"ok": True, "pose": self._pose.to_dict()}

    # ------------------------------------------------------------------
    # Programs
    # ------------------------------------------------------------------

    def run_program(self, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute a sequence of bridge actions sequentially.

        Each step is ``{"action": "<name>", "kwargs": {...}}``. ``kwargs``
        is optional. Errors are collected per-step rather than aborting,
        so partial programs still report useful telemetry.
        """
        results: List[Dict[str, Any]] = []
        for raw in steps:
            step = _parse_step(raw)
            try:
                value = self.invoke(step.action, **step.kwargs)
                results.append({"action": step.action, "ok": True, "result": value})
            except Exception as exc:
                results.append(
                    {"action": step.action, "ok": False, "error": str(exc)}
                )
        return {"ok": all(r["ok"] for r in results), "steps": results}

    # ------------------------------------------------------------------
    # Generic dispatch
    # ------------------------------------------------------------------

    def invoke(self, action: str, **kwargs: Any) -> Any:
        """Dispatch a string action name to its bound method."""
        registry: Dict[str, Callable[..., Any]] = {
            "connect": self.connect,
            "disconnect": lambda: (self.disconnect(), {"ok": True})[1],
            "get_pose": self.get_pose,
            "move_to": self.move_to,
            "set_speed": self.set_speed,
            "gripper_open": self.gripper_open,
            "gripper_close": self.gripper_close,
            "home": self.home,
            "run_program": self.run_program,
            "status": self.status,
        }
        if action not in registry:
            raise ValueError(f"unknown DOBOT action: {action!r}")
        return registry[action](**kwargs)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _record(self, action: str, **kwargs: Any) -> None:
        self._command_log.append(
            {"t": time.time(), "action": action, "kwargs": dict(kwargs)}
        )

    def _send_serial_frame(self, frame: bytes) -> None:
        try:
            self._device.write(frame)  # type: ignore[union-attr]
            self._device.flush()  # type: ignore[union-attr]
        except Exception as exc:
            log.warning("DobotBridge: serial write failed (%s)", exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_step(raw: Dict[str, Any]) -> _Step:
    if not isinstance(raw, dict):
        raise TypeError(f"program step must be a dict, got {type(raw).__name__}")
    action = raw.get("action")
    if not isinstance(action, str) or not action:
        raise ValueError("program step missing 'action'")
    kwargs = raw.get("kwargs", {}) or {}
    if not isinstance(kwargs, dict):
        raise TypeError("'kwargs' must be a dict")
    return _Step(action=action, kwargs=kwargs)


def _simulate_pose(target: Pose) -> Pose:
    """Approximate joint angles for a target Cartesian pose.

    A simplified planar-IK so simulation results look plausible. Not for
    production trajectory planning — production callers must use the real
    backend.
    """
    base_angle = math.degrees(math.atan2(target.y, target.x or 1e-9))
    reach = math.sqrt(target.x ** 2 + target.y ** 2)
    arm_angle = math.degrees(math.atan2(target.z, reach or 1e-9))
    return Pose(
        x=target.x,
        y=target.y,
        z=target.z,
        r=target.r,
        joint1=base_angle,
        joint2=arm_angle,
        joint3=-arm_angle,
        joint4=target.r,
    )


def _build_movj_frame(x: float, y: float, z: float, r: float, mode: str) -> bytes:
    """Build a minimal DOBOT communication frame for a joint move.

    Real DOBOT framing: 0xAA 0xAA <len> <id> <ctrl> <params...> <checksum>.
    This builder emits a syntactically valid frame for the ``SetPTPCmd``
    (id 84) message; production drivers should use the manufacturer SDK.
    """
    import struct

    ptp_mode = {"MOVJ": 1, "MOVL": 2, "JUMP": 0}.get(mode, 1)
    payload = struct.pack("<Bffff", ptp_mode, x, y, z, r)
    msg_id = 84  # SetPTPCmd
    ctrl = 0x03  # rw=1, isQueued=1
    body = bytes([msg_id, ctrl]) + payload
    length = len(body)
    checksum = (-sum(body)) & 0xFF
    return bytes([0xAA, 0xAA, length]) + body + bytes([checksum])


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_dobot_bridge() -> DobotBridge:
    """Return a fresh :class:`DobotBridge` (caller must call ``connect()``)."""
    return DobotBridge()
