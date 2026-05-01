"""Tests for robotics/motion_skills.py — MotionController."""

from __future__ import annotations

import pytest

from agency.robotics.simulation import SimulationBridge
from agency.robotics.motion_skills import MotionController


@pytest.fixture
def controller():
    sim = SimulationBridge(backend="mock")
    sim.connect()
    return MotionController(sim)


def _check_result(result: dict, action: str) -> None:
    assert isinstance(result, dict)
    assert result.get("action") == action
    assert result.get("status") in ("ok", "mock")
    assert isinstance(result.get("duration_s"), float)
    assert result["duration_s"] >= 0


def test_walk_forward(controller):
    result = controller.walk_forward(2.0)
    _check_result(result, "walk_forward")


def test_walk_forward_custom_speed(controller):
    result = controller.walk_forward(1.0, speed=1.0)
    _check_result(result, "walk_forward")
    assert result["distance"] == 1.0


def test_walk_backward(controller):
    result = controller.walk_backward(1.5)
    _check_result(result, "walk_backward")


def test_walk_backward_default_speed(controller):
    result = controller.walk_backward(1.0)
    assert result["speed"] == 0.3


def test_turn(controller):
    result = controller.turn(90.0)
    _check_result(result, "turn")


def test_turn_negative_angle(controller):
    result = controller.turn(-45.0)
    _check_result(result, "turn")
    assert result["angle_degrees"] == -45.0


def test_sit(controller):
    result = controller.sit()
    _check_result(result, "sit")


def test_stand(controller):
    result = controller.stand()
    _check_result(result, "stand")


def test_wave(controller):
    result = controller.wave()
    _check_result(result, "wave")


def test_grasp_default(controller):
    result = controller.grasp()
    _check_result(result, "grasp")
    assert result.get("object") == "object"


def test_grasp_named_object(controller):
    result = controller.grasp("bottle")
    assert result["object"] == "bottle"


def test_release(controller):
    result = controller.release()
    _check_result(result, "release")


def test_nod(controller):
    result = controller.nod()
    _check_result(result, "nod")


def test_shake_head(controller):
    result = controller.shake_head()
    _check_result(result, "shake_head")


def test_raise_arm_right(controller):
    result = controller.raise_arm("right")
    _check_result(result, "raise_arm")
    assert result.get("arm") == "right"


def test_raise_arm_left(controller):
    result = controller.raise_arm("left")
    assert result.get("arm") == "left"


def test_lower_arm_right(controller):
    result = controller.lower_arm("right")
    _check_result(result, "lower_arm")


def test_lower_arm_left(controller):
    result = controller.lower_arm("left")
    assert result.get("arm") == "left"


def test_sequence_of_moves(controller):
    """Execute a realistic sequence without errors."""
    controller.stand()
    controller.walk_forward(1.0)
    controller.turn(90.0)
    controller.walk_forward(0.5)
    controller.sit()


def test_duration_proportional_to_distance(controller):
    r1 = controller.walk_forward(1.0, speed=1.0)
    r2 = controller.walk_forward(2.0, speed=1.0)
    assert r2["duration_s"] > r1["duration_s"]
