"""Tests for bridges.cubesandbox."""
from __future__ import annotations

import pytest

from bridges.cubesandbox import CubeSandbox, GRAVITY_Y


@pytest.fixture
def sandbox() -> CubeSandbox:
    return CubeSandbox()


def test_scene_html_includes_three_and_cannon(sandbox: CubeSandbox) -> None:
    html = sandbox.generate_scene_html()
    assert "three" in html
    assert "cannon-es" in html
    assert "WebGLRenderer" in html
    assert "World" in html


def test_scene_html_includes_seeded_objects(sandbox: CubeSandbox) -> None:
    html = sandbox.generate_scene_html(
        objects=[{"type": "sphere", "x": 0, "y": 5, "z": 0,
                  "color": "#ff0000"}])
    assert "#ff0000" in html
    assert "sphere" in html


def test_scene_html_invalid_object_type(sandbox: CubeSandbox) -> None:
    with pytest.raises(ValueError):
        sandbox.generate_scene_html(objects=[{"type": "donut"}])


def test_scene_html_no_gravity_zeros_world(sandbox: CubeSandbox) -> None:
    html = sandbox.generate_scene_html(gravity=False)
    assert "Vec3(0, 0.0, 0)" in html


def test_add_object_returns_state_with_object(sandbox: CubeSandbox) -> None:
    state = sandbox.add_object(None, "box", (1.0, 2.0, 3.0))
    assert len(state["objects"]) == 1
    obj = state["objects"][0]
    assert obj["type"] == "box"
    assert obj["x"] == 1.0
    assert obj["y"] == 2.0
    assert obj["z"] == 3.0
    assert "id" in obj


def test_add_object_accepts_dict_position(sandbox: CubeSandbox) -> None:
    state = sandbox.add_object(
        None, "sphere", {"x": 0, "y": 4, "z": -1},
        properties={"color": "#abc", "size": 0.5})
    obj = state["objects"][0]
    assert obj["color"] == "#abc"
    assert obj["size"] == 0.5
    assert obj["y"] == 4.0


def test_add_object_invalid_type(sandbox: CubeSandbox) -> None:
    with pytest.raises(ValueError):
        sandbox.add_object(None, "torus", (0, 0, 0))


def test_add_object_invalid_position(sandbox: CubeSandbox) -> None:
    with pytest.raises(ValueError):
        sandbox.add_object(None, "box", (1, 2))


def test_add_plane_is_static(sandbox: CubeSandbox) -> None:
    state = sandbox.add_object(None, "plane", (0, 0, 0))
    assert state["objects"][0]["static"] is True
    assert state["objects"][0]["mass"] == 0.0


def test_simulate_step_applies_gravity(sandbox: CubeSandbox) -> None:
    state = sandbox.add_object(
        None, "box", (0, 10, 0), {"size": 1.0})
    sandbox.simulate_step(state, dt=0.1)
    obj = state["objects"][0]
    assert obj["vy"] == pytest.approx(GRAVITY_Y * 0.1, rel=1e-6)
    assert obj["y"] < 10.0


def test_simulate_step_static_plane_does_not_move(sandbox: CubeSandbox) -> None:
    state = sandbox.add_object(None, "plane", (0, 0, 0))
    sandbox.simulate_step(state, dt=0.1)
    sandbox.simulate_step(state, dt=0.1)
    obj = state["objects"][0]
    assert obj["x"] == 0.0
    assert obj["y"] == 0.0
    assert obj["z"] == 0.0


def test_simulate_step_floor_collision_bounces(sandbox: CubeSandbox) -> None:
    state = sandbox.add_object(
        None, "box", (0, 0.4, 0), {"size": 1.0, "vy": -5.0})
    sandbox.simulate_step(state, dt=0.05)
    obj = state["objects"][0]
    assert obj["y"] >= 0.5 - 1e-6
    assert obj["vy"] >= 0.0


def test_simulate_step_advances_time(sandbox: CubeSandbox) -> None:
    state = sandbox.add_object(None, "box", (0, 5, 0))
    sandbox.simulate_step(state, dt=0.1)
    sandbox.simulate_step(state, dt=0.1)
    assert state["t"] == pytest.approx(0.2)


def test_simulate_step_no_gravity_keeps_velocity(
    sandbox: CubeSandbox,
) -> None:
    state = {"objects": [], "gravity": False, "t": 0.0}
    sandbox.add_object(state, "box", (0, 5, 0), {"vx": 2.0})
    sandbox.simulate_step(state, dt=1.0)
    obj = state["objects"][0]
    assert obj["x"] == pytest.approx(2.0)
    assert obj["vy"] == 0.0


def test_invoke_dispatches_simulate_step(sandbox: CubeSandbox) -> None:
    state = sandbox.add_object(None, "box", (0, 3, 0))
    out = sandbox.invoke("simulate_step", scene_state=state, dt=0.05)
    assert out is state


def test_invoke_unknown_action(sandbox: CubeSandbox) -> None:
    with pytest.raises(ValueError):
        sandbox.invoke("teleport")


def test_normalize_state_rejects_non_dict(sandbox: CubeSandbox) -> None:
    with pytest.raises(ValueError):
        sandbox.simulate_step("not a state")  # type: ignore[arg-type]
