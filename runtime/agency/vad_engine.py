"""
VAD Engine — Pass 23
Voice Activity Detection
Backends: webrtcvad → energy threshold (RMS) → MockVAD
"""

from __future__ import annotations
import struct
import math
import threading
import time
from typing import Optional, Callable

# ── backends ───────────────────────────────────────────────────────────────────

class _WebRTCVADBackend:
    def __init__(self, aggressiveness: int = 2, sample_rate: int = 16000):
        import webrtcvad  # may raise ImportError
        self._vad = webrtcvad.Vad(aggressiveness)
        self._sample_rate = sample_rate

    def is_speech(self, audio_chunk: bytes) -> bool:
        # webrtcvad requires exactly 10/20/30ms frames at 8/16/32/48 kHz
        frame_duration_ms = 20
        frame_size = int(self._sample_rate * frame_duration_ms / 1000) * 2  # 16-bit
        chunk = audio_chunk[:frame_size].ljust(frame_size, b'\x00')
        try:
            return self._vad.is_speech(chunk, self._sample_rate)
        except Exception:
            return False


class _EnergyBackend:
    """RMS-based energy threshold VAD."""

    def __init__(self, sample_rate: int = 16000):
        self._sample_rate = sample_rate
        self._noise_floor: float = 500.0  # raw RMS units, calibrated later

    def _rms(self, audio_chunk: bytes) -> float:
        if len(audio_chunk) < 2:
            return 0.0
        n = len(audio_chunk) // 2
        samples = struct.unpack(f"<{n}h", audio_chunk[:n * 2])
        return math.sqrt(sum(s * s for s in samples) / n) if n > 0 else 0.0

    def is_speech(self, audio_chunk: bytes) -> bool:
        return self._rms(audio_chunk) > self._noise_floor * 1.5

    def calibrate(self, stream, duration_s: float = 2.0):
        """Read `duration_s` seconds from stream and set noise floor."""
        chunk_size = 1024
        total_rms = 0.0
        n_chunks = 0
        end = time.time() + duration_s
        while time.time() < end:
            try:
                data = stream.read(chunk_size)
                total_rms += self._rms(data)
                n_chunks += 1
            except Exception:
                break
        if n_chunks > 0:
            self._noise_floor = total_rms / n_chunks


class _MockVAD:
    """Always reports speech — safe fallback for tests."""

    def is_speech(self, audio_chunk: bytes) -> bool:  # noqa: ARG002
        return True

    def calibrate(self, stream, duration_s: float = 2.0):  # noqa: ARG002
        pass


# ── public engine ──────────────────────────────────────────────────────────────

class VADEngine:
    """
    VAD pipeline: webrtcvad → energy threshold → MockVAD.
    All external imports are guarded inside try/except.
    """

    SILENCE_CHUNK = 1024
    SAMPLE_RATE   = 16000

    def __init__(self, sample_rate: int = 16000):
        self.SAMPLE_RATE = sample_rate
        self._backend, self._energy = self._init_backend()

    def _init_backend(self):
        energy = _EnergyBackend(self.SAMPLE_RATE)
        try:
            vad = _WebRTCVADBackend(aggressiveness=2, sample_rate=self.SAMPLE_RATE)
            return vad, energy
        except Exception:
            pass
        return energy, energy

    # ── public API ────────────────────────────────────────────────────────────

    def is_speech(self, audio_chunk: bytes) -> bool:
        try:
            return self._backend.is_speech(audio_chunk)
        except Exception:
            return _MockVAD().is_speech(audio_chunk)

    def calibrate_noise_floor(self, stream, duration_s: float = 2.0) -> None:
        """Calibrate energy floor from ambient noise."""
        try:
            if hasattr(self._energy, "calibrate"):
                self._energy.calibrate(stream, duration_s)
        except Exception:
            pass

    def listen_until_silence(
        self,
        stream,
        silence_ms: int = 1500,
        chunk_size: int = 1024,
    ) -> bytes:
        """
        Read from `stream` (pyaudio stream or file-like with .read())
        until `silence_ms` of consecutive silence is detected.
        Returns accumulated audio bytes.
        """
        frames: list[bytes] = []
        silent_chunks = 0
        chunks_per_ms = max(1, self.SAMPLE_RATE // 1000)
        silence_limit = int(silence_ms * chunks_per_ms / chunk_size) + 1

        while True:
            try:
                data = stream.read(chunk_size)
            except Exception:
                break
            if not data:
                break
            frames.append(data)
            if self.is_speech(data):
                silent_chunks = 0
            else:
                silent_chunks += 1
                if silent_chunks >= silence_limit:
                    break

        return b"".join(frames)

    @property
    def backend_name(self) -> str:
        return type(self._backend).__name__
