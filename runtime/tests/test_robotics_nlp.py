"""Tests for robotics/nlp_to_motion.py — NLPToMotion."""

from __future__ import annotations

import pytest

from agency.robotics.simulation import SimulationBridge
from agency.robotics.motion_skills import MotionController
from agency.robotics.nlp_to_motion import NLPToMotion


@pytest.fixture
def nlp():
    return NLPToMotion()


@pytest.fixture
def controller():
    sim = SimulationBridge(backend="mock")
    sim.connect()
    return MotionController(sim)


# ------------------------------------------------------------------
# parse() tests
# ------------------------------------------------------------------

def test_parse_walk_forward_with_distance(nlp):
    result = nlp.parse("walk forward 2 meters")
    assert result is not None
    assert result["skill"] == "walk_forward"
    assert result["params"].get("distance") == pytest.approx(2.0)


def test_parse_walk_forward_no_unit(nlp):
    result = nlp.parse("walk forward 3")
    assert result is not None
    assert result["skill"] == "walk_forward"


def test_parse_walk_backward(nlp):
    result = nlp.parse("walk backward 1.5")
    assert result is not None
    assert result["skill"] == "walk_backward"


def test_parse_walk_back(nlp):
    result = nlp.parse("walk back 2")
    assert result is not None
    assert result["skill"] in ("walk_backward", "walk_forward")


def test_parse_turn_with_angle(nlp):
    result = nlp.parse("turn 90 degrees")
    assert result is not None
    assert result["skill"] == "turn"
    assert result["params"].get("angle_degrees") == pytest.approx(90.0)


def test_parse_turn_left(nlp):
    result = nlp.parse("turn left")
    assert result is not None
    assert result["skill"] == "turn"
    assert result["params"].get("angle_degrees") == pytest.approx(90.0)


def test_parse_turn_right(nlp):
    result = nlp.parse("turn right")
    assert result is not None
    assert result["skill"] == "turn"
    assert result["params"].get("angle_degrees") == pytest.approx(-90.0)


def test_parse_sit(nlp):
    result = nlp.parse("sit down")
    assert result is not None
    assert result["skill"] == "sit"
    assert result["params"] == {}


def test_parse_sit_short(nlp):
    result = nlp.parse("sit")
    assert result is not None
    assert result["skill"] == "sit"


def test_parse_stand(nlp):
    result = nlp.parse("stand up")
    assert result is not None
    assert result["skill"] == "stand"


def test_parse_wave(nlp):
    result = nlp.parse("wave")
    assert result is not None
    assert result["skill"] == "wave"


def test_parse_grasp(nlp):
    result = nlp.parse("grasp")
    assert result is not None
    assert result["skill"] == "grasp"


def test_parse_nod(nlp):
    result = nlp.parse("nod")
    assert result is not None
    assert result["skill"] == "nod"


def test_parse_shake_head(nlp):
    result = nlp.parse("shake head")
    assert result is not None
    assert result["skill"] == "shake_head"


def test_parse_case_insensitive(nlp):
    result = nlp.parse("WALK FORWARD 1")
    assert result is not None
    assert result["skill"] == "walk_forward"


def test_parse_no_match_returns_none(nlp):
    result = nlp.parse("do a backflip")
    assert result is None


def test_parse_empty_string_returns_none(nlp):
    result = nlp.parse("")
    assert result is None


# ------------------------------------------------------------------
# execute() tests
# ------------------------------------------------------------------

def test_execute_walk_forward(nlp, controller):
    result = nlp.execute("walk forward 1", controller)
    assert result.get("action") == "walk_forward"
    assert "error" not in result


def test_execute_sit(nlp, controller):
    result = nlp.execute("sit down", controller)
    assert result.get("action") == "sit"


def test_execute_stand(nlp, controller):
    result = nlp.execute("stand up", controller)
    assert result.get("action") == "stand"


def test_execute_no_match_returns_error(nlp, controller):
    result = nlp.execute("do a somersault", controller)
    assert "error" in result
    assert result["error"] == "no match"


def test_execute_turn_right(nlp, controller):
    result = nlp.execute("turn right", controller)
    assert result.get("action") == "turn"


def test_execute_wave(nlp, controller):
    result = nlp.execute("wave", controller)
    assert result.get("action") == "wave"


def test_execute_nod(nlp, controller):
    result = nlp.execute("nod", controller)
    assert result.get("action") == "nod"
