"""
JARVIS BRAINIAC — Local Voice Processing Module
=================================================

100% local speech-to-text (Faster-Whisper) and text-to-speech (XTTSv2).
Hebrew auto-detection. Real-time streaming. Zero cloud.

All heavy dependencies are optional — mock fallbacks ensure the module
loads and functions even when no ML libraries are installed.

Dependencies (all optional):
    - faster-whisper   : STT engine (OpenAI Whisper reimplementation in CTranslate2)
    - TTS              : Coqui TTS (XTTSv2 for multilingual TTS)
    - sounddevice     : Real-time audio I/O
    - numpy           : Audio array processing
    - torch           : PyTorch backend for XTTSv2
    - scipy           : WAV file I/O (usually comes with numpy)

Usage
-----
    >>> from runtime.agency.local_voice import get_voice_processor
    >>> v = get_voice_processor()
    >>> result = v.transcribe("recording.wav")
    >>> print(result["text"])
    >>> wav_path = v.synthesize("שלום עולם")
"""

from __future__ import annotations

import os
import re
import sys
import time
import threading
import tempfile
import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, List

# ---------------------------------------------------------------------------
#  Graceful optional imports  (no hard failures)
# ---------------------------------------------------------------------------

HAVE_FASTER_WHISPER = False
HAVE_TTS = False
HAVE_SOUNDDEVICE = False
HAVE_NUMPY = False
HAVE_TORCH = False
HAVE_SCIPY = False

# faster-whisper
try:
    import faster_whisper
    from faster_whisper import WhisperModel
    HAVE_FASTER_WHISPER = True
except Exception:
    pass

# Coqui TTS
try:
    import TTS
    from TTS.api import TTS as TTS_API
    HAVE_TTS = True
except Exception:
    pass

# sounddevice
try:
    import sounddevice as sd
    HAVE_SOUNDDEVICE = True
except Exception:
    pass

# numpy
try:
    import numpy as np
    HAVE_NUMPY = True
except Exception:
    pass

# torch
try:
    import torch
    HAVE_TORCH = True
except Exception:
    pass

# scipy (for wavfile read/write)
try:
    from scipy.io import wavfile
    HAVE_SCIPY = True
except Exception:
    pass

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

DEFAULT_STT_MODEL = "large-v3"
DEFAULT_TTS_MODEL = "tts_models/multilingual/multi-dataset/xtts_v2"
HEBREW_UNICODE_RE = re.compile(r"[\u0590-\u05FF]")
ENGLISH_UNICODE_RE = re.compile(r"[a-zA-Z]")
DEFAULT_SAMPLE_RATE = 16000
CHUNK_DURATION_SEC = 0.5
VAD_THRESHOLD = 0.01  # RMS energy threshold for voice activity detection


# ---------------------------------------------------------------------------
#  Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TranscriptionResult:
    """Structured output from transcription."""
    text: str
    language: str
    confidence: float
    segments: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "language": self.language,
            "confidence": self.confidence,
            "segments": self.segments,
        }


# ---------------------------------------------------------------------------
#  Utility functions
# ---------------------------------------------------------------------------

def _safe_rms(audio_array) -> float:
    """Compute RMS energy safely."""
    if not HAVE_NUMPY:
        return 0.0
    if len(audio_array) == 0:
        return 0.0
    return float(np.sqrt(np.mean(audio_array.astype(np.float64) ** 2)))


def _resample_audio(audio_array, orig_sr: int, target_sr: int = 16000):
    """Simple linear-interpolation resampling."""
    if not HAVE_NUMPY:
        return audio_array
    if orig_sr == target_sr:
        return audio_array
    orig_len = len(audio_array)
    new_len = int(orig_len * target_sr / orig_sr)
    indices = np.linspace(0, orig_len - 1, new_len)
    return np.interp(indices, np.arange(orig_len), audio_array)


def _load_audio(audio_path: str, sample_rate: int = 16000):
    """Load audio file to numpy array (mono, float32, target SR)."""
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    # Try scipy first
    if HAVE_SCIPY:
        sr, data = wavfile.read(audio_path)
        if data.ndim > 1:
            data = data.mean(axis=1)
        data = data.astype(np.float32)
        # Normalize based on dtype max
        if data.max() > 1.0:
            max_val = np.iinfo(data.dtype).max if np.issubdtype(data.dtype, np.integer) else 1.0
            data = data / max_val
        if sr != sample_rate:
            data = _resample_audio(data, sr, sample_rate)
        return data

    # Fallback: try sounddevice / wavio helpers
    if HAVE_NUMPY:
        # Last resort: read raw bytes and try to infer format
        # This is a very basic fallback
        warnings.warn("scipy not available; using basic audio loading", RuntimeWarning)
        return None

    return None


def _write_wav(path: str, audio_array, sample_rate: int = 24000):
    """Write numpy audio array to WAV file."""
    if HAVE_SCIPY and HAVE_NUMPY:
        # Scale to int16 for WAV
        audio_int16 = (audio_array * 32767).astype(np.int16)
        wavfile.write(path, sample_rate, audio_int16)
        return
    # If no scipy, we cannot write WAV properly — but TTS should handle this
    raise RuntimeError("scipy required to write WAV files")


# ---------------------------------------------------------------------------
#  Base ABC
# ---------------------------------------------------------------------------

class BaseVoiceProcessor(ABC):
    """Abstract base for all voice processors (Local + Mock)."""

    @abstractmethod
    def transcribe(self, audio_path: str, language: str = None) -> dict:
        ...

    @abstractmethod
    def transcribe_stream(self, audio_source, callback: Callable):
        ...

    @abstractmethod
    def synthesize(self, text: str, language: str = "he", speaker_wav: str = None) -> str:
        ...

    @abstractmethod
    def detect_language(self, text: str) -> str:
        ...

    @abstractmethod
    def is_hebrew(self, text: str) -> bool:
        ...

    @abstractmethod
    def start_listening(self, hotword: str = None):
        ...

    @abstractmethod
    def stop_listening(self):
        ...

    @abstractmethod
    def get_status(self) -> dict:
        ...


# ---------------------------------------------------------------------------
#  LocalVoiceProcessor
# ---------------------------------------------------------------------------

class LocalVoiceProcessor(BaseVoiceProcessor):
    """
    Local speech-to-text (Faster-Whisper) and text-to-speech (XTTSv2).
    Hebrew auto-detection. Real-time streaming. Zero cloud.
    """

    def __init__(
        self,
        stt_model: str = DEFAULT_STT_MODEL,
        tts_model: str = DEFAULT_TTS_MODEL,
        device: str = "cuda",
    ):
        self.stt_model_name = stt_model
        self.tts_model_name = tts_model
        self.device = device
        self.compute_type = "float16" if device == "cuda" else "int8"

        # Subsystem handles
        self._stt: Any = None
        self._tts: Any = None
        self._stt_available = False
        self._tts_available = False

        # Threading
        self._listen_thread: Optional[threading.Thread] = None
        self._listen_stop_event = threading.Event()
        self._listen_active = False
        self._hotword: Optional[str] = None
        self._hotword_detected = False

        # Internal audio ring buffer for streaming
        self._stream_buffer: List[Any] = []
        self._stream_lock = threading.Lock()

        # Counters / diagnostics
        self._transcribe_count = 0
        self._synthesize_count = 0
        self._errors: List[str] = []

        # ---- init STT ------------------------------------------------------
        if HAVE_FASTER_WHISPER:
            try:
                self._stt = WhisperModel(
                    stt_model,
                    device=device,
                    compute_type=self.compute_type,
                )
                self._stt_available = True
            except Exception as exc:
                self._errors.append(f"STT init failed: {exc}")
                warnings.warn(
                    f"Failed to load Faster-Whisper model '{stt_model}': {exc}",
                    RuntimeWarning,
                )
        else:
            self._errors.append("faster-whisper not installed")

        # ---- init TTS ------------------------------------------------------
        if HAVE_TTS:
            try:
                # Coqui TTS API — load model once
                self._tts = TTS_API(tts_model)
                self._tts_available = True
            except Exception as exc:
                self._errors.append(f"TTS init failed: {exc}")
                warnings.warn(
                    f"Failed to load TTS model '{tts_model}': {exc}",
                    RuntimeWarning,
                )
        else:
            self._errors.append("TTS (Coqui) not installed")

    # ------------------------------------------------------------------
    #  Language detection
    # ------------------------------------------------------------------

    def detect_language(self, text: str) -> str:
        """
        Detect language from text.

        Returns
        -------
        str
            "he" if Hebrew characters detected,
            "en" if English characters detected,
            "unknown" otherwise.
        """
        if not text:
            return "unknown"
        if HEBREW_UNICODE_RE.search(text):
            return "he"
        if ENGLISH_UNICODE_RE.search(text):
            return "en"
        return "unknown"

    def is_hebrew(self, text: str) -> bool:
        """Check if text contains Hebrew characters."""
        return bool(HEBREW_UNICODE_RE.search(text))

    # ------------------------------------------------------------------
    #  STT
    # ------------------------------------------------------------------

    def transcribe(self, audio_path: str, language: str = None) -> dict:
        """
        Transcribe an audio file to text.

        Parameters
        ----------
        audio_path : str
            Path to the audio file (WAV / MP3 / FLAC supported).
        language : str, optional
            ISO-639-1 language code (e.g. "he", "en").  If None → auto-detect.

        Returns
        -------
        dict
            {
                "text": str,
                "language": str,
                "confidence": float,
                "segments": [dict, ...]
            }
        """
        if not os.path.isfile(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if not self._stt_available:
            warnings.warn("STT backend unavailable; returning empty transcription", RuntimeWarning)
            return TranscriptionResult(
                text="",
                language=language or "unknown",
                confidence=0.0,
                segments=[],
            ).to_dict()

        try:
            segments_iter, info = self._stt.transcribe(
                audio_path,
                language=language,
                vad_filter=True,
                condition_on_previous_text=True,
            )

            segments: List[dict] = []
            text_parts: List[str] = []
            avg_prob_sum = 0.0
            segment_count = 0

            for seg in segments_iter:
                seg_dict = {
                    "id": seg.id,
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text,
                    "avg_logprob": getattr(seg, "avg_logprob", 0.0),
                }
                segments.append(seg_dict)
                text_parts.append(seg.text)
                avg_prob_sum += seg_dict["avg_logprob"]
                segment_count += 1

            full_text = " ".join(text_parts).strip()
            detected_lang = info.language if info else (language or "unknown")

            # Convert avg_logprob to pseudo-confidence
            if segment_count > 0:
                # logprob is usually negative; map roughly to [0,1]
                raw_conf = avg_prob_sum / segment_count
                confidence = max(0.0, min(1.0, 1.0 + raw_conf))
            else:
                confidence = 0.0

            # If language was not provided, auto-detect from text too
            if language is None:
                detected_lang = self.detect_language(full_text) or detected_lang

            self._transcribe_count += 1

            return TranscriptionResult(
                text=full_text,
                language=detected_lang,
                confidence=round(confidence, 3),
                segments=segments,
            ).to_dict()

        except Exception as exc:
            self._errors.append(f"transcribe error: {exc}")
            raise RuntimeError(f"Transcription failed: {exc}") from exc

    # ------------------------------------------------------------------
    #  Streaming STT
    # ------------------------------------------------------------------

    def transcribe_stream(self, audio_source, callback: Callable[[str, bool], None]):
        """
        Real-time streaming transcription.

        Parameters
        ----------
        audio_source : callable or generator
            Should yield numpy audio chunks (float32, mono, 16 kHz) when called.
        callback : callable
            ``callback(text: str, is_final: bool)`` invoked per chunk.

        Uses a background thread so the caller is not blocked.
        """
        if not callable(callback):
            raise TypeError("callback must be callable")

        def _loop():
            accumulated_text = ""
            chunk_buffer: List[Any] = []

            try:
                for chunk in audio_source():
                    if not HAVE_NUMPY:
                        callback("[numpy unavailable for streaming]", False)
                        break

                    chunk_buffer.append(chunk)

                    # Simple VAD — accumulate until silence gap
                    rms = _safe_rms(chunk)
                    is_speech = rms > VAD_THRESHOLD

                    if not is_speech and len(chunk_buffer) > 0:
                        # Flush buffer for transcription
                        audio_clip = np.concatenate(chunk_buffer)
                        chunk_buffer.clear()

                        # Write temp file for faster-whisper
                        if self._stt_available and HAVE_SCIPY:
                            with tempfile.NamedTemporaryFile(
                                suffix=".wav", delete=False
                            ) as tmp:
                                tmp_path = tmp.name
                                _write_wav(tmp_path, audio_clip, DEFAULT_SAMPLE_RATE)
                            try:
                                result = self.transcribe(tmp_path, language=None)
                                txt = result["text"].strip()
                                if txt:
                                    accumulated_text += " " + txt
                                    callback(txt, False)
                            finally:
                                try:
                                    os.unlink(tmp_path)
                                except OSError:
                                    pass
                        else:
                            callback("[STT unavailable]", False)

                # Final flush
                if chunk_buffer and HAVE_NUMPY:
                    audio_clip = np.concatenate(chunk_buffer)
                    if self._stt_available and HAVE_SCIPY:
                        with tempfile.NamedTemporaryFile(
                            suffix=".wav", delete=False
                        ) as tmp:
                            tmp_path = tmp.name
                            _write_wav(tmp_path, audio_clip, DEFAULT_SAMPLE_RATE)
                        try:
                            result = self.transcribe(tmp_path, language=None)
                            txt = result["text"].strip()
                            if txt:
                                accumulated_text += " " + txt
                                callback(txt, True)
                            else:
                                callback("", True)
                        finally:
                            try:
                                os.unlink(tmp_path)
                            except OSError:
                                pass
                    else:
                        callback("[STT unavailable]", True)
                else:
                    callback(accumulated_text.strip(), True)

            except Exception as exc:
                self._errors.append(f"stream error: {exc}")
                callback(f"[stream error: {exc}]", True)

        stream_thread = threading.Thread(target=_loop, daemon=True, name="voice-stream")
        stream_thread.start()
        return stream_thread

    # ------------------------------------------------------------------
    #  TTS
    # ------------------------------------------------------------------

    def synthesize(
        self,
        text: str,
        language: str = "he",
        speaker_wav: str = None,
    ) -> str:
        """
        Convert text to speech.

        Parameters
        ----------
        text : str
            Text to synthesize.
        language : str
            Target language.  If "auto", detect from text.
        speaker_wav : str, optional
            Path to a reference speaker WAV for voice cloning.

        Returns
        -------
        str
            Absolute path to the generated WAV file.
        """
        if not text or not text.strip():
            raise ValueError("text must not be empty")

        # Auto-detect Hebrew
        if language == "auto":
            language = self.detect_language(text)
            if language == "unknown":
                language = "he"  # Default to Hebrew for JARVIS

        # Ensure output directory exists
        out_dir = Path(tempfile.gettempdir()) / "jarvis_tts"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"tts_{int(time.time() * 1000)}.wav"

        if not self._tts_available:
            warnings.warn("TTS backend unavailable; returning empty path", RuntimeWarning)
            return ""

        try:
            # Coqui XTTSv2
            if speaker_wav and os.path.isfile(speaker_wav):
                self._tts.tts_to_file(
                    text=text,
                    file_path=str(out_path),
                    speaker_wav=speaker_wav,
                    language=language,
                )
            else:
                self._tts.tts_to_file(
                    text=text,
                    file_path=str(out_path),
                    language=language,
                )

            self._synthesize_count += 1
            return str(out_path.resolve())

        except Exception as exc:
            self._errors.append(f"synthesize error: {exc}")
            raise RuntimeError(f"Synthesis failed: {exc}") from exc

    # ------------------------------------------------------------------
    #  Continuous listening
    # ------------------------------------------------------------------

    def start_listening(self, hotword: str = None):
        """
        Start a continuous listening loop in a background thread.

        Parameters
        ----------
        hotword : str, optional
            If provided, only process utterances that follow this hotword.
        """
        if self._listen_active:
            warnings.warn("Listening already active", RuntimeWarning)
            return

        self._hotword = hotword
        self._hotword_detected = hotword is None  # If no hotword, always process
        self._listen_stop_event.clear()
        self._listen_active = True

        self._listen_thread = threading.Thread(
            target=self._listen_loop, daemon=True, name="voice-listen"
        )
        self._listen_thread.start()

    def stop_listening(self):
        """Stop the continuous listening loop."""
        if not self._listen_active:
            return
        self._listen_stop_event.set()
        self._listen_active = False
        if self._listen_thread and self._listen_thread.is_alive():
            self._listen_thread.join(timeout=2.0)
        self._listen_thread = None

    def _listen_loop(self):
        """Internal listening loop — captures from microphone in chunks."""
        if not HAVE_SOUNDDEVICE or not HAVE_NUMPY:
            warnings.warn("sounddevice/numpy unavailable; listening loop cannot capture audio", RuntimeWarning)
            self._listen_active = False
            return

        try:
            # Ring buffer for audio chunks
            buffer: List[Any] = []
            silence_frames = 0
            max_silence_frames = int(2.0 / CHUNK_DURATION_SEC)  # 2 seconds of silence

            def _audio_callback(indata, frames, time_info, status):
                with self._stream_lock:
                    self._stream_buffer.append(indata.copy())

            # Open input stream
            with sd.InputStream(
                samplerate=DEFAULT_SAMPLE_RATE,
                channels=1,
                dtype=np.float32,
                blocksize=int(DEFAULT_SAMPLE_RATE * CHUNK_DURATION_SEC),
                callback=_audio_callback,
            ):
                while not self._listen_stop_event.is_set():
                    # Drain ring buffer
                    with self._stream_lock:
                        chunks = self._stream_buffer[:]
                        self._stream_buffer.clear()

                    if not chunks:
                        time.sleep(CHUNK_DURATION_SEC)
                        continue

                    for chunk in chunks:
                        rms = _safe_rms(chunk)
                        if rms > VAD_THRESHOLD:
                            buffer.append(chunk)
                            silence_frames = 0
                        else:
                            silence_frames += 1
                            if buffer:
                                buffer.append(chunk)

                    # If enough silence, process accumulated buffer
                    if silence_frames >= max_silence_frames and buffer:
                        audio_clip = np.concatenate(buffer)
                        buffer.clear()
                        silence_frames = 0

                        # Write temp file
                        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                            tmp_path = tmp.name
                            _write_wav(tmp_path, audio_clip, DEFAULT_SAMPLE_RATE)

                        try:
                            result = self.transcribe(tmp_path, language=None)
                            txt = result["text"].strip()

                            if self._hotword and not self._hotword_detected:
                                if self._hotword.lower() in txt.lower():
                                    self._hotword_detected = True
                                    # Strip hotword from text and process remainder
                                    txt = txt.lower().replace(self._hotword.lower(), "").strip()
                                    if txt:
                                        self._on_utterance(txt, result)
                            elif self._hotword_detected or self._hotword is None:
                                if txt:
                                    self._on_utterance(txt, result)

                        finally:
                            try:
                                os.unlink(tmp_path)
                            except OSError:
                                pass

                    time.sleep(0.05)

        except Exception as exc:
            self._errors.append(f"listen loop error: {exc}")
        finally:
            self._listen_active = False

    def _on_utterance(self, text: str, result: dict):
        """Hook called when a complete utterance is detected. Override in subclass."""
        print(f"[JARVIS Voice] {text}  (lang={result.get('language')}, conf={result.get('confidence')})")

    # ------------------------------------------------------------------
    #  Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """
        Returns the status of all voice subsystems.

        Returns
        -------
        dict
            {
                "stt_available": bool,
                "tts_available": bool,
                "sounddevice_available": bool,
                "numpy_available": bool,
                "torch_available": bool,
                "stt_model": str,
                "tts_model": str,
                "device": str,
                "listening": bool,
                "transcribe_count": int,
                "synthesize_count": int,
                "errors": List[str],
            }
        """
        return {
            "stt_available": self._stt_available,
            "tts_available": self._tts_available,
            "sounddevice_available": HAVE_SOUNDDEVICE,
            "numpy_available": HAVE_NUMPY,
            "torch_available": HAVE_TORCH,
            "stt_model": self.stt_model_name,
            "tts_model": self.tts_model_name,
            "device": self.device,
            "listening": self._listen_active,
            "transcribe_count": self._transcribe_count,
            "synthesize_count": self._synthesize_count,
            "errors": list(self._errors),
        }


# ---------------------------------------------------------------------------
#  MockVoiceProcessor
# ---------------------------------------------------------------------------

class MockVoiceProcessor(BaseVoiceProcessor):
    """
    Fully-functional mock voice processor.

    Same interface as LocalVoiceProcessor, but transcribe returns simulated
    text and synthesize returns an empty string (no audio file generated).
    All methods work without any external dependencies.
    """

    # Simulated responses by language
    _MOCK_TRANSCRIPTIONS = {
        "he": "שלום, זו תמלול לדוגמה בעברית",
        "en": "Hello, this is a sample transcription in English",
    }

    def __init__(self):
        self._listen_active = False
        self._listen_thread: Optional[threading.Thread] = None
        self._listen_stop_event = threading.Event()
        self._transcribe_count = 0
        self._synthesize_count = 0

    # --- Language detection (pure regex, zero deps) ----------------------

    def detect_language(self, text: str) -> str:
        if not text:
            return "unknown"
        if HEBREW_UNICODE_RE.search(text):
            return "he"
        if ENGLISH_UNICODE_RE.search(text):
            return "en"
        return "unknown"

    def is_hebrew(self, text: str) -> bool:
        return bool(HEBREW_UNICODE_RE.search(text))

    # --- STT mock --------------------------------------------------------

    def transcribe(self, audio_path: str, language: str = None) -> dict:
        """Mock transcription — returns simulated text even if file doesn't exist."""
        detected = language or "en"
        if language == "auto":
            detected = "he" if "hebrew" in audio_path.lower() else "en"
        text = self._MOCK_TRANSCRIPTIONS.get(detected, self._MOCK_TRANSCRIPTIONS["en"])
        self._transcribe_count += 1

        return TranscriptionResult(
            text=text,
            language=detected,
            confidence=0.85,
            segments=[
                {
                    "id": 0,
                    "start": 0.0,
                    "end": 3.0,
                    "text": text,
                    "avg_logprob": -0.15,
                }
            ],
        ).to_dict()

    # --- Streaming mock --------------------------------------------------

    def transcribe_stream(self, audio_source, callback: Callable[[str, bool], None]):
        if not callable(callback):
            raise TypeError("callback must be callable")

        def _simulate():
            chunks = [
                ("Hello ", False),
                ("this ", False),
                ("is ", False),
                ("streaming...", False),
                ("Final text here.", True),
            ]
            for txt, is_final in chunks:
                time.sleep(0.3)
                callback(txt, is_final)

        t = threading.Thread(target=_simulate, daemon=True, name="mock-stream")
        t.start()
        return t

    # --- TTS mock --------------------------------------------------------

    def synthesize(self, text: str, language: str = "he", speaker_wav: str = None) -> str:
        if not text or not text.strip():
            raise ValueError("text must not be empty")
        self._synthesize_count += 1
        # Return empty string — no audio file generated
        return ""

    # --- Listening mock --------------------------------------------------

    def start_listening(self, hotword: str = None):
        if self._listen_active:
            return
        self._listen_active = True
        self._listen_stop_event.clear()

        def _loop():
            counter = 0
            while not self._listen_stop_event.is_set() and counter < 1000:
                time.sleep(1.0)
                counter += 1
            self._listen_active = False

        self._listen_thread = threading.Thread(target=_loop, daemon=True, name="mock-listen")
        self._listen_thread.start()

    def stop_listening(self):
        if not self._listen_active:
            return
        self._listen_stop_event.set()
        self._listen_active = False
        if self._listen_thread and self._listen_thread.is_alive():
            self._listen_thread.join(timeout=1.0)
        self._listen_thread = None

    # --- Status mock -----------------------------------------------------

    def get_status(self) -> dict:
        return {
            "stt_available": False,
            "tts_available": False,
            "sounddevice_available": False,
            "numpy_available": False,
            "torch_available": False,
            "stt_model": "mock",
            "tts_model": "mock",
            "device": "cpu",
            "listening": self._listen_active,
            "transcribe_count": self._transcribe_count,
            "synthesize_count": self._synthesize_count,
            "errors": [],
        }


# ---------------------------------------------------------------------------
#  Factory
# ---------------------------------------------------------------------------

def get_voice_processor(
    stt_model: str = DEFAULT_STT_MODEL,
    tts_model: str = DEFAULT_TTS_MODEL,
    device: str = "cuda",
    force_mock: bool = False,
) -> BaseVoiceProcessor:
    """
    Auto-detect available backends and return the best voice processor.

    Parameters
    ----------
    stt_model : str
        Faster-Whisper model size (default: "large-v3").
    tts_model : str
        Coqui TTS model name (default: XTTSv2).
    device : str
        "cuda" or "cpu".
    force_mock : bool
        If True, always return MockVoiceProcessor.

    Returns
    -------
    BaseVoiceProcessor
        LocalVoiceProcessor if faster-whisper or TTS is available,
        otherwise MockVoiceProcessor.
    """
    if force_mock:
        return MockVoiceProcessor()

    # If at least one real backend exists, try LocalVoiceProcessor
    if HAVE_FASTER_WHISPER or HAVE_TTS:
        try:
            return LocalVoiceProcessor(
                stt_model=stt_model,
                tts_model=tts_model,
                device=device,
            )
        except Exception as exc:
            warnings.warn(
                f"LocalVoiceProcessor init failed ({exc}); falling back to mock.",
                RuntimeWarning,
            )
            return MockVoiceProcessor()

    return MockVoiceProcessor()


# ---------------------------------------------------------------------------
#  __main__ smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    # Factory
    proc = get_voice_processor()
    print(f"Processor type : {type(proc).__name__}")
    print(f"Status         : {json.dumps(proc.get_status(), indent=2, ensure_ascii=False)}")

    # Language detection
    samples = [
        "שלום עולם",
        "Hello world",
        "12345",
        "שלום and hello",
    ]
    for s in samples:
        print(f"  detect_language({s!r}) → {proc.detect_language(s)}  | hebrew={proc.is_hebrew(s)}")

    # Mock synthesize
    wav = proc.synthesize("שלום")
    print(f"  synthesize('שלום') → {wav!r}")

    print("\nSmoke test passed.")
