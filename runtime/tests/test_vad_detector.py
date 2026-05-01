"""Tests for agency.vad_detector — VADDetector."""

from __future__ import annotations

import struct

import pytest

from agency.vad_detector import VADDetector


class TestVADDetectorBasics:
    def test_default_threshold(self):
        vad = VADDetector()
        assert vad.threshold == 0.02

    def test_custom_threshold(self):
        vad = VADDetector(threshold=0.1)
        assert vad.threshold == 0.1

    def test_initial_is_not_speaking(self):
        vad = VADDetector()
        assert vad._is_speaking is False


class TestGenerateHelpers:
    def test_generate_silence_correct_length(self):
        silence = VADDetector.generate_silence(duration_ms=100, sample_rate=16000)
        # 100ms at 16 kHz = 1600 samples × 2 bytes = 3200 bytes
        assert len(silence) == 3200

    def test_generate_silence_all_zeros(self):
        silence = VADDetector.generate_silence(30)
        n = len(silence) // 2
        samples = struct.unpack(f"<{n}h", silence)
        assert all(s == 0 for s in samples)

    def test_generate_tone_correct_length(self):
        tone = VADDetector.generate_tone(440, duration_ms=100, sample_rate=16000)
        assert len(tone) == 3200  # 1600 samples × 2 bytes

    def test_generate_tone_non_zero(self):
        tone = VADDetector.generate_tone(440, duration_ms=100)
        n = len(tone) // 2
        samples = struct.unpack(f"<{n}h", tone)
        assert any(s != 0 for s in samples)


class TestIsSpeech:
    def test_silence_not_speech(self):
        vad = VADDetector(threshold=0.02)
        silence = VADDetector.generate_silence(30)
        assert vad.is_speech(silence) is False

    def test_tone_is_speech(self):
        vad = VADDetector(threshold=0.02)
        tone = VADDetector.generate_tone(440, 30)
        assert vad.is_speech(tone) is True

    def test_is_speaking_state_updated(self):
        vad = VADDetector(threshold=0.02)
        tone = VADDetector.generate_tone(440, 30)
        vad.is_speech(tone)
        assert vad._is_speaking is True
        silence = VADDetector.generate_silence(30)
        vad.is_speech(silence)
        assert vad._is_speaking is False

    def test_empty_chunk_is_silence(self):
        vad = VADDetector(threshold=0.02)
        assert vad.is_speech(b"") is False


class TestProcessStream:
    def test_process_stream_returns_one_per_chunk(self):
        vad = VADDetector()
        chunks = [VADDetector.generate_silence(30)] * 5
        results = vad.process_stream(chunks)
        assert len(results) == 5

    def test_process_stream_result_keys(self):
        vad = VADDetector()
        chunks = [VADDetector.generate_silence(30)]
        result = vad.process_stream(chunks)[0]
        assert "chunk_index" in result
        assert "is_speech" in result
        assert "rms" in result

    def test_process_stream_tone_flagged_as_speech(self):
        vad = VADDetector(threshold=0.02)
        chunks = [VADDetector.generate_tone(440, 30)]
        results = vad.process_stream(chunks)
        assert results[0]["is_speech"] is True

    def test_process_stream_rms_is_float(self):
        vad = VADDetector()
        chunks = [VADDetector.generate_silence(30)]
        results = vad.process_stream(chunks)
        assert isinstance(results[0]["rms"], float)


class TestDetectUtterances:
    def test_no_speech_returns_empty(self):
        vad = VADDetector(threshold=0.02)
        chunks = [VADDetector.generate_silence(30)] * 10
        utterances = vad.detect_utterances(chunks)
        assert utterances == []

    def test_continuous_speech_returns_one_utterance(self):
        vad = VADDetector(threshold=0.02)
        tone = VADDetector.generate_tone(440, 30)
        chunks = [tone] * 10
        utterances = vad.detect_utterances(chunks, min_speech_frames=3)
        assert len(utterances) == 1
        start, end = utterances[0]
        assert start == 0
        assert end == 9

    def test_utterance_below_min_frames_skipped(self):
        vad = VADDetector(threshold=0.02)
        tone = VADDetector.generate_tone(440, 30)
        silence = VADDetector.generate_silence(30)
        # Only 2 frames of speech, min=3 → should be skipped
        chunks = [silence, tone, tone, silence, silence]
        utterances = vad.detect_utterances(chunks, min_speech_frames=3)
        assert utterances == []

    def test_utterance_indices_are_tuples(self):
        vad = VADDetector(threshold=0.02)
        tone = VADDetector.generate_tone(440, 30)
        chunks = [tone] * 5
        utterances = vad.detect_utterances(chunks, min_speech_frames=3)
        for u in utterances:
            assert isinstance(u, tuple)
            assert len(u) == 2
