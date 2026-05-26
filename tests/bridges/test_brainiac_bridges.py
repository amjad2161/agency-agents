"""Tests for all 10 JARVIS Brainiac bridges."""
from __future__ import annotations
import tempfile
import base64
from pathlib import Path
import pytest

from jarvis_brainiac.bridges.blender import BlenderBridge
from jarvis_brainiac.bridges.cadam import CadamBridge
from jarvis_brainiac.bridges.dobot import DobotBridge
from jarvis_brainiac.bridges.lyra2 import Lyra2Bridge
from jarvis_brainiac.bridges.matrix_wallpaper import MatrixWallpaperBridge
from jarvis_brainiac.bridges.metaverse import MetaverseBridge
from jarvis_brainiac.bridges.personas import PersonasBridge
from jarvis_brainiac.bridges.rtk_ai import RtkAiBridge
from jarvis_brainiac.bridges.scifi_ui import ScifiUiBridge
from jarvis_brainiac.bridges.working_demos import WorkingDemosBridge


def test_blender_bridge() -> None:
    bridge = BlenderBridge()
    assert bridge.name == "blender"
    assert "create-mesh" in bridge.capabilities

    # Test actions
    out_create = bridge.invoke("create-mesh", type="CUBE", location=(1.0, 2.0, 3.0), scale=(2.0, 2.0, 2.0))
    assert out_create["ok"] is True
    assert out_create["type"] == "CUBE"

    out_render = bridge.invoke("render-scene", blend_file="scene.blend", output_path="out.png")
    assert "ok" in out_render

    out_export = bridge.invoke("export-gltf", blend_file="scene.blend", output_path="out.gltf")
    assert "ok" in out_export

    # Test unknown action
    out_bad = bridge.invoke("nonexistent-action")
    assert out_bad["ok"] is False


def test_cadam_bridge() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        dxf_path = Path(tmp_dir) / "test.dxf"
        # Write a dummy minimal DXF content
        dxf_path.write_text("0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF\n", encoding="utf-8")

        bridge = CadamBridge()
        assert bridge.name == "cadam"

        out_open = bridge.invoke("open-part", filepath=str(dxf_path))
        assert out_open["ok"] is True or "entities" in out_open

        out_path = bridge.invoke("tool-path", filepath=str(dxf_path))
        assert isinstance(out_path, (dict, list))

        svg_out = Path(tmp_dir) / "out.svg"
        out_sim = bridge.invoke("simulate", input_dxf=str(dxf_path), output_svg=str(svg_out))
        assert "ok" in out_sim


def test_dobot_bridge() -> None:
    bridge = DobotBridge(port="COM9")
    assert bridge.name == "dobot"

    out_home = bridge.invoke("home")
    assert out_home["ok"] is True

    out_move = bridge.invoke("move-xyz", x=100.0, y=50.0, z=50.0, r=10.0, mode="MOVL")
    assert out_move["ok"] is True
    assert "pose" in out_move

    out_grip = bridge.invoke("gripper", open=True)
    assert out_grip["ok"] is True


def test_lyra2_bridge() -> None:
    bridge = Lyra2Bridge()
    assert bridge.name == "lyra2"

    # Test TTS
    out_tts = bridge.invoke("tts", text="שלום עולם", voice="jarvis", language="he")
    assert out_tts["ok"] is True
    assert "audio_content" in out_tts

    # Test ASR
    dummy_wav = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80\x3e\x00\x00\x00\x7d\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    b64_wav = base64.b64encode(dummy_wav).decode("utf-8")
    out_asr = bridge.invoke("asr", audio_bytes=b64_wav, language="he")
    assert out_asr["ok"] is True
    assert "text" in out_asr

    # Test voice clone
    out_clone = bridge.invoke("voice-clone", voice_name="amjad_voice")
    assert out_clone["ok"] is True


def test_matrix_wallpaper_bridge() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        bridge = MatrixWallpaperBridge(assets_dir=tmp_dir)
        assert bridge.name == "matrix_wallpaper"

        out_density = bridge.invoke("set-density", density=0.7)
        assert out_density["ok"] is True

        out_start = bridge.invoke("start", duration=1.5)
        # May be ok or false depending on platformEdge browser kiosk availability, but should not crash
        assert "ok" in out_start

        out_stop = bridge.invoke("stop")
        assert "ok" in out_stop


def test_metaverse_bridge() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        bridge = MetaverseBridge(assets_dir=tmp_dir)
        assert bridge.name == "metaverse"

        out_enter = bridge.invoke("enter-world", theme="cyberpunk", size="small")
        assert out_enter["ok"] is True
        world_id = out_enter["world_id"]

        out_spawn = bridge.invoke("spawn-object", world_id=world_id, asset_type="cube", position=(0.0, 1.0, 0.0), properties={"color": "#ff00ff"})
        assert out_spawn["ok"] is True

        out_record = bridge.invoke("record", world_id=world_id)
        assert out_record["ok"] is True


def test_personas_bridge() -> None:
    bridge = PersonasBridge()
    assert bridge.name == "personas"

    out_route = bridge.invoke("persona-route", query="ניתוח חוזה שכירות של משרד")
    assert out_route["ok"] is True
    assert "persona_type" in out_route

    out_consult = bridge.invoke("consult-domain", query="מהם הדגשים המשפטיים בהקמת סטארטאפ?", context={"industry": "AI"})
    assert out_consult["ok"] is True
    assert "analysis" in out_consult

    out_mem = bridge.invoke("memory", persona_type="legal")
    assert out_mem["ok"] is True


def test_rtk_ai_bridge() -> None:
    bridge = RtkAiBridge()
    assert bridge.name == "rtk_ai"

    out_pos = bridge.invoke("get-position", lat=32.0853, lon=34.7818, alt=12.5)
    assert out_pos["ok"] is True
    assert "lat" in out_pos

    out_sub = bridge.invoke("subscribe-stream", stream_url="ntrip://test")
    assert out_sub["ok"] is True

    out_cal = bridge.invoke("calibrate", lat=32.0853, lon=34.7818, alt=12.5)
    assert out_cal["ok"] is True
    assert "corrected_lat" in out_cal


def test_scifi_ui_bridge() -> None:
    bridge = ScifiUiBridge()
    assert bridge.name == "scifi_ui"

    out_hud = bridge.invoke("render-hud")
    assert out_hud["ok"] is True
    assert "url" in out_hud

    out_text = bridge.invoke("holo-text", text="SYSTEM INITIALIZED", color="#00ff00")
    assert out_text["ok"] is True

    out_particle = bridge.invoke("particle-field", density=150)
    assert out_particle["ok"] is True


def test_working_demos_bridge() -> None:
    bridge = WorkingDemosBridge()
    assert bridge.name == "working_demos"

    out_list = bridge.invoke("list-demos")
    assert out_list["ok"] is True
    assert "demos" in out_list

    out_record = bridge.invoke("record-output")
    assert out_record["ok"] is True
