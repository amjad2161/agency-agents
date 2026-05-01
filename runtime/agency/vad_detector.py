"""Voice Activity Detection (VAD).

Detects speech versus silence in raw PCM audio data using an RMS energy
threshold.  No audio hardware is needed — the class is fully testable
with synthesised audio produced by the static helper methods.

Audio format assumptions (unless otherwise noted):
- 16-bit signed PCM, little-endian
- Mono (single channel)
- Sample rate: 16 000 Hz (adjustable via ``sample_rate`` arguments)
"""

from __future__ import annotations

import math
import struct
from typing import Sequence


class VADDetector:
    """Detect speech vs silence in audio data using RMS energy threshold."""

    def __init__(
        self,
        threshold: float = 0.02,
        frame_duration_ms: int = 30,
    ) -> None:
        self.threshold = threshold
        self.frame_duration_ms = frame_duration_ms
        self._is_speaking: bool = False

    # ------------------------------------------------------------------
    # Core detection
    # ------------------------------------------------------------------

    @staticmethod
    def _rms(audio_chunk: bytes) -> float:
        """Compute normalised RMS energy of raw 16-bit PCM bytes."""
        n = len(audio_chunk) // 2
        if n == 0:
            return 0.0
        samples = struct.unpack(f"<{n}h", audio_chunk[: n * 2])
        mean_sq = sum(s * s for s in samples) / n
        # Normalise by max 16-bit value (32768)
        return math.sqrt(mean_sq) / 32768.0

    def is_speech(self, audio_chunk: bytes) -> bool:
        """Return *True* if *audio_chunk* contains speech-level energy."""
        rms = self._rms(audio_chunk)
        speaking = rms >= self.threshold
        self._is_speaking = speaking
        return speaking

    # ------------------------------------------------------------------
    # Stream processing
    # ------------------------------------------------------------------

    def process_stream(
        self, audio_chunks: list[bytes]
    ) -> list[dict]:
        """Process a list of audio chunks.

        Returns a list of dicts::

            [{chunk_index: int, is_speech: bool, rms: float}, ...]
        """
        results: list[dict] = []
        for idx, chunk in enumerate(audio_chunks):
            rms = self._rms(chunk)
            speech = rms >= self.threshold
            self._is_speaking = speech
            results.append({"chunk_index": idx, "is_speech": speech, "rms": rms})
        return results

    def detect_utterances(
        self,
        audio_chunks: list[bytes],
        min_speech_frames: int = 3,
    ) -> list[tuple[int, int]]:
        """Find contiguous speech segments in *audio_chunks*.

        A segment must span at least *min_speech_frames* consecutive
        speech frames to be reported.

        Returns a list of ``(start_index, end_index)`` tuples (inclusive
        of *end_index*).
        """
        stream = self.process_stream(audio_chunks)
        utterances: list[tuple[int, int]] = []
        in_speech = False
        start: int = 0

        for item in stream:
            i = item["chunk_index"]
            if item["is_speech"]:
                if not in_speech:
                    in_speech = True
                    start = i
            else:
                if in_speech:
                    length = i - start
                    if length >= min_speech_frames:
                        utterances.append((start, i - 1))
                    in_speech = False

        # Close any open segment at end of stream
        if in_speech:
            end = len(audio_chunks) - 1
            length = end - start + 1
            if length >= min_speech_frames:
                utterances.append((start, end))

        return utterances

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    @staticmethod
    def generate_silence(
        duration_ms: int, sample_rate: int = 16_000
    ) -> bytes:
        """Generate a buffer of silent (zero-value) PCM audio."""
        n_samples = int(sample_rate * duration_ms / 1000)
        return struct.pack(f"<{n_samples}h", *([0] * n_samples))

    @staticmethod
    def generate_tone(
        frequency_hz: int,
        duration_ms: int,
        sample_rate: int = 16_000,
    ) -> bytes:
        """Generate a pure sine-wave tone at *frequency_hz*.

        Amplitude is set to ~80 % of the 16-bit maximum so the resulting
        RMS is well above any reasonable VAD threshold.
        """
        n_samples = int(sample_rate * duration_ms / 1000)
        amplitude = 26000  # ~79 % of 32767
        samples = [
            int(amplitude * math.sin(2 * math.pi * frequency_hz * i / sample_rate))
            for i in range(n_samples)
        ]
        return struct.pack(f"<{n_samples}h", *samples)
