"""Tests for bridges.neural_avatar."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from bridges.neural_avatar import (
    EMOTION_PRESETS,
    NeuralAvatarBridge,
)


@pytest.fixture
def bridge(tmp_path: Path) -> NeuralAvatarBridge:
    return NeuralAvatarBridge(asset_dir=tmp_path / "avatar")


def test_generate_avatar_writes_self_contained_html(bridge, tmp_path):
    out = bridge.generate_avatar(style="professional", gender="neutral")
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "<!doctype html>" in html
    assert "three.module.js" in html  # CDN three.js loaded
    assert "WebGLRenderer" in html
    assert "professional" in html
    # Emotion presets must be embedded for the runtime.
    for emotion in EMOTION_PRESETS:
        assert emotion in html


def test_generate_avatar_respects_custom_output_path(bridge, tmp_path):
    target = tmp_path / "nested" / "custom.html"
    out = bridge.generate_avatar(output_path=target)
    assert out == target
    assert target.exists()


@pytest.mark.parametrize("emotion", list(EMOTION_PRESETS.keys()))
def test_animate_returns_parameters_for_each_preset(bridge, emotion):
    result = bridge.animate(emotion)
    assert result["emotion"] == emotion
    assert "css_transform" in result
    assert "transition" in result
    assert "duration_ms" in result["js_params"]
    assert result["js_params"]["color"].startswith("#")


def test_animate_unknown_emotion_raises(bridge):
    with pytest.raises(ValueError, match="unknown emotion"):
        bridge.animate("ennui")


def test_speak_hebrew_produces_phoneme_timeline(bridge):
    result = bridge.speak("שלום", language="he")
    assert result["language"] == "he"
    assert result["text"] == "שלום"
    assert len(result["phonemes"]) >= 4
    # Timeline must be monotonic.
    starts = [p["start_ms"] for p in result["phonemes"]]
    assert starts == sorted(starts)
    # Visemes carry both 'open' and 'wide'.
    for p in result["phonemes"]:
        assert "open" in p["viseme"]
        assert "wide" in p["viseme"]
    assert result["total_ms"] > 0


def test_speak_english_includes_rest_for_whitespace(bridge):
    result = bridge.speak("hi there", language="en")
    rest_phonemes = [p for p in result["phonemes"] if p["phoneme"] == "REST"]
    assert rest_phonemes, "expected REST viseme for the space"


def test_speak_rejects_non_string(bridge):
    with pytest.raises(TypeError):
        bridge.speak(12345)  # type: ignore[arg-type]


def test_set_appearance_returns_new_state(bridge):
    new_state = bridge.set_appearance({"skin_color": "#abcdef"})
    assert new_state["skin_color"] == "#abcdef"
    # Other keys preserved.
    assert "shirt_color" in new_state


def test_set_appearance_rejects_unknown_key(bridge):
    with pytest.raises(ValueError, match="unknown appearance keys"):
        bridge.set_appearance({"third_eye": "#000"})


def test_set_appearance_rejects_non_dict(bridge):
    with pytest.raises(TypeError):
        bridge.set_appearance("blue")  # type: ignore[arg-type]


def test_export_glb_writes_valid_header(bridge, tmp_path):
    glb = tmp_path / "avatar.glb"
    out = bridge.export_glb(glb)
    assert out == glb
    raw = glb.read_bytes()
    assert raw[:4] == b"glTF"
    version = struct.unpack("<I", raw[4:8])[0]
    total_length = struct.unpack("<I", raw[8:12])[0]
    assert version == 2
    assert total_length == len(raw)
    # JSON chunk type marker
    json_chunk_type = raw[16:20]
    assert json_chunk_type == b"JSON"


def test_invoke_dispatches_known_action(bridge):
    result = bridge.invoke("animate", emotion="happy")
    assert result["emotion"] == "happy"


def test_invoke_unknown_action_raises(bridge):
    with pytest.raises(ValueError, match="unknown action"):
        bridge.invoke("teleport")
