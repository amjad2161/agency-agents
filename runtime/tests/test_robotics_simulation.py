"""Tests for robotics/simulation.py — SimulationBridge (mock backend)."""

from __future__ import annotations

import pytest

from agency.robotics.simulation import SimulationBridge


@pytest.fixture
def sim():
    s = SimulationBridge(backend="mock")
    s.connect()
    yield s
    s.disconnect()


def test_backend_is_mock():
    s = SimulationBridge(backend="mock")
    assert s.backend == "mock"


def test_connect_returns_true(sim):
    # Already connected by fixture — test a fresh one
    s = SimulationBridge(backend="mock")
    result = s.connect()
    assert result is True


def test_connected_after_connect(sim):
    assert sim.connected is True


def test_disconnect_sets_connected_false(sim):
    sim.disconnect()
    assert sim.connected is False


def test_load_robot_returns_true(sim):
    result = sim.load_robot()
    assert result is True


def test_load_robot_with_path(sim):
    result = sim.load_robot(model_path="some_robot.urdf")
    assert result is True


def test_get_joint_states_returns_list(sim):
    states = sim.get_joint_states()
    assert isinstance(states, list)


def test_get_joint_states_has_fields(sim):
    states = sim.get_joint_states()
    assert len(states) > 0
    for s in states:
        assert "name" in s
        assert "position" in s
        assert "velocity" in s
        assert "torque" in s


def test_set_joint_position_valid(sim):
    result = sim.set_joint_position(0, 1.5)
    assert result is True


def test_set_joint_position_updates_state(sim):
    sim.set_joint_position(0, 2.0)
    states = sim.get_joint_states()
    assert states[0]["position"] == pytest.approx(2.0)


def test_set_joint_position_invalid_id(sim):
    result = sim.set_joint_position(999, 1.0)
    assert result is False


def test_step_does_not_raise(sim):
    sim.step()  # should not raise


def test_step_does_not_raise_twice(sim):
    # MOCK backend may or may not change position; verify no exception raised.
    sim.step()
    sim.step()


def test_get_base_position_returns_tuple(sim):
    pos = sim.get_base_position()
    assert isinstance(pos, tuple)
    assert len(pos) == 3


def test_get_base_position_floats(sim):
    pos = sim.get_base_position()
    for v in pos:
        assert isinstance(v, float)


def test_reset_restores_state(sim):
    sim.set_joint_position(0, 3.0)
    sim.step()
    sim.reset()
    states = sim.get_joint_states()
    assert states[0]["position"] == 0.0
    pos = sim.get_base_position()
    assert pos == (0.0, 0.0, 0.0)


def test_auto_backend_falls_back_to_mock():
    s = SimulationBridge(backend="pybullet")
    # If pybullet not installed, should fall back gracefully after connect
    s.connect()
    # It either connected to pybullet or fell back to mock — should be connected
    assert s.connected is True
