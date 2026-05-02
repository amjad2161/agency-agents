"""Motion skill library for the JARVIS humanoid robot.

Each skill accepts a SimulationBridge and executes a motion primitive.
All skills return True on success, False on non-critical failure, and
raise SimulationError on critical failures.

Skills log via the JARVIS structured logger and record to the audit log.

Usage
-----
    from agency.robotics.simulation import SimulationBridge, SimulationBackend
    from agency.robotics.motion_skills import walk_forward, wave_hand

    sim = SimulationBridge(SimulationBackend.MOCK)
    sim.load_humanoid()
    walk_forward(sim, distance_m=1.0)
    wave_hand(sim, hand="right")
    sim.disconnect()
"""

from __future__ import annotations

import math
import time
from typing import Optional

from ..logging import get_logger
from .simulation import SimulationBridge, SimulationError, HUMANOID_JOINTS

log = get_logger()

# ---------------------------------------------------------------------------
# Audit helper (thin shim — avoids mandatory audit import at module level)
# ---------------------------------------------------------------------------

def _audit(event: str, payload: dict) -> None:
    """Append a robotics event to the JARVIS audit log if audit is available."""
    try:
        from ..audit import append as _append
        _append(event, payload)
    except Exception:
        pass   # audit log is best-effort; never break motion skills


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _steps_for(sim: SimulationBridge, seconds: float) -> int:
    """Compute simulation steps for a real-time duration."""
    dt = getattr(getattr(sim, "_impl", sim), "_dt", 1.0 / 240.0)
    return max(1, int(seconds / dt))


def _set_legs_walk(sim: SimulationBridge, phase: float, amplitude: float = 0.4) -> None:
    """Parametric walking gait — alternating hip/knee oscillation."""
    sim.set_joint_position("left_hip_pitch",  math.sin(phase) * amplitude)
    sim.set_joint_position("right_hip_pitch", math.sin(phase + math.pi) * amplitude)
    sim.set_joint_position("left_knee",  max(0, math.sin(phase + math.pi / 4)) * amplitude * 0.6)
    sim.set_joint_position("right_knee", max(0, math.sin(phase + math.pi * 5 / 4)) * amplitude * 0.6)


# ---------------------------------------------------------------------------
# Locomotion skills
# ---------------------------------------------------------------------------

def walk_forward(sim: SimulationBridge, distance_m: float, speed: float = 0.5) -> bool:
    """Walk forward *distance_m* metres at *speed* m/s.

    Returns True on success.
    """
    log.info("motion.walk_forward distance=%.2f speed=%.2f", distance_m, speed)
    _audit("robot.motion", {"skill": "walk_forward", "distance_m": distance_m, "speed": speed})
    try:
        duration = distance_m / max(speed, 0.01)
        step_count = _steps_for(sim, duration)
        dt = getattr(getattr(sim, "_impl", sim), "_dt", 1.0 / 240.0)
        for i in range(step_count):
            phase = 2 * math.pi * (i * dt / 0.5)   # 0.5 s gait cycle
            _set_legs_walk(sim, phase)
            sim.set_joint_velocity("left_hip_pitch",  speed * 0.5)
            sim.set_joint_velocity("right_hip_pitch", speed * 0.5)
            sim.step()
        # Return to neutral after walk
        for j in HUMANOID_JOINTS:
            sim.set_joint_position(j, 0.0)
        return True
    except SimulationError:
        raise
    except Exception as exc:
        log.warning("walk_forward failed: %s", exc)
        return False


def walk_backward(sim: SimulationBridge, distance_m: float, speed: float = 0.3) -> bool:
    """Walk backward *distance_m* metres at *speed* m/s."""
    log.info("motion.walk_backward distance=%.2f speed=%.2f", distance_m, speed)
    _audit("robot.motion", {"skill": "walk_backward", "distance_m": distance_m, "speed": speed})
    try:
        duration = distance_m / max(speed, 0.01)
        step_count = _steps_for(sim, duration)
        dt = getattr(getattr(sim, "_impl", sim), "_dt", 1.0 / 240.0)
        for i in range(step_count):
            phase = 2 * math.pi * (i * dt / 0.5)
            _set_legs_walk(sim, -phase)   # negative phase = backward
            sim.step()
        for j in HUMANOID_JOINTS:
            sim.set_joint_position(j, 0.0)
        return True
    except SimulationError:
        raise
    except Exception as exc:
        log.warning("walk_backward failed: %s", exc)
        return False


def turn_left(sim: SimulationBridge, angle_deg: float) -> bool:
    """Turn left *angle_deg* degrees in-place."""
    log.info("motion.turn_left angle=%.1f", angle_deg)
    _audit("robot.motion", {"skill": "turn_left", "angle_deg": angle_deg})
    try:
        # Rotate by applying yaw torque for proportional steps
        angle_rad = math.radians(angle_deg)
        steps = max(1, int(abs(angle_rad) / (math.pi / 8)))
        delta = angle_rad / steps
        for _ in range(steps):
            sim.set_joint_position("left_hip_yaw",  -delta)
            sim.set_joint_position("right_hip_yaw",  delta)
            sim.step()
        return True
    except SimulationError:
        raise
    except Exception as exc:
        log.warning("turn_left failed: %s", exc)
        return False


def turn_right(sim: SimulationBridge, angle_deg: float) -> bool:
    """Turn right *angle_deg* degrees in-place."""
    log.info("motion.turn_right angle=%.1f", angle_deg)
    _audit("robot.motion", {"skill": "turn_right", "angle_deg": angle_deg})
    try:
        angle_rad = math.radians(angle_deg)
        steps = max(1, int(abs(angle_rad) / (math.pi / 8)))
        delta = angle_rad / steps
        for _ in range(steps):
            sim.set_joint_position("left_hip_yaw",   delta)
            sim.set_joint_position("right_hip_yaw", -delta)
            sim.step()
        return True
    except SimulationError:
        raise
    except Exception as exc:
        log.warning("turn_right failed: %s", exc)
        return False


def stand_still(sim: SimulationBridge) -> bool:
    """Hold standing pose — neutral joints, zero velocity."""
    log.info("motion.stand_still")
    _audit("robot.motion", {"skill": "stand_still"})
    try:
        for j in HUMANOID_JOINTS:
            sim.set_joint_position(j, 0.0)
            sim.set_joint_velocity(j, 0.0)
        sim.step()
        return True
    except SimulationError:
        raise
    except Exception as exc:
        log.warning("stand_still failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Posture skills
# ---------------------------------------------------------------------------

def sit_down(sim: SimulationBridge) -> bool:
    """Transition from standing to sitting."""
    log.info("motion.sit_down")
    _audit("robot.motion", {"skill": "sit_down"})
    try:
        # Flex hips and knees to sitting angles
        target = {
            "left_hip_pitch":  math.radians(90),
            "right_hip_pitch": math.radians(90),
            "left_knee":       math.radians(90),
            "right_knee":      math.radians(90),
        }
        steps = 60
        for step in range(steps + 1):
            t = step / steps
            for j, angle in target.items():
                sim.set_joint_position(j, angle * t)
            sim.step()
        return True
    except SimulationError:
        raise
    except Exception as exc:
        log.warning("sit_down failed: %s", exc)
        return False


def stand_up(sim: SimulationBridge) -> bool:
    """Transition from sitting to standing."""
    log.info("motion.stand_up")
    _audit("robot.motion", {"skill": "stand_up"})
    try:
        sitting = {
            "left_hip_pitch":  math.radians(90),
            "right_hip_pitch": math.radians(90),
            "left_knee":       math.radians(90),
            "right_knee":      math.radians(90),
        }
        steps = 60
        for step in range(steps + 1):
            t = 1.0 - step / steps   # interpolate back to 0
            for j, angle in sitting.items():
                sim.set_joint_position(j, angle * t)
            sim.step()
        # Neutral
        for j in HUMANOID_JOINTS:
            sim.set_joint_position(j, 0.0)
        return True
    except SimulationError:
        raise
    except Exception as exc:
        log.warning("stand_up failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Expressive / manipulation skills
# ---------------------------------------------------------------------------

def wave_hand(sim: SimulationBridge, hand: str = "right") -> bool:
    """Wave the selected hand (default: right)."""
    log.info("motion.wave_hand hand=%s", hand)
    _audit("robot.motion", {"skill": "wave_hand", "hand": hand})
    try:
        if hand.lower() == "right":
            shoulder = "right_shoulder_pitch"
            elbow    = "right_elbow"
        else:
            shoulder = "left_shoulder_pitch"
            elbow    = "left_elbow"

        # Raise arm
        sim.set_joint_position(shoulder, math.radians(90))
        sim.set_joint_position(elbow,    math.radians(-30))
        for _ in range(30):
            sim.step()

        # Wave: oscillate elbow 3 times
        for cycle in range(3):
            for angle in [60, 0, 60, 0]:
                sim.set_joint_position(elbow, math.radians(-angle))
                for _ in range(10):
                    sim.step()

        # Lower arm
        sim.set_joint_position(shoulder, 0.0)
        sim.set_joint_position(elbow,    0.0)
        for _ in range(30):
            sim.step()
        return True
    except SimulationError:
        raise
    except Exception as exc:
        log.warning("wave_hand failed: %s", exc)
        return False


def nod_head(sim: SimulationBridge, times: int = 2) -> bool:
    """Nod head *times* times."""
    log.info("motion.nod_head times=%d", times)
    _audit("robot.motion", {"skill": "nod_head", "times": times})
    try:
        for _ in range(times):
            sim.set_joint_position("neck_pitch", math.radians(20))
            for _ in range(15):
                sim.step()
            sim.set_joint_position("neck_pitch", 0.0)
            for _ in range(15):
                sim.step()
        return True
    except SimulationError:
        raise
    except Exception as exc:
        log.warning("nod_head failed: %s", exc)
        return False


def reach_forward(sim: SimulationBridge, distance_m: float = 0.3) -> bool:
    """Extend both arms forward by *distance_m* (mapped to shoulder angle)."""
    log.info("motion.reach_forward distance=%.2f", distance_m)
    _audit("robot.motion", {"skill": "reach_forward", "distance_m": distance_m})
    try:
        # Rough mapping: 0.3 m reach ≈ 45° shoulder flexion
        angle_rad = min(math.pi / 2, distance_m / 0.3 * math.radians(45))
        sim.set_joint_position("left_shoulder_pitch",  angle_rad)
        sim.set_joint_position("right_shoulder_pitch", angle_rad)
        for _ in range(30):
            sim.step()
        return True
    except SimulationError:
        raise
    except Exception as exc:
        log.warning("reach_forward failed: %s", exc)
        return False


def grasp_object(sim: SimulationBridge, object_name: str = "") -> bool:
    """Close fingers / grip an object (gripper stub)."""
    log.info("motion.grasp_object object=%r", object_name)
    _audit("robot.motion", {"skill": "grasp_object", "object": object_name})
    try:
        # In real hardware: close gripper servos.
        # In simulation: rotate elbow joints slightly inward.
        sim.set_joint_position("right_elbow", math.radians(-15))
        sim.set_joint_position("left_elbow",  math.radians(-15))
        for _ in range(20):
            sim.step()
        return True
    except SimulationError:
        raise
    except Exception as exc:
        log.warning("grasp_object failed: %s", exc)
        return False


def release_object(sim: SimulationBridge) -> bool:
    """Open fingers / release held object."""
    log.info("motion.release_object")
    _audit("robot.motion", {"skill": "release_object"})
    try:
        sim.set_joint_position("right_elbow", 0.0)
        sim.set_joint_position("left_elbow",  0.0)
        for _ in range(20):
            sim.step()
        return True
    except SimulationError:
        raise
    except Exception as exc:
        log.warning("release_object failed: %s", exc)
        return False
