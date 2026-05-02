"""Tests for bridges.cubesandbox."""

from __future__ import annotations

from pathlib import Path

import pytest

from bridges.cubesandbox import CubeSandboxBridge


@pytest.fixture
def sb(tmp_path: Path) -> CubeSandboxBridge:
    return CubeSandboxBridge(asset_dir=tmp_path / "scenes")


def test_create_scene_writes_html_with_three_and_cannon(sb):
    out = sb.create_scene([
        {"type": "box", "position": (0, 5, 0), "color": "#ff0000"},
        {"type": "sphere", "position": (1, 8, 0), "color": "#00ff00"},
    ])
    assert "scene_id" in out
    assert out["html_path"].exists()
    html = out["html_path"].read_text(encoding="utf-8")
    assert "three" in html.lower()
    assert "cannon-es" in html.lower()
    assert "WebGLRenderer" in html
    assert len(out["object_ids"]) == 2


def test_create_scene_with_no_objects(sb):
    out = sb.create_scene()
    assert out["object_ids"] == []
    assert out["html_path"].exists()


def test_add_object_returns_id_and_stores_state(sb):
    s = sb.create_scene()
    sid = s["scene_id"]
    oid = sb.add_object(sid, type="box", position=(0, 3, 0), mass=2.0, color="#abcdef")
    state = sb.get_state(sid)
    matched = [o for o in state["objects"] if o["id"] == oid]
    assert len(matched) == 1
    assert matched[0]["mass"] == 2.0
    assert matched[0]["color"] == "#abcdef"
    assert matched[0]["position"] == [0.0, 3.0, 0.0]


def test_add_object_unknown_type_raises(sb):
    s = sb.create_scene()
    with pytest.raises(ValueError, match="unknown type"):
        sb.add_object(s["scene_id"], type="torus")


def test_simulate_physics_falls_under_gravity(sb):
    s = sb.create_scene()
    sid = s["scene_id"]
    oid = sb.add_object(sid, type="box", position=(0, 10, 0), size=1.0)
    final = sb.simulate_physics(sid, steps=10, dt=0.1)
    obj = next(o for o in final if o["id"] == oid)
    # After 1 second of free fall (10 steps * 0.1) Y must be lower than start.
    assert obj["position"][1] < 10.0
    # Velocity must be downward.
    assert obj["velocity"][1] < 0


def test_simulate_physics_settles_on_floor(sb):
    s = sb.create_scene()
    sid = s["scene_id"]
    oid = sb.add_object(sid, type="sphere", position=(0, 8, 0), size=1.0)
    sb.simulate_physics(sid, steps=600, dt=0.016)
    state = sb.get_state(sid)
    obj = next(o for o in state["objects"] if o["id"] == oid)
    # Floor contact at y = radius = 0.5
    assert obj["position"][1] >= 0.49
    # Energy bled away — Y velocity small.
    assert abs(obj["velocity"][1]) < 1.5


def test_simulate_physics_static_object_does_not_move(sb):
    s = sb.create_scene()
    sid = s["scene_id"]
    oid = sb.add_object(sid, type="box", position=(2, 5, 1), static=True)
    sb.simulate_physics(sid, steps=50, dt=0.1)
    state = sb.get_state(sid)
    obj = next(o for o in state["objects"] if o["id"] == oid)
    assert obj["position"] == [2.0, 5.0, 1.0]


def test_apply_force_changes_velocity(sb):
    s = sb.create_scene()
    sid = s["scene_id"]
    oid = sb.add_object(sid, type="box", position=(0, 5, 0), mass=2.0)
    before = sb.get_state(sid)["objects"][0]["velocity"]
    assert before == [0.0, 0.0, 0.0]
    sb.apply_force(sid, oid, (10.0, 0.0, 0.0))
    after = sb.get_state(sid)["objects"][0]["velocity"]
    # 10 N / 2 kg = 5 m/s along x
    assert after[0] == pytest.approx(5.0)


def test_apply_force_to_static_raises(sb):
    s = sb.create_scene()
    sid = s["scene_id"]
    oid = sb.add_object(sid, type="box", position=(0, 5, 0), static=True)
    with pytest.raises(ValueError, match="static"):
        sb.apply_force(sid, oid, (1, 0, 0))


def test_apply_force_unknown_object_raises(sb):
    s = sb.create_scene()
    with pytest.raises(KeyError):
        sb.apply_force(s["scene_id"], "obj_missing", (1, 0, 0))


def test_get_state_unknown_scene_raises(sb):
    with pytest.raises(KeyError, match="scene"):
        sb.get_state("nope")


def test_simulate_invalid_dt(sb):
    s = sb.create_scene()
    with pytest.raises(ValueError, match="dt"):
        sb.simulate_physics(s["scene_id"], steps=1, dt=0)


def test_invoke_dispatches(sb):
    s = sb.invoke("create_scene", objects=[{"type": "box"}])
    assert s["html_path"].exists()


def test_invoke_unknown_action(sb):
    with pytest.raises(ValueError, match="unknown action"):
        sb.invoke("teleport_universe")
