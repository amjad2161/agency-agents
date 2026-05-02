"""Speech-to-Text engine for JARVIS robot voice control.

Backends (tried in order):
1. openai-whisper  (offline, pip install openai-whisper)
2. SpeechRecognition + Google Web API  (pip install SpeechRecognition pyaudio)
3. MOCK  (returns preset strings — zero deps, for CI/testing)

Usage
-----
    stt = STTEngine()           # auto-detect
    text = stt.listen(timeout=5.0)
    if text:
        print("Heard:", text)
"""

from __future__ import annotations

import threading
import time
from enum import Enum
from pathlib import Path
from typing import List, Optional

from ..logging import get_logger

log = get_logger()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class STTBackend(str, Enum):
    WHISPER = "whisper"
    GOOGLE  = "google"
    MOCK    = "mock"


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------

class _WhisperSTT:
    """Offline Whisper-based transcription."""

    def __init__(self, model_size: str = "tiny") -> None:
        try:
            import whisper as _whisper   # type: ignore
        except ImportError as e:
            raise ImportError(
                "Whisper not installed. Run: pip install openai-whisper"
            ) from e
        self._whisper = _whisper
        self._model_size = model_size
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            log.info("stt.whisper loading model=%s", self._model_size)
            self._model = self._whisper.load_model(self._model_size)

    def listen(self, timeout: float = 5.0) -> Optional[str]:
        """Record from the default mic for *timeout* seconds and transcribe."""
        try:
            import sounddevice as sd   # type: ignore
            import numpy as np         # type: ignore
        except ImportError:
            log.warning("stt.whisper: sounddevice/numpy not available for mic capture")
            return None

        self._ensure_model()
        sample_rate = 16_000
        frames = int(sample_rate * timeout)
        log.info("stt.whisper recording %.1f s", timeout)
        recording = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="float32")
        sd.wait()
        audio = recording.flatten()
        result = self._model.transcribe(audio, fp16=False)
        text = result.get("text", "").strip()
        log.info("stt.whisper transcribed=%r", text)
        return text or None

    def transcribe_file(self, audio_path: str) -> str:
        self._ensure_model()
        result = self._model.transcribe(audio_path, fp16=False)
        return result.get("text", "").strip()

    def is_available(self) -> bool:
        try:
            import whisper  # type: ignore  # noqa: F401
            return True
        except ImportError:
            return False


class _GoogleSTT:
    """Google Web Speech API via SpeechRecognition library."""

    def __init__(self) -> None:
        try:
            import speech_recognition as sr  # type: ignore
        except ImportError as e:
            raise ImportError(
                "SpeechRecognition not installed. "
                "Run: pip install SpeechRecognition pyaudio"
            ) from e
        self._sr = sr
        self._recognizer = sr.Recognizer()

    def listen(self, timeout: float = 5.0) -> Optional[str]:
        sr = self._sr
        try:
            with sr.Microphone() as source:
                log.info("stt.google listening timeout=%.1f", timeout)
                audio = self._recognizer.listen(source, timeout=timeout, phrase_time_limit=timeout)
            text = self._recognizer.recognize_google(audio)
            log.info("stt.google transcribed=%r", text)
            return text
        except sr.WaitTimeoutError:
            log.info("stt.google timeout — no speech")
            return None
        except sr.UnknownValueError:
            log.info("stt.google could not understand audio")
            return None
        except Exception as exc:
            log.warning("stt.google error: %s", exc)
            return None

    def transcribe_file(self, audio_path: str) -> str:
        sr = self._sr
        with sr.AudioFile(audio_path) as source:
            audio = self._recognizer.record(source)
        return self._recognizer.recognize_google(audio)

    def is_available(self) -> bool:
        try:
            import speech_recognition  # type: ignore  # noqa: F401
            return True
        except ImportError:
            return False


class _MockSTT:
    """Zero-dependency mock STT for CI / unit testing.

    Cycles through *preset_responses* on each listen() call.
    """

    DEFAULT_RESPONSES: List[str] = [
        "walk forward 2 meters",
        "turn left 90 degrees",
        "sit down",
        "wave hand",
        "stop",
    ]

    def __init__(self, responses: Optional[List[str]] = None) -> None:
        self._responses = responses or list(self.DEFAULT_RESPONSES)
        self._index = 0

    def listen(self, timeout: float = 5.0) -> Optional[str]:  # noqa: ARG002
        if not self._responses:
            return None
        text = self._responses[self._index % len(self._responses)]
        self._index += 1
        log.info("stt.mock returning=%r", text)
        return text

    def transcribe_file(self, audio_path: str) -> str:  # noqa: ARG002
        return self._responses[0] if self._responses else ""

    def is_available(self) -> bool:
        return True

    def set_responses(self, responses: List[str]) -> None:
        self._responses = responses
        self._index = 0


# ---------------------------------------------------------------------------
# Public façade: STTEngine
# ---------------------------------------------------------------------------

class STTEngine:
    """Unified STT interface.  Auto-detects best available backend.

    Parameters
    ----------
    backend:
        Explicit backend selection. If AUTO (None), tries Whisper → Google → MOCK.
    model_size:
        Whisper model size (tiny / base / small / medium / large).
    mock_responses:
        Preset responses for MOCK backend.
    """

    def __init__(
        self,
        backend: Optional[STTBackend] = None,
        model_size: str = "tiny",
        mock_responses: Optional[List[str]] = None,
    ) -> None:
        self._impl = self._create_backend(backend, model_size, mock_responses)
        log.info("STTEngine backend=%s", type(self._impl).__name__)

    def _create_backend(self, backend, model_size, mock_responses):
        if backend == STTBackend.MOCK or backend == "mock":
            return _MockSTT(mock_responses)

        if backend == STTBackend.WHISPER or backend == "whisper":
            try:
                return _WhisperSTT(model_size)
            except ImportError as exc:
                log.warning("Whisper unavailable (%s) — falling back to MOCK", exc)
                return _MockSTT(mock_responses)

        if backend == STTBackend.GOOGLE or backend == "google":
            try:
                return _GoogleSTT()
            except ImportError as exc:
                log.warning("Google STT unavailable (%s) — falling back to MOCK", exc)
                return _MockSTT(mock_responses)

        # Auto-detect
        try:
            w = _WhisperSTT(model_size)
            if w.is_available():
                return w
        except ImportError:
            pass
        try:
            g = _GoogleSTT()
            if g.is_available():
                return g
        except ImportError:
            pass
        log.info("STTEngine: no real backend available, using MOCK")
        return _MockSTT(mock_responses)

    # --- public API ---

    def listen(self, timeout: float = 5.0) -> Optional[str]:
        """Record from mic for *timeout* seconds and return transcribed text."""
        return self._impl.listen(timeout)

    def transcribe_file(self, audio_path: str) -> str:
        """Transcribe an audio file and return the text."""
        return self._impl.transcribe_file(audio_path)

    def is_available(self) -> bool:
        """Return True if the selected backend is functional."""
        return self._impl.is_available()

    @property
    def is_mock(self) -> bool:
        return isinstance(self._impl, _MockSTT)

    def set_mock_responses(self, responses: List[str]) -> None:
        """Override preset responses (only effective with MOCK backend)."""
        if isinstance(self._impl, _MockSTT):
            self._impl.set_responses(responses)
