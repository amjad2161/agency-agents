"""Local voice subsystem (Tier 5).

Provides STT (Faster-Whisper) and TTS (XTTSv2) shaped APIs that gracefully
degrade to no-op text adapters when the heavy optional dependencies are
not installed. The point is to keep the JARVIS voice surface available in
hermetic test environments and offline boxes.
"""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Hebrew detection for auto-language switching.
_HEBREW = re.compile(r"[\u0590-\u05FF]")


def detect_language(text: str) -> str:
    return "he" if _HEBREW.search(text or "") else "en"


@dataclass
class VoiceConfig:
    stt_model: str = "base"
    tts_voice: str = "default"
    sample_rate: int = 16000
    cache_dir: Path = field(default_factory=lambda: Path.home() / ".agency" / "voice")

    @classmethod
    def from_env(cls) -> "VoiceConfig":
        return cls(
            stt_model=os.environ.get("JARVIS_STT_MODEL", "base"),
            tts_voice=os.environ.get("JARVIS_TTS_VOICE", "default"),
            sample_rate=int(os.environ.get("JARVIS_VOICE_SR", "16000")),
            cache_dir=Path(os.environ.get(
                "JARVIS_VOICE_CACHE",
                str(Path.home() / ".agency" / "voice"),
            )).expanduser(),
        )


class LocalVoice:
    """Faster-Whisper / XTTSv2 facade with deterministic fallbacks."""

    def __init__(self, config: VoiceConfig | None = None) -> None:
        self.config = config or VoiceConfig.from_env()
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)
        self._stt = self._load_stt()
        self._tts = self._load_tts()

    # ------------------------------------------------------------------ STT
    def transcribe(self, audio: bytes | str | Path, *, language: str | None = None) -> dict[str, Any]:
        """Transcribe audio. Bytes / file path / mock string are all accepted."""
        if self._stt is None or isinstance(audio, str) and not Path(audio).exists():
            text = audio if isinstance(audio, str) else f"[mock-stt:{len(audio)}-bytes]"
            return {
                "text": str(text),
                "language": language or detect_language(str(text)),
                "engine": "mock",
            }
        # Real engine path — never executed in tests because optional dep is missing.
        result = self._stt.transcribe(audio, language=language)  # pragma: no cover
        return {
            "text": result.get("text", ""),
            "language": result.get("language", language or "en"),
            "engine": "faster-whisper",
        }

    # ------------------------------------------------------------------ TTS
    def synthesize(self, text: str, *, voice: str | None = None,
                   language: str | None = None) -> bytes:
        """Render *text* into PCM/WAV bytes (mock returns text-marker WAV)."""
        lang = language or detect_language(text)
        voice = voice or self.config.tts_voice
        if self._tts is None:
            buf = io.BytesIO()
            buf.write(b"RIFF")
            buf.write(len(text).to_bytes(4, "little"))
            buf.write(b"WAVEmock")
            buf.write(f"|lang={lang}|voice={voice}|".encode("utf-8"))
            buf.write(text.encode("utf-8"))
            return buf.getvalue()
        return self._tts.tts(text=text, language=lang, speaker=voice)  # pragma: no cover

    # ------------------------------------------------------------------ helpers
    def health(self) -> dict[str, Any]:
        return {
            "stt": "real" if self._stt else "mock",
            "tts": "real" if self._tts else "mock",
            "cache_dir": str(self.config.cache_dir),
        }

    def _load_stt(self) -> Any | None:
        try:  # pragma: no cover — optional
            from faster_whisper import WhisperModel  # type: ignore
            return WhisperModel(self.config.stt_model)
        except Exception:
            return None

    def _load_tts(self) -> Any | None:
        try:  # pragma: no cover — optional
            from TTS.api import TTS  # type: ignore
            return TTS(self.config.tts_voice)
        except Exception:
            return None
