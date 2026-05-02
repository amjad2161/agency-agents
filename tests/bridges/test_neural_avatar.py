"""Tests for bridges.neural_avatar."""
from __future__ import annotations

import pytest

from bridges.neural_avatar import NeuralAvatar


@pytest.fixture
def avatar() -> NeuralAvatar:
    return NeuralAvatar()


def test_html_contains_name_and_role(avatar: NeuralAvatar) -> None:
    html = avatar.generate_html("J.A.R.V.I.S.", "Assistant")
    assert "J.A.R.V.I.S." in html
    assert "Assistant" in html
    assert "<!doctype html>" in html.lower()


def test_html_includes_threejs_module(avatar: NeuralAvatar) -> None:
    html = avatar.generate_html("Vision", "AI", style="iron_man")
    assert "three" in html
    assert "OrbitControls" in html
    assert "WebGLRenderer" in html


def test_html_escapes_user_input(avatar: NeuralAvatar) -> None:
    html = avatar.generate_html("<script>alert(1)</script>", "x", "neon")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_get_avatar_config_known_styles(avatar: NeuralAvatar) -> None:
    for style in ("holographic", "iron_man", "ghost", "neon"):
        cfg = avatar.get_avatar_config(style)
        assert "color" in cfg
        assert "emissive" in cfg
        assert "roughness" in cfg
        assert isinstance(cfg["roughness"], float)


def test_get_avatar_config_unknown_raises(avatar: NeuralAvatar) -> None:
    with pytest.raises(ValueError):
        avatar.get_avatar_config("nope")


def test_lip_sync_basic_word(avatar: NeuralAvatar) -> None:
    seq = avatar.generate_lip_sync_sequence("hi")
    assert len(seq) == 2
    assert seq[0]["phoneme"] == "HH"
    assert seq[1]["phoneme"] == "IY"
    assert seq[0]["start"] == 0.0
    assert seq[0]["end"] > seq[0]["start"]
    assert seq[1]["start"] == seq[0]["end"]


def test_lip_sync_handles_silence(avatar: NeuralAvatar) -> None:
    seq = avatar.generate_lip_sync_sequence("a b")
    phonemes = [s["phoneme"] for s in seq]
    assert "SIL" in phonemes
    sil = next(s for s in seq if s["phoneme"] == "SIL")
    assert sil["intensity"] == 0.0


def test_lip_sync_digraph_recognized(avatar: NeuralAvatar) -> None:
    seq = avatar.generate_lip_sync_sequence("ship")
    phonemes = [s["phoneme"] for s in seq]
    assert phonemes[0] == "SH"
    assert "IY" in phonemes
    assert "P" in phonemes


def test_lip_sync_empty_string(avatar: NeuralAvatar) -> None:
    assert avatar.generate_lip_sync_sequence("") == []


def test_lip_sync_timing_monotonic(avatar: NeuralAvatar) -> None:
    seq = avatar.generate_lip_sync_sequence("hello world")
    last_end = -1.0
    for s in seq:
        assert s["start"] >= last_end - 1e-6
        assert s["end"] > s["start"]
        last_end = s["end"]


def test_invoke_dispatches_generate_html(avatar: NeuralAvatar) -> None:
    out = avatar.invoke(
        "generate_html", name="Test", role="Bot", style="ghost")
    assert "Test" in out
    assert "Bot" in out


def test_invoke_dispatches_lip_sync(avatar: NeuralAvatar) -> None:
    out = avatar.invoke(
        "generate_lip_sync_sequence", text="cat")
    assert isinstance(out, list)
    assert any(s["phoneme"] == "K" for s in out)


def test_invoke_unknown_action_raises(avatar: NeuralAvatar) -> None:
    with pytest.raises(ValueError):
        avatar.invoke("not_a_real_action")


def test_invalid_default_style_raises() -> None:
    with pytest.raises(ValueError):
        NeuralAvatar(default_style="bogus")


def test_html_invalid_style_raises(avatar: NeuralAvatar) -> None:
    with pytest.raises(ValueError):
        avatar.generate_html("X", "Y", style="bogus")
