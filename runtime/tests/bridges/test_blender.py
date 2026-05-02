"""Tests for the Blender bridge — uses mock mode (no Blender install required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agency.bridges.blender import BlenderBridge, get_blender_bridge


@pytest.fixture()
def bridge() -> BlenderBridge:
    # Force mock mode by pointing at a path that does not exist.
    return BlenderBridge(blender_executable="/does/not/exist/blender")


def test_factory_returns_bridge_instance() -> None:
    b = get_blender_bridge(blender_executable="/nope/blender")
    assert isinstance(b, BlenderBridge)


def test_blender_unavailable_when_path_invalid(bridge: BlenderBridge) -> None:
    assert bridge.blender_available is False
    assert bridge.hardware_available is False
    status = bridge.status()
    assert status["blender_available"] is False
    assert status["explicit_executable"] == "/does/not/exist/blender"


def test_render_scene_returns_mock_payload(bridge: BlenderBridge, tmp_path: Path) -> None:
    out = tmp_path / "render.png"
    result = bridge.render_scene(
        blend_file=str(tmp_path / "scene.blend"),
        output_path=str(out),
        frame=42,
        resolution=(640, 480),
    )
    assert result["mock"] is True
    assert result["ok"] is False
    assert result["target"] == str(out)
    assert "bpy.ops.render.render" in result["script_preview"]
    assert "Install Blender" in result["instructions"]


def test_run_script_returns_mock_payload(bridge: BlenderBridge, tmp_path: Path) -> None:
    result = bridge.run_script(
        blend_file=str(tmp_path / "scene.blend"),
        python_script="import bpy\nprint('hi')",
    )
    assert result["mock"] is True
    assert "import bpy" in result["script_preview"]


def test_create_primitive_validates_type(bridge: BlenderBridge) -> None:
    with pytest.raises(ValueError):
        bridge.create_primitive(type="PYRAMID")


def test_create_primitive_returns_mock_with_metadata(bridge: BlenderBridge, tmp_path: Path) -> None:
    out = tmp_path / "cube.blend"
    result = bridge.create_primitive(
        type="cube",
        location=(1.0, 2.0, 3.0),
        scale=(2.0, 2.0, 2.0),
        output_blend=str(out),
    )
    assert result["mock"] is True
    assert result["type"] == "CUBE"
    assert result["location"] == [1.0, 2.0, 3.0]
    assert result["scale"] == [2.0, 2.0, 2.0]
    assert "primitive_cube_add" in result["script_preview"]


def test_export_gltf_returns_mock_payload(bridge: BlenderBridge, tmp_path: Path) -> None:
    out = tmp_path / "model.glb"
    result = bridge.export_gltf(
        blend_file=str(tmp_path / "scene.blend"),
        output_path=str(out),
    )
    assert result["mock"] is True
    assert result["target"] == str(out)
    assert "export_scene.gltf" in result["script_preview"]


def test_get_scene_info_returns_mock_defaults(bridge: BlenderBridge, tmp_path: Path) -> None:
    result = bridge.get_scene_info(blend_file=str(tmp_path / "scene.blend"))
    assert result["mock"] is True
    assert result["objects"] == []
    assert result["materials"] == []
    assert result["frame_start"] == 1
    assert result["frame_end"] == 250


def test_invoke_dispatches_known_actions(bridge: BlenderBridge, tmp_path: Path) -> None:
    out = tmp_path / "render.png"
    payload = bridge.invoke(
        "render_scene",
        blend_file=str(tmp_path / "scene.blend"),
        output_path=str(out),
    )
    assert payload["mock"] is True

    with pytest.raises(ValueError):
        bridge.invoke("nuke_universe")


def test_status_action_works_via_invoke(bridge: BlenderBridge) -> None:
    status = bridge.invoke("status")
    assert status["blender_available"] is False
    assert status["explicit_executable"].endswith("blender")
