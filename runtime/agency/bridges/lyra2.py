"""NVIDIA Lyra 2.0 / Riva audio codec bridge.

Three backends are tried in order, falling back gracefully:

1. ``nvidia-riva-client`` — real Lyra2/Riva STT + TTS when the SDK is
   installed and a Riva server is reachable.
2. ``openai-whisper`` — high-quality offline STT fallback.
3. Pure-Python *mock* codec that produces deterministic, structurally
   valid output (zlib-compressed payloads, valid RIFF/WAV headers,
   stub transcripts). This makes the bridge usable in CI on machines
   without GPUs or audio hardware.

Only stdlib + optional backends are imported. The bridge has zero
side effects at import time.
"""

from __future__ import annotations

import math
import struct
import wave
import zlib
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable, Dict, List, Optional

from ..logging import get_logger

log = get_logger()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LYRA2_MAGIC = b"LY2\x00"
SUPPORTED_BITRATES = (3200, 6000, 9200)
SUPPORTED_SAMPLE_RATES = (8000, 16000, 32000, 48000)
SUPPORTED_LANGUAGES = ("en", "he", "es", "fr", "de", "ja", "zh", "ar", "ru", "pt")

_VOICE_PROFILES = {
    "jarvis":   {"base_freq": 110.0, "formants": (700.0, 1220.0)},
    "narrator": {"base_freq":  90.0, "formants": (560.0, 1080.0)},
    "assistant":{"base_freq": 220.0, "formants": (840.0, 1640.0)},
    "child":    {"base_freq": 280.0, "formants": (920.0, 1840.0)},
}
DEFAULT_VOICE = "jarvis"


# ---------------------------------------------------------------------------
# Optional backend detection
# ---------------------------------------------------------------------------

def _has_riva() -> bool:
    try:
        import riva.client  # noqa: F401
        return True
    except Exception:
        return False


def _has_whisper() -> bool:
    try:
        import whisper  # noqa: F401
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Frame:
    """One Lyra2 mock frame: bitrate header + zlib-compressed PCM."""

    bitrate: int
    sample_rate: int
    payload: bytes


class Lyra2Bridge:
    """NVIDIA Lyra 2.0 / Riva bridge with whisper + mock fallbacks."""

    def __init__(self, riva_server: Optional[str] = None) -> None:
        self._riva_server = riva_server or "localhost:50051"
        self._stt_backend = self._detect_stt_backend()
        self._tts_backend = self._detect_tts_backend()
        self._codec_backend = "riva" if _has_riva() else "mock"

    # ------------------------------------------------------------------
    # Backend detection
    # ------------------------------------------------------------------

    def _detect_stt_backend(self) -> str:
        if _has_riva():
            return "riva"
        if _has_whisper():
            return "whisper"
        return "mock"

    def _detect_tts_backend(self) -> str:
        if _has_riva():
            return "riva"
        return "mock"

    @property
    def stt_backend(self) -> str:
        return self._stt_backend

    @property
    def tts_backend(self) -> str:
        return self._tts_backend

    @property
    def codec_backend(self) -> str:
        return self._codec_backend

    # ------------------------------------------------------------------
    # Codec info
    # ------------------------------------------------------------------

    def get_codec_info(self) -> Dict[str, Any]:
        return {
            "available_bitrates": list(SUPPORTED_BITRATES),
            "supported_languages": list(SUPPORTED_LANGUAGES),
            "supported_sample_rates": list(SUPPORTED_SAMPLE_RATES),
            "stt_backend": self._stt_backend,
            "tts_backend": self._tts_backend,
            "codec_backend": self._codec_backend,
            "riva_server": self._riva_server,
            "voices": sorted(_VOICE_PROFILES.keys()),
        }

    # ------------------------------------------------------------------
    # Encode / decode
    # ------------------------------------------------------------------

    def encode(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        bitrate: int = 3200,
    ) -> bytes:
        """Compress raw PCM s16le audio to a Lyra2-style frame stream.

        With the mock backend the output is a self-describing
        zlib-compressed container; with the riva backend we delegate to
        the SDK if reachable, else mock again.
        """
        self._validate_audio_input(audio_bytes)
        self._validate_sample_rate(sample_rate)
        self._validate_bitrate(bitrate)

        if self._codec_backend == "riva":
            try:
                return _riva_encode(audio_bytes, sample_rate, bitrate)
            except Exception as exc:
                log.warning("Lyra2Bridge: riva encode failed (%s) — mock fallback", exc)

        return _mock_encode(_Frame(bitrate=bitrate, sample_rate=sample_rate, payload=audio_bytes))

    def decode(self, compressed: bytes, sample_rate: int = 16000) -> bytes:
        """Decompress a Lyra2 frame stream back into PCM s16le audio."""
        if not isinstance(compressed, (bytes, bytearray)):
            raise TypeError("compressed must be bytes")
        self._validate_sample_rate(sample_rate)
        if len(compressed) < len(LYRA2_MAGIC):
            raise ValueError("compressed buffer too short")

        if self._codec_backend == "riva" and not compressed.startswith(LYRA2_MAGIC):
            try:
                return _riva_decode(compressed, sample_rate)
            except Exception as exc:
                log.warning("Lyra2Bridge: riva decode failed (%s) — mock fallback", exc)

        return _mock_decode(bytes(compressed))

    # ------------------------------------------------------------------
    # Speech-to-text
    # ------------------------------------------------------------------

    def transcribe(self, audio_bytes: bytes, language: str = "he") -> Dict[str, Any]:
        """Convert PCM audio (or a WAV file) to text.

        Returns ``{"text": str, "language": str, "backend": str,
        "duration_seconds": float}``.
        """
        self._validate_audio_input(audio_bytes)
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"language {language!r} not supported — must be one of {SUPPORTED_LANGUAGES}"
            )

        duration = _estimate_audio_duration(audio_bytes)

        if self._stt_backend == "riva":
            try:
                text = _riva_transcribe(audio_bytes, language, self._riva_server)
                return {
                    "text": text,
                    "language": language,
                    "backend": "riva",
                    "duration_seconds": duration,
                }
            except Exception as exc:
                log.warning("Lyra2Bridge: riva STT failed (%s)", exc)

        if self._stt_backend == "whisper":
            try:
                text = _whisper_transcribe(audio_bytes, language)
                return {
                    "text": text,
                    "language": language,
                    "backend": "whisper",
                    "duration_seconds": duration,
                }
            except Exception as exc:
                log.warning("Lyra2Bridge: whisper STT failed (%s)", exc)

        text = _mock_transcribe(audio_bytes, language, duration)
        return {
            "text": text,
            "language": language,
            "backend": "mock",
            "duration_seconds": duration,
        }

    # ------------------------------------------------------------------
    # Text-to-speech
    # ------------------------------------------------------------------

    def synthesize(
        self,
        text: str,
        voice: str = DEFAULT_VOICE,
        language: str = "he",
        sample_rate: int = 22050,
    ) -> bytes:
        """Render ``text`` to a WAV byte string.

        Returns a complete RIFF/WAV blob (header + PCM s16le data).
        """
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if voice not in _VOICE_PROFILES:
            raise ValueError(
                f"voice {voice!r} not in available voices {sorted(_VOICE_PROFILES)}"
            )
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"language {language!r} not supported — must be one of {SUPPORTED_LANGUAGES}"
            )
        if sample_rate not in SUPPORTED_SAMPLE_RATES + (22050, 44100):
            raise ValueError(f"unsupported sample rate {sample_rate!r}")

        if self._tts_backend == "riva":
            try:
                return _riva_synthesize(text, voice, language, sample_rate, self._riva_server)
            except Exception as exc:
                log.warning("Lyra2Bridge: riva TTS failed (%s)", exc)

        return _mock_synthesize(text, voice, sample_rate)

    # ------------------------------------------------------------------
    # Generic dispatch
    # ------------------------------------------------------------------

    def invoke(self, action: str, **kwargs: Any) -> Any:
        registry: Dict[str, Callable[..., Any]] = {
            "encode": self.encode,
            "decode": self.decode,
            "transcribe": self.transcribe,
            "synthesize": self.synthesize,
            "get_codec_info": self.get_codec_info,
        }
        if action not in registry:
            raise ValueError(f"unknown lyra2 action: {action!r}")
        return registry[action](**kwargs)

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_audio_input(self, audio_bytes: bytes) -> None:
        if not isinstance(audio_bytes, (bytes, bytearray)):
            raise TypeError("audio_bytes must be bytes")
        if len(audio_bytes) == 0:
            raise ValueError("audio_bytes is empty")

    def _validate_sample_rate(self, sample_rate: int) -> None:
        if sample_rate not in SUPPORTED_SAMPLE_RATES:
            raise ValueError(
                f"sample_rate {sample_rate!r} not supported — must be one of {SUPPORTED_SAMPLE_RATES}"
            )

    def _validate_bitrate(self, bitrate: int) -> None:
        if bitrate not in SUPPORTED_BITRATES:
            raise ValueError(
                f"bitrate {bitrate!r} not supported — must be one of {SUPPORTED_BITRATES}"
            )


# ---------------------------------------------------------------------------
# Mock codec
# ---------------------------------------------------------------------------

def _mock_encode(frame: _Frame) -> bytes:
    """Encode to: LY2\\x00 | u32 bitrate | u32 sample_rate | u32 zlen | zdata."""
    body = zlib.compress(frame.payload, level=6)
    header = LYRA2_MAGIC + struct.pack("<III", frame.bitrate, frame.sample_rate, len(body))
    return header + body


def _mock_decode(buf: bytes) -> bytes:
    if not buf.startswith(LYRA2_MAGIC):
        raise ValueError("not a Lyra2 mock frame")
    if len(buf) < len(LYRA2_MAGIC) + 12:
        raise ValueError("Lyra2 mock frame truncated")
    bitrate, sample_rate, zlen = struct.unpack(
        "<III", buf[len(LYRA2_MAGIC):len(LYRA2_MAGIC) + 12]
    )
    if bitrate not in SUPPORTED_BITRATES:
        raise ValueError(f"unsupported bitrate in frame: {bitrate}")
    if sample_rate not in SUPPORTED_SAMPLE_RATES:
        raise ValueError(f"unsupported sample rate in frame: {sample_rate}")
    body = buf[len(LYRA2_MAGIC) + 12:len(LYRA2_MAGIC) + 12 + zlen]
    if len(body) != zlen:
        raise ValueError("Lyra2 mock frame body truncated")
    return zlib.decompress(body)


def _mock_transcribe(audio_bytes: bytes, language: str, duration: float) -> str:
    """Deterministic stub: returns a hash-derived caption + duration tag."""
    digest = zlib.adler32(bytes(audio_bytes)) & 0xFFFFFFFF
    return f"[mock:{language}] audio adler32={digest:08x} duration={duration:.2f}s"


def _mock_synthesize(text: str, voice: str, sample_rate: int) -> bytes:
    """Render text as a sine-tone WAV with formant overtones.

    Duration scales with text length so the output is differentiable;
    silent gaps are inserted at spaces so the rhythm follows the words.
    """
    profile = _VOICE_PROFILES[voice]
    base = float(profile["base_freq"])
    formant_a, formant_b = profile["formants"]

    seconds_per_char = 0.07
    duration = max(0.3, len(text) * seconds_per_char)
    n_samples = int(sample_rate * duration)
    samples: List[int] = []
    for i in range(n_samples):
        t = i / sample_rate
        char_idx = int(t / seconds_per_char)
        if char_idx < len(text) and text[char_idx] == " ":
            samples.append(0)
            continue
        char_offset = (ord(text[char_idx]) if char_idx < len(text) else 0) % 17
        freq = base + char_offset * 4.0
        s = (
            0.5 * math.sin(2 * math.pi * freq * t)
            + 0.25 * math.sin(2 * math.pi * formant_a * t)
            + 0.15 * math.sin(2 * math.pi * formant_b * t)
        )
        envelope = 0.5 * (1 - math.cos(2 * math.pi * (i / max(1, n_samples - 1))))
        sample_value = int(max(-1.0, min(1.0, s * envelope)) * 0x7FFF)
        samples.append(sample_value)

    buf = BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Real backend wrappers (best-effort; mock fallback if any step fails)
# ---------------------------------------------------------------------------

def _riva_encode(audio_bytes: bytes, sample_rate: int, bitrate: int) -> bytes:
    """Try a Riva-side compression. Conservative: many releases of
    nvidia-riva-client do not expose a public Lyra encoder, so callers
    that want a deterministic byte stream should fall back to the mock
    encoder. We raise to signal mock fallback when no real encoder is
    present."""
    raise RuntimeError("riva audio codec encoder not available in this build")


def _riva_decode(compressed: bytes, sample_rate: int) -> bytes:
    raise RuntimeError("riva audio codec decoder not available in this build")


def _riva_transcribe(audio_bytes: bytes, language: str, server: str) -> str:
    import riva.client  # type: ignore

    auth = riva.client.Auth(uri=server)
    asr = riva.client.ASRService(auth)
    config = riva.client.RecognitionConfig(
        language_code=language,
        max_alternatives=1,
        sample_rate_hertz=16000,
    )
    response = asr.offline_recognize(audio_bytes, config)
    alternatives = []
    for result in response.results:
        if result.alternatives:
            alternatives.append(result.alternatives[0].transcript)
    return " ".join(a.strip() for a in alternatives if a).strip()


def _whisper_transcribe(audio_bytes: bytes, language: str) -> str:
    import tempfile

    import whisper  # type: ignore

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        model = whisper.load_model("tiny")
        result = model.transcribe(tmp_path, language=language)
        return str(result.get("text", "")).strip()
    finally:
        try:
            import os as _os

            _os.unlink(tmp_path)
        except OSError:
            pass


def _riva_synthesize(
    text: str, voice: str, language: str, sample_rate: int, server: str,
) -> bytes:
    import riva.client  # type: ignore

    auth = riva.client.Auth(uri=server)
    tts = riva.client.SpeechSynthesisService(auth)
    response = tts.synthesize(
        text,
        voice_name=voice,
        language_code=language,
        sample_rate_hz=sample_rate,
        encoding=riva.client.AudioEncoding.LINEAR_PCM,
    )
    pcm = response.audio
    buf = BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def _estimate_audio_duration(audio_bytes: bytes) -> float:
    """Return the audio duration in seconds.

    Treats the buffer as either a WAV (uses the header) or raw 16-bit
    PCM at 16 kHz.
    """
    if audio_bytes.startswith(b"RIFF") and b"WAVE" in audio_bytes[:12]:
        try:
            with wave.open(BytesIO(audio_bytes), "rb") as wav:
                frames = wav.getnframes()
                rate = wav.getframerate() or 1
                return frames / float(rate)
        except (wave.Error, EOFError):
            pass
    return max(0.0, len(audio_bytes) / (2.0 * 16000))


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_lyra2_bridge(riva_server: Optional[str] = None) -> Lyra2Bridge:
    """Return a fresh :class:`Lyra2Bridge`."""
    return Lyra2Bridge(riva_server=riva_server)


__all__ = [
    "Lyra2Bridge",
    "get_lyra2_bridge",
    "LYRA2_MAGIC",
    "SUPPORTED_BITRATES",
    "SUPPORTED_LANGUAGES",
    "SUPPORTED_SAMPLE_RATES",
]
