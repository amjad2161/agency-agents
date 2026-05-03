"""Tests for the DOBOT bridge — all run in simulation mode."""

from __future__ import annotations

import pytest

from agency.bridges.dobot import DobotBridge, Pose, get_dobot_bridge


@pytest.fixture()
def bridge() -> DobotBridge:
    b = get_dobot_bridge()
    b.connect(port="SIM_PORT")
    return b


def test_factory_returns_unconnected_bridge() -> None:
    b = get_dobot_bridge()
    assert isinstance(b, DobotBridge)
    assert b.is_connected is False
    assert b.hardware_available is False


def test_connect_falls_back_to_simulation(bridge: DobotBridge) -> None:
    assert bridge.is_connected is True
    # Real backend should not be reported on a CI machine.
    assert bridge.backend == "simulation"
    assert bridge.hardware_available is False
    assert bridge.status()["port"] == "SIM_PORT"


def test_get_pose_returns_default_pose(bridge: DobotBridge) -> None:
    pose = bridge.get_pose()
    assert set(pose.keys()) == {
        "x", "y", "z", "r", "joint1", "joint2", "joint3", "joint4",
    }
    assert pose["x"] == pytest.approx(200.0)
    assert pose["z"] == pytest.approx(50.0)


def test_move_to_updates_pose(bridge: DobotBridge) -> None:
    result = bridge.move_to(150.0, 50.0, 30.0, r=10.0, mode="MOVL")
    assert result["ok"] is True
    pose = bridge.get_pose()
    assert pose["x"] == pytest.approx(150.0)
    assert pose["y"] == pytest.approx(50.0)
    assert pose["z"] == pytest.approx(30.0)
    assert pose["r"] == pytest.approx(10.0)


def test_move_to_rejects_unknown_mode(bridge: DobotBridge) -> None:
    with pytest.raises(ValueError):
        bridge.move_to(100.0, 0.0, 0.0, mode="WIGGLE")


def test_set_speed_clamps_to_safe_range(bridge: DobotBridge) -> None:
    out = bridge.set_speed(velocity=999.0, acceleration=-5.0)
    assert out["velocity"] == 200.0
    assert out["acceleration"] == 1.0


def test_gripper_open_close_round_trip(bridge: DobotBridge) -> None:
    closed = bridge.gripper_close()
    assert closed["open"] is False
    opened = bridge.gripper_open()
    assert opened["open"] is True
    assert bridge.status()["gripper_open"] is True


def test_home_resets_pose_and_marks_homed(bridge: DobotBridge) -> None:
    bridge.move_to(123.0, 45.0, 67.0)
    out = bridge.home()
    assert out["ok"] is True
    assert bridge.status()["homed"] is True
    pose = bridge.get_pose()
    assert pose["x"] == pytest.approx(200.0)
    assert pose["z"] == pytest.approx(50.0)


def test_run_program_executes_steps_in_order(bridge: DobotBridge) -> None:
    program = [
        {"action": "home"},
        {"action": "move_to", "kwargs": {"x": 180.0, "y": 20.0, "z": 40.0}},
        {"action": "gripper_close"},
        {"action": "gripper_open"},
    ]
    result = bridge.run_program(program)
    assert result["ok"] is True
    actions = [s["action"] for s in result["steps"]]
    assert actions == ["home", "move_to", "gripper_close", "gripper_open"]


def test_run_program_collects_per_step_errors(bridge: DobotBridge) -> None:
    program = [
        {"action": "move_to", "kwargs": {"x": 100.0, "y": 0.0, "z": 0.0, "mode": "BOGUS"}},
        {"action": "home"},
    ]
    result = bridge.run_program(program)
    assert result["ok"] is False
    assert result["steps"][0]["ok"] is False
    assert "BOGUS" in result["steps"][0]["error"]
    # Subsequent step still ran.
    assert result["steps"][1]["ok"] is True


def test_invoke_dispatches_known_actions(bridge: DobotBridge) -> None:
    pose = bridge.invoke("get_pose")
    assert "x" in pose

    moved = bridge.invoke("move_to", x=170.0, y=10.0, z=5.0)
    assert moved["ok"] is True

    with pytest.raises(ValueError):
        bridge.invoke("teleport", x=0)


def test_pose_dataclass_is_frozen() -> None:
    p = Pose()
    with pytest.raises((AttributeError, Exception)):
        p.x = 999.0  # type: ignore[misc]


def test_status_reports_command_count(bridge: DobotBridge) -> None:
    bridge.move_to(150.0, 0.0, 0.0)
    bridge.set_speed(50.0, 50.0)
    bridge.gripper_close()
    status = bridge.status()
    assert status["commands_executed"] >= 3
    assert status["backend"] == "simulation"
