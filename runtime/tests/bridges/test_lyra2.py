"""Tests for the Lyra 2.0 audio bridge — all run with mock backend."""

from __future__ import annotations

import struct
import wave
from io import BytesIO

import pytest

from agency.bridges.lyra2 import (
    LYRA2_MAGIC,
    Lyra2Bridge,
    SUPPORTED_BITRATES,
    SUPPORTED_LANGUAGES,
    get_lyra2_bridge,
)


def _make_pcm(seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    n = int(seconds * sample_rate)
    return struct.pack(f"<{n}h", *([0] * n))


@pytest.fixture()
def bridge() -> Lyra2Bridge:
    return get_lyra2_bridge()


def test_factory_returns_bridge_with_known_backends(bridge: Lyra2Bridge) -> None:
    info = bridge.get_codec_info()
    assert info["stt_backend"] in {"riva", "whisper", "mock"}
    assert info["tts_backend"] in {"riva", "mock"}
    assert info["codec_backend"] in {"riva", "mock"}
    assert sorted(info["available_bitrates"]) == sorted(SUPPORTED_BITRATES)
    assert "he" in info["supported_languages"]
    assert "jarvis" in info["voices"]


def test_encode_returns_lyra2_frame(bridge: Lyra2Bridge) -> None:
    pcm = _make_pcm(0.5)
    encoded = bridge.encode(pcm, sample_rate=16000, bitrate=3200)
    assert encoded.startswith(LYRA2_MAGIC)
    assert len(encoded) > len(LYRA2_MAGIC) + 12


def test_encode_decode_round_trip(bridge: Lyra2Bridge) -> None:
    pcm = _make_pcm(0.25)
    encoded = bridge.encode(pcm, sample_rate=16000, bitrate=6000)
    decoded = bridge.decode(encoded, sample_rate=16000)
    assert decoded == pcm


def test_encode_rejects_bad_bitrate(bridge: Lyra2Bridge) -> None:
    with pytest.raises(ValueError):
        bridge.encode(_make_pcm(0.1), bitrate=1234)


def test_encode_rejects_bad_sample_rate(bridge: Lyra2Bridge) -> None:
    with pytest.raises(ValueError):
        bridge.encode(_make_pcm(0.1), sample_rate=12345)


def test_encode_rejects_empty_audio(bridge: Lyra2Bridge) -> None:
    with pytest.raises(ValueError):
        bridge.encode(b"")


def test_decode_rejects_garbage(bridge: Lyra2Bridge) -> None:
    with pytest.raises(ValueError):
        bridge.decode(b"NOTAFRAME_PAYLOAD")


def test_transcribe_returns_text_metadata(bridge: Lyra2Bridge) -> None:
    pcm = _make_pcm(2.0)
    result = bridge.transcribe(pcm, language="he")
    assert isinstance(result, dict)
    assert "text" in result and isinstance(result["text"], str) and result["text"]
    assert result["language"] == "he"
    assert result["backend"] in {"riva", "whisper", "mock"}
    assert result["duration_seconds"] > 0


def test_transcribe_rejects_unknown_language(bridge: Lyra2Bridge) -> None:
    with pytest.raises(ValueError):
        bridge.transcribe(_make_pcm(0.1), language="klingon")


def test_synthesize_returns_valid_wav(bridge: Lyra2Bridge) -> None:
    wav_bytes = bridge.synthesize("שלום JARVIS", voice="jarvis", language="he")
    assert wav_bytes.startswith(b"RIFF")
    assert b"WAVE" in wav_bytes[:12]
    with wave.open(BytesIO(wav_bytes), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getnframes() > 0


def test_synthesize_rejects_unknown_voice(bridge: Lyra2Bridge) -> None:
    with pytest.raises(ValueError):
        bridge.synthesize("hi", voice="dragonborn")


def test_synthesize_rejects_unknown_language(bridge: Lyra2Bridge) -> None:
    with pytest.raises(ValueError):
        bridge.synthesize("hi", language="klingon")


def test_invoke_dispatches_known_actions(bridge: Lyra2Bridge) -> None:
    info = bridge.invoke("get_codec_info")
    assert "voices" in info

    pcm = _make_pcm(0.1)
    encoded = bridge.invoke("encode", audio_bytes=pcm, sample_rate=16000, bitrate=3200)
    assert encoded.startswith(LYRA2_MAGIC)
    decoded = bridge.invoke("decode", compressed=encoded, sample_rate=16000)
    assert decoded == pcm


def test_invoke_rejects_unknown_action(bridge: Lyra2Bridge) -> None:
    with pytest.raises(ValueError):
        bridge.invoke("kaboom")


def test_supported_languages_is_iterable_of_strings() -> None:
    for code in SUPPORTED_LANGUAGES:
        assert isinstance(code, str)
        assert 2 <= len(code) <= 5
