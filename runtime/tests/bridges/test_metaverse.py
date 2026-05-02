"""Tests for the Metaverse WebXR bridge."""

from __future__ import annotations

from pathlib import Path

import pytest

from agency.bridges.metaverse import (
    MetaverseBridge,
    VALID_ASSETS,
    VALID_ROLES,
    VALID_SIZES,
    VALID_THEMES,
    get_metaverse_bridge,
)


@pytest.fixture()
def bridge(tmp_path: Path) -> MetaverseBridge:
    return get_metaverse_bridge(assets_dir=tmp_path / "metaverse")


def test_factory_returns_empty_bridge(tmp_path: Path) -> None:
    b = get_metaverse_bridge(assets_dir=tmp_path)
    assert isinstance(b, MetaverseBridge)


def test_create_world_writes_html_with_aframe(bridge: MetaverseBridge) -> None:
    out = bridge.create_world(theme="cyberpunk", size="medium")
    assert out["ok"] is True
    assert out["theme"] == "cyberpunk"
    assert out["size"] == "medium"

    html_path = Path(out["html_path"])
    assert html_path.exists()
    text = html_path.read_text(encoding="utf-8")
    assert "<a-scene" in text
    assert "aframe" in text
    assert "vr-mode-ui" in text
    assert out["world_id"] in text


def test_create_world_rejects_bad_theme(bridge: MetaverseBridge) -> None:
    with pytest.raises(ValueError):
        bridge.create_world(theme="atlantis", size="medium")


def test_create_world_rejects_bad_size(bridge: MetaverseBridge) -> None:
    with pytest.raises(ValueError):
        bridge.create_world(theme="cyberpunk", size="huge")


def test_join_session_returns_token(bridge: MetaverseBridge) -> None:
    world = bridge.create_world(theme="cyberpunk", size="small")
    sess = bridge.join_session(world["world_id"], "Amjad")
    assert sess["ok"] is True
    assert sess["session_token"].startswith("sess_")
    state = bridge.get_world_state(world["world_id"])
    assert "Amjad" in state["users"]


def test_join_session_rejects_bad_user(bridge: MetaverseBridge) -> None:
    world = bridge.create_world(theme="cyberpunk", size="small")
    with pytest.raises(ValueError):
        bridge.join_session(world["world_id"], "")


def test_join_session_unknown_world(bridge: MetaverseBridge) -> None:
    with pytest.raises(KeyError):
        bridge.join_session("world_nope", "Amjad")


def test_add_object_appends_to_world(bridge: MetaverseBridge) -> None:
    world = bridge.create_world(theme="forest", size="medium")
    initial_state = bridge.get_world_state(world["world_id"])
    initial_count = len(initial_state["objects"])

    out = bridge.add_object(
        world["world_id"], "sphere", [1.0, 1.0, -3.0], {"color": "#ff00aa", "label": "Hi"}
    )
    assert out["object_id"].startswith("obj_")

    state = bridge.get_world_state(world["world_id"])
    assert len(state["objects"]) == initial_count + 1
    types = {o["asset_type"] for o in state["objects"]}
    assert "sphere" in types

    html = Path(world["html_path"]).read_text(encoding="utf-8")
    assert "Hi" in html
    assert "#ff00aa" in html


def test_add_object_rejects_bad_asset_type(bridge: MetaverseBridge) -> None:
    world = bridge.create_world(theme="cyberpunk", size="small")
    with pytest.raises(ValueError):
        bridge.add_object(world["world_id"], "dragon", [0.0, 0.0, 0.0])


def test_add_object_rejects_bad_position(bridge: MetaverseBridge) -> None:
    world = bridge.create_world(theme="cyberpunk", size="small")
    with pytest.raises(ValueError):
        bridge.add_object(world["world_id"], "cube", [0.0, 0.0])


def test_set_environment_updates_state_and_html(bridge: MetaverseBridge) -> None:
    world = bridge.create_world(theme="spacestation", size="small")
    out = bridge.set_environment(world["world_id"], sky="dawn", fog=False, ambient_light=0.7)
    assert out["sky"] == "dawn"
    assert out["fog"] is False
    state = bridge.get_world_state(world["world_id"])
    assert state["sky"] == "dawn"
    assert state["fog"] is False
    assert state["ambient_light"] == pytest.approx(0.7)


def test_set_environment_rejects_bad_sky(bridge: MetaverseBridge) -> None:
    world = bridge.create_world(theme="cyberpunk", size="small")
    with pytest.raises(ValueError):
        bridge.set_environment(world["world_id"], sky="rainbow")


def test_set_environment_rejects_bad_ambient(bridge: MetaverseBridge) -> None:
    world = bridge.create_world(theme="cyberpunk", size="small")
    with pytest.raises(ValueError):
        bridge.set_environment(world["world_id"], ambient_light=2.0)


def test_generate_avatar_npc_returns_aframe_entity(bridge: MetaverseBridge) -> None:
    world = bridge.create_world(theme="cyberpunk", size="small")
    npc = bridge.generate_avatar_npc("Hermes", role="guide", world_id=world["world_id"])
    assert npc["ok"] is True
    assert npc["avatar_id"].startswith("npc_")
    entity = npc["entity_html"]
    assert "<a-entity" in entity
    assert "Hermes" in entity
    assert "guide" in entity

    state = bridge.get_world_state(world["world_id"])
    assert any(a["name"] == "Hermes" for a in state["avatars"])


def test_generate_avatar_npc_without_world(bridge: MetaverseBridge) -> None:
    npc = bridge.generate_avatar_npc("Standalone")
    assert npc["world_id"] is None
    assert "Standalone" in npc["entity_html"]


def test_generate_avatar_npc_rejects_bad_role(bridge: MetaverseBridge) -> None:
    with pytest.raises(ValueError):
        bridge.generate_avatar_npc("Cylon", role="overlord")


def test_invoke_dispatches_actions(bridge: MetaverseBridge) -> None:
    world = bridge.invoke("create_world", theme="neon-city", size="small")
    state = bridge.invoke("get_world_state", world_id=world["world_id"])
    assert state["theme"] == "neon-city"


def test_invoke_rejects_unknown_action(bridge: MetaverseBridge) -> None:
    with pytest.raises(ValueError):
        bridge.invoke("teleport_to_mars")


def test_validation_catalogues_are_consistent() -> None:
    assert "cyberpunk" in VALID_THEMES
    assert "medium" in VALID_SIZES
    assert "guide" in VALID_ROLES
    assert "cube" in VALID_ASSETS
