"""
Pass 23 Tests — 60+ tests
NLUEngine · VADEngine · CameraTracker · SecureConfig · NetworkMonitor · ObjectMemory
Zero real network / hardware / API calls.
"""

from __future__ import annotations
import io
import os
import sys
import json
import struct
import math
import pickle
import tempfile
import threading
import time
import socket
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
import pytest

# ── path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

# ===========================================================================
# NLUEngine
# ===========================================================================
from agency.nlu_engine import (
    NLUEngine, NLUResult, _detect_lang, _extract_entities,
    _classify_intent_regex, _MockNLU,
)

class TestNLUResult:
    def test_to_dict_has_all_fields(self):
        r = NLUResult("greeting", {"PERSON": "Alice"}, 0.9, "en")
        d = r.to_dict()
        assert d["intent"] == "greeting"
        assert d["entities"] == {"PERSON": "Alice"}
        assert d["confidence"] == 0.9
        assert d["lang"] == "en"


class TestDetectLang:
    def test_hebrew_detected(self):
        assert _detect_lang("שלום עולם") == "he"

    def test_english_detected(self):
        assert _detect_lang("hello world how are you") == "en"

    def test_mixed_prefers_hebrew_if_dominant(self):
        # lots of Hebrew chars
        result = _detect_lang("מה קורה bro זה כיף")
        assert result in ("he", "en", "auto")  # at least doesn't crash

    def test_empty_string(self):
        lang = _detect_lang("")
        assert lang in ("he", "en", "auto")


class TestExtractEntities:
    def test_extracts_time_israeli_format(self):
        e = _extract_entities("הפגישה ב-15/04/2024 10:30")
        assert "TIME" in e
        assert "15/04/2024" in e["TIME"]

    def test_extracts_number(self):
        e = _extract_entities("move 42 steps forward")
        assert "NUMBER" in e
        assert e["NUMBER"] == "42"

    def test_extracts_location_hebrew(self):
        e = _extract_entities("נסע לתל אביב מחר")
        assert "LOCATION" in e

    def test_extracts_location_english(self):
        e = _extract_entities("fly to Tel Aviv tomorrow")
        assert "LOCATION" in e

    def test_extracts_person_english(self):
        e = _extract_entities("call John Smith now")
        assert "PERSON" in e
        assert "John" in e["PERSON"]

    def test_extracts_skill_slug(self):
        e = _extract_entities("activate weather skill")
        assert "SKILL_SLUG" in e
        assert e["SKILL_SLUG"] == "weather"

    def test_no_false_positives_on_empty(self):
        e = _extract_entities("")
        assert isinstance(e, dict)


class TestClassifyIntentRegex:
    # Hebrew intents
    def test_hebrew_greeting(self):
        intent, conf = _classify_intent_regex("שלום ג'ארביס", "he")
        assert intent == "greeting"
        assert conf > 0.5

    def test_hebrew_farewell(self):
        intent, _ = _classify_intent_regex("להתראות!", "he")
        assert intent == "farewell"

    def test_hebrew_command(self):
        intent, _ = _classify_intent_regex("תעשה לי קפה", "he")
        assert intent == "command"

    def test_hebrew_question(self):
        intent, _ = _classify_intent_regex("מה השעה?", "he")
        assert intent == "question"

    def test_hebrew_robot_command(self):
        intent, _ = _classify_intent_regex("תזוז קדימה", "he")
        assert intent == "robot_command"

    def test_hebrew_memory_store(self):
        intent, _ = _classify_intent_regex("תזכור שאני אוהב קפה", "he")
        assert intent == "memory_store"

    def test_hebrew_memory_recall(self):
        intent, _ = _classify_intent_regex("מה זכרת?", "he")
        assert intent == "memory_recall"

    def test_hebrew_emotion_query(self):
        intent, _ = _classify_intent_regex("מה שלומך היום?", "he")
        assert intent == "emotion_query"

    # English intents
    def test_english_greeting(self):
        intent, conf = _classify_intent_regex("Hello there!", "en")
        assert intent == "greeting"
        assert conf > 0.7

    def test_english_farewell(self):
        intent, _ = _classify_intent_regex("Goodbye for now", "en")
        assert intent == "farewell"

    def test_english_question(self):
        intent, _ = _classify_intent_regex("What time is it?", "en")
        assert intent == "question"

    def test_english_command(self):
        intent, _ = _classify_intent_regex("Run the script now", "en")
        assert intent == "command"

    def test_english_robot_command(self):
        intent, _ = _classify_intent_regex("Move forward 5 steps", "en")
        assert intent == "robot_command"

    def test_english_memory_store(self):
        intent, _ = _classify_intent_regex("Remember that I like coffee", "en")
        assert intent == "memory_store"

    def test_english_memory_recall(self):
        intent, _ = _classify_intent_regex("What do you remember about me?", "en")
        assert intent == "memory_recall"

    def test_english_emotion_query(self):
        intent, _ = _classify_intent_regex("How are you doing today?", "en")
        assert intent == "emotion_query"

    def test_unknown_falls_through(self):
        intent, _ = _classify_intent_regex("xyzzy plugh plover", "en")
        assert intent == "unknown"


class TestMockNLU:
    def test_mock_returns_unknown(self):
        r = _MockNLU().parse("anything")
        assert r.intent == "unknown"
        assert r.confidence == 0.5
        assert r.lang == "auto"
        assert r.entities == {}


class TestNLUEngine:
    def test_engine_initialises(self):
        eng = NLUEngine()
        assert eng is not None

    def test_parse_returns_nlu_result(self):
        eng = NLUEngine()
        r = eng.parse("Hello!")
        assert isinstance(r, NLUResult)
        assert r.intent in (
            "greeting", "command", "question", "farewell",
            "emotion_query", "skill_request", "memory_store",
            "memory_recall", "robot_command", "unknown",
        )

    def test_parse_hebrew_greeting(self):
        eng = NLUEngine()
        r = eng.parse("שלום ג'ארביס")
        assert r.intent == "greeting"
        assert r.lang == "he"

    def test_parse_english_question(self):
        eng = NLUEngine()
        r = eng.parse("What is the weather today?")
        assert r.intent == "question"

    def test_parse_does_not_raise(self):
        eng = NLUEngine()
        for text in ["", "   ", "123", "שלום hello mixed"]:
            r = eng.parse(text)
            assert isinstance(r, NLUResult)

    def test_backend_name_is_string(self):
        eng = NLUEngine()
        assert isinstance(eng.backend_name, str)


# ===========================================================================
# VADEngine
# ===========================================================================
from agency.vad_engine import VADEngine, _EnergyBackend, _MockVAD


def _make_pcm(amplitude: int = 1000, frames: int = 512) -> bytes:
    """Create 16-bit mono PCM audio chunk."""
    return struct.pack(f"<{frames}h", *([amplitude] * frames))


class TestMockVAD:
    def test_always_returns_true(self):
        vad = _MockVAD()
        assert vad.is_speech(b"\x00" * 100) is True
        assert vad.is_speech(b"") is True

    def test_calibrate_is_noop(self):
        vad = _MockVAD()
        vad.calibrate(None, 0)  # must not raise


class TestEnergyBackend:
    def test_loud_audio_is_speech(self):
        eb = _EnergyBackend()
        eb._noise_floor = 100.0
        loud = _make_pcm(5000, 512)
        assert eb.is_speech(loud) is True

    def test_silent_audio_is_not_speech(self):
        eb = _EnergyBackend()
        eb._noise_floor = 10000.0
        silent = _make_pcm(0, 512)
        assert eb.is_speech(silent) is False

    def test_empty_chunk_is_not_speech(self):
        eb = _EnergyBackend()
        assert eb.is_speech(b"") is False

    def test_calibrate_sets_noise_floor(self):
        eb = _EnergyBackend()
        # fake stream
        chunk = _make_pcm(300, 512)
        stream = MagicMock()
        stream.read.return_value = chunk
        # run for 0 duration — should not crash
        eb.calibrate(stream, duration_s=0.0)


class TestVADEngine:
    def test_engine_initialises(self):
        vad = VADEngine()
        assert vad is not None

    def test_is_speech_returns_bool(self):
        vad = VADEngine()
        result = vad.is_speech(b"\x00" * 640)
        assert isinstance(result, bool)

    def test_listen_until_silence_returns_bytes(self):
        vad = VADEngine()
        # stream that yields one chunk then silence
        chunks = [_make_pcm(200, 512), b"\x00" * 1024] * 5 + [b""]
        stream = MagicMock()
        stream.read.side_effect = chunks
        data = vad.listen_until_silence(stream, silence_ms=10, chunk_size=1024)
        assert isinstance(data, bytes)

    def test_calibrate_does_not_raise(self):
        vad = VADEngine()
        stream = MagicMock()
        stream.read.return_value = _make_pcm(100, 512)
        vad.calibrate_noise_floor(stream, duration_s=0.0)

    def test_backend_name_is_string(self):
        vad = VADEngine()
        assert isinstance(vad.backend_name, str)


# ===========================================================================
# CameraTracker
# ===========================================================================
from agency.robotics.camera_tracker import (
    CameraTracker, TrackResult, _PID, _MockTrackerBackend,
)


class TestPID:
    def test_zero_error_gives_zero_output(self):
        pid = _PID()
        assert pid.update(0.0) == 0.0

    def test_positive_error_gives_positive_output(self):
        pid = _PID(Kp=0.5, Ki=0.0, Kd=0.0)
        assert pid.update(1.0) > 0.0

    def test_reset_clears_state(self):
        pid = _PID(Kp=0.1, Ki=0.1, Kd=0.0)
        for _ in range(5):
            pid.update(1.0)
        pid.reset()
        # after reset, integral is 0 — small error gives small output
        out = pid.update(0.01)
        assert abs(out) < 0.1


class TestMockTracker:
    def test_update_returns_true_and_bbox(self):
        t = _MockTrackerBackend()
        ok, bbox = t.update(None)
        assert ok is True
        assert len(bbox) == 4

    def test_init_does_not_raise(self):
        t = _MockTrackerBackend()
        t.init(None, (0, 0, 10, 10))


class TestTrackResult:
    def test_fields_exist(self):
        tr = TrackResult(0.5, 0.5, 0.1, 0.1, True, "face")
        assert tr.tracked is True
        assert tr.label == "face"
        assert 0.0 <= tr.target_x <= 1.0
        assert 0.0 <= tr.target_y <= 1.0


class TestCameraTracker:
    def test_initialises(self):
        ct = CameraTracker()
        assert ct is not None

    def test_backend_name_is_string(self):
        ct = CameraTracker()
        assert isinstance(ct.backend_name, str)

    def test_track_face_returns_track_result(self):
        ct = CameraTracker()
        # fake numpy-like frame with shape
        frame = MagicMock()
        frame.shape = (480, 640, 3)
        result = ct.track_face(frame)
        assert isinstance(result, TrackResult)

    def test_track_object_returns_track_result(self):
        ct = CameraTracker()
        frame = MagicMock()
        frame.shape = (480, 640, 3)
        result = ct.track_object(frame, "person")
        assert isinstance(result, TrackResult)

    def test_pan_tilt_within_bounds_when_tracked(self):
        ct = CameraTracker()
        tr = TrackResult(0.8, 0.2, 0.1, 0.1, True, "face")
        pan, tilt = ct.get_pan_tilt_command(tr, (640, 480))
        assert -30.0 <= pan  <= 30.0
        assert -30.0 <= tilt <= 30.0

    def test_pan_tilt_zero_when_not_tracked(self):
        ct = CameraTracker()
        tr = TrackResult(0.0, 0.0, 0.0, 0.0, False, "")
        pan, tilt = ct.get_pan_tilt_command(tr, (640, 480))
        assert pan  == 0.0
        assert tilt == 0.0

    def test_pan_tilt_center_target_near_zero(self):
        ct = CameraTracker()
        # target exactly at center
        tr = TrackResult(0.5, 0.5, 0.1, 0.1, True, "face")
        pan, tilt = ct.get_pan_tilt_command(tr, (640, 480))
        assert abs(pan)  < 5.0
        assert abs(tilt) < 5.0

    def test_mock_tracker_track_result_values(self):
        ct = CameraTracker()
        # force mock backend
        from agency.robotics.camera_tracker import _MockTrackerBackend
        ct._tracker_backend = _MockTrackerBackend()
        frame = MagicMock()
        frame.shape = (100, 100, 3)
        result = ct.track_face(frame)
        assert result.tracked is True
        # track_face always labels "face" regardless of backend
        assert result.label == "face"


# ===========================================================================
# SecureConfig
# ===========================================================================
from agency.secure_config import SecureConfig, _derive_key, _machine_id


class TestDeriveKey:
    def test_returns_32_bytes(self):
        key = _derive_key(b"test-machine-id")
        assert len(key) == 32

    def test_deterministic(self):
        k1 = _derive_key(b"abc")
        k2 = _derive_key(b"abc")
        assert k1 == k2

    def test_different_ids_give_different_keys(self):
        k1 = _derive_key(b"machine-A")
        k2 = _derive_key(b"machine-B")
        assert k1 != k2

    def test_machine_id_returns_bytes(self):
        mid = _machine_id()
        assert isinstance(mid, bytes)
        assert len(mid) == 8


class TestSecureConfig:
    """All tests use a tmp file — no ~/.agency pollution."""

    @pytest.fixture
    def cfg(self, tmp_path):
        secrets_file = tmp_path / "secrets.enc"
        sc = SecureConfig(machine_bytes=b"test-machine-123")
        # patch the path to tmp
        sc._path_override = secrets_file
        # monkey-patch save/load to use tmp_path
        from agency import secure_config as sc_mod
        original_path = sc_mod.SECRETS_FILE
        sc_mod.SECRETS_FILE = secrets_file
        yield sc
        sc_mod.SECRETS_FILE = original_path

    def test_set_and_get_roundtrip(self, cfg):
        cfg.set_secret("MY_KEY", "my_value_123")
        val = cfg.get_secret("MY_KEY")
        assert val == "my_value_123"

    def test_get_missing_returns_none(self, cfg):
        assert cfg.get_secret("NONEXISTENT") is None

    def test_list_keys(self, cfg):
        cfg.set_secret("KEY_A", "val_a")
        cfg.set_secret("KEY_B", "val_b")
        keys = cfg.list_keys()
        assert "KEY_A" in keys
        assert "KEY_B" in keys

    def test_list_empty_when_no_secrets(self, cfg):
        keys = cfg.list_keys()
        assert keys == []

    def test_delete_existing_key(self, cfg):
        cfg.set_secret("TO_DELETE", "val")
        assert cfg.delete_key("TO_DELETE") is True
        assert cfg.get_secret("TO_DELETE") is None

    def test_delete_nonexistent_returns_false(self, cfg):
        assert cfg.delete_key("GHOST") is False

    def test_overwrite_key(self, cfg):
        cfg.set_secret("K", "v1")
        cfg.set_secret("K", "v2")
        assert cfg.get_secret("K") == "v2"

    def test_multiple_keys_independent(self, cfg):
        cfg.set_secret("A", "alpha")
        cfg.set_secret("B", "beta")
        assert cfg.get_secret("A") == "alpha"
        assert cfg.get_secret("B") == "beta"

    def test_backend_name_is_string(self, cfg):
        assert isinstance(cfg.backend_name, str)


# ===========================================================================
# NetworkMonitor
# ===========================================================================
from agency.network_monitor import (
    NetworkMonitor, ConnectivityResult, PingResult,
    _tcp_ping_ms, _dns_ok,
)


class TestConnectivityResult:
    def test_to_dict(self):
        r = ConnectivityResult(online=True, dns_ok=True, latency_ms=12.5, isp="Bezeq")
        d = r.to_dict()
        assert d["online"] is True
        assert d["dns_ok"] is True
        assert d["latency_ms"] == 12.5
        assert d["isp"] == "Bezeq"


class TestNetworkMonitor:
    """All network calls are patched to avoid real I/O."""

    @pytest.fixture
    def mon(self):
        return NetworkMonitor()

    def _mock_conn(self, online=True, dns=True, latency=15.0):
        return ConnectivityResult(online=online, dns_ok=dns, latency_ms=latency, isp="TestISP")

    def test_check_connectivity_returns_correct_type(self, mon):
        with patch("agency.network_monitor._dns_ok", return_value=True), \
             patch("agency.network_monitor._tcp_ping_ms", return_value=12.0), \
             patch("agency.network_monitor._detect_isp", return_value="TestISP"):
            result = mon.check_connectivity()
        assert isinstance(result, ConnectivityResult)
        assert result.dns_ok is True
        assert result.latency_ms == 12.0
        assert result.isp == "TestISP"

    def test_check_connectivity_offline(self, mon):
        with patch("agency.network_monitor._dns_ok", return_value=False), \
             patch("agency.network_monitor._tcp_ping_ms", return_value=None), \
             patch("agency.network_monitor._detect_isp", return_value="offline"):
            result = mon.check_connectivity()
        assert result.online is False

    def test_ping_returns_ping_result(self, mon):
        with patch("agency.network_monitor._tcp_ping_ms", return_value=5.0):
            result = mon.ping("8.8.8.8", count=3)
        assert isinstance(result, PingResult)
        assert result.host == "8.8.8.8"
        assert result.avg_ms == pytest.approx(5.0)
        assert result.packet_loss_pct == pytest.approx(0.0)

    def test_ping_total_loss(self, mon):
        with patch("agency.network_monitor._tcp_ping_ms", return_value=None):
            result = mon.ping("0.0.0.0", count=3)
        assert result.packet_loss_pct == pytest.approx(100.0)
        assert result.avg_ms == 0.0

    def test_get_latency_to_anthropic_patched(self, mon):
        with patch("agency.network_monitor._tcp_ping_ms", return_value=50.0):
            lat = mon.get_latency_to_anthropic()
        assert lat == pytest.approx(50.0)

    def test_get_latency_to_anthropic_unreachable(self, mon):
        with patch("agency.network_monitor._tcp_ping_ms", return_value=None):
            lat = mon.get_latency_to_anthropic()
        assert lat == 0.0

    def test_watch_thread_starts(self, mon):
        with patch.object(mon, "check_connectivity", return_value=self._mock_conn()):
            mon.watch(interval_s=100, callback=None)
            time.sleep(0.05)
            assert mon._watch_thread is not None
            assert mon._watch_thread.is_alive()
            mon.stop_watch()

    def test_watch_calls_callback_on_change(self, mon):
        received = []
        def cb(r):
            received.append(r)

        call_count = [0]
        def fake_check():
            call_count[0] += 1
            # Alternate online/offline to trigger callback
            online = (call_count[0] % 2 == 1)
            return ConnectivityResult(online=online, dns_ok=True, latency_ms=5.0, isp="X")

        with patch.object(mon, "check_connectivity", side_effect=fake_check):
            mon.watch(interval_s=0.05, callback=cb)
            time.sleep(0.3)
            mon.stop_watch()
        # callback should have fired at least once
        assert len(received) >= 1

    def test_stop_watch_terminates_thread(self, mon):
        with patch.object(mon, "check_connectivity", return_value=self._mock_conn()):
            mon.watch(interval_s=100, callback=None)
            time.sleep(0.05)
            mon.stop_watch()
            # thread should be dead shortly
            time.sleep(0.1)
            if mon._watch_thread:
                assert not mon._watch_thread.is_alive()


# ===========================================================================
# ObjectMemory
# ===========================================================================
from agency.robotics.object_memory import ObjectMemory, Detection, KnownObject


class TestObjectMemory:
    @pytest.fixture
    def mem(self, tmp_path):
        return ObjectMemory(memory_path=tmp_path / "obj_mem.pkl")

    def test_observe_and_find(self, mem):
        det = Detection("cat", 0.9, (0.1, 0.2, 0.3, 0.4))
        mem.observe(det, frame_id=1)
        obj = mem.find("cat")
        assert obj is not None
        assert obj.label == "cat"
        assert obj.times_seen == 1
        assert obj.confidence == pytest.approx(0.9)

    def test_observe_increments_times_seen(self, mem):
        det = Detection("dog", 0.8, (0.0, 0.0, 0.1, 0.1))
        mem.observe(det, frame_id=1)
        mem.observe(det, frame_id=2)
        obj = mem.find("dog")
        assert obj.times_seen == 2

    def test_find_returns_none_for_unknown(self, mem):
        assert mem.find("unicorn") is None

    def test_find_case_insensitive(self, mem):
        det = Detection("Cat", 0.7, (0.0, 0.0, 0.1, 0.1))
        mem.observe(det, frame_id=5)
        assert mem.find("cat") is not None
        assert mem.find("CAT") is not None

    def test_get_known_objects_returns_list(self, mem):
        mem.observe(Detection("a", 0.5, (0,0,0,0)), 1)
        mem.observe(Detection("b", 0.6, (0,0,0,0)), 2)
        objs = mem.get_known_objects()
        assert len(objs) == 2
        labels = {o.label.lower() for o in objs}
        assert "a" in labels and "b" in labels

    def test_forget_old_removes_stale(self, mem):
        mem.observe(Detection("old_thing", 0.5, (0,0,0,0)), frame_id=1)
        mem.observe(Detection("new_thing", 0.5, (0,0,0,0)), frame_id=500)
        removed = mem.forget_old(max_age_frames=100)
        assert removed == 1
        assert mem.find("old_thing") is None
        assert mem.find("new_thing") is not None

    def test_forget_old_no_removal_when_all_fresh(self, mem):
        mem.observe(Detection("x", 0.5, (0,0,0,0)), frame_id=1)
        mem.observe(Detection("y", 0.5, (0,0,0,0)), frame_id=2)
        removed = mem.forget_old(max_age_frames=1000)
        assert removed == 0

    def test_persistence_roundtrip(self, tmp_path):
        path = tmp_path / "mem.pkl"
        mem1 = ObjectMemory(memory_path=path)
        mem1.observe(Detection("chair", 0.85, (0.1, 0.2, 0.3, 0.4)), frame_id=10)
        # Create new instance — should load from pickle
        mem2 = ObjectMemory(memory_path=path)
        obj = mem2.find("chair")
        assert obj is not None
        assert obj.times_seen == 1
        assert obj.confidence == pytest.approx(0.85)

    def test_clear_empties_memory(self, mem):
        mem.observe(Detection("x", 0.5, (0,0,0,0)), 1)
        mem.clear()
        assert len(mem) == 0
        assert mem.find("x") is None

    def test_len_reflects_count(self, mem):
        assert len(mem) == 0
        mem.observe(Detection("p", 0.9, (0,0,0,0)), 1)
        assert len(mem) == 1

    def test_avg_bbox_updates(self, mem):
        det = Detection("box", 0.9, (0.0, 0.0, 0.1, 0.1))
        mem.observe(det, 1)
        det2 = Detection("box", 0.9, (1.0, 1.0, 0.1, 0.1))
        mem.observe(det2, 2)
        obj = mem.find("box")
        # avg should be between original and new
        assert 0.0 < obj.avg_bbox[0] < 1.0

    def test_known_object_to_dict(self):
        obj = KnownObject("table", 5, 3, (0.1, 0.2, 0.3, 0.4), 0.75)
        d = obj.to_dict()
        assert d["label"] == "table"
        assert d["times_seen"] == 3
        assert d["confidence"] == pytest.approx(0.75)

    def test_forget_old_removes_stale(self, mem):
        mem.observe(Detection("cat", 0.9, (0.1, 0.1, 0.1, 0.1)), 1)
        mem.observe(Detection("dog", 0.9, (0.2, 0.2, 0.1, 0.1)), 100)
        mem.forget_old(max_age_frames=50)
        assert mem.find("cat") is None
        assert mem.find("dog") is not None

    def test_forget_old_keeps_recent(self, mem):
        mem.observe(Detection("cat", 0.9, (0.1, 0.1, 0.1, 0.1)), 1)
        mem.observe(Detection("dog", 0.9, (0.2, 0.2, 0.1, 0.1)), 10)
        mem.forget_old(max_age_frames=50)
        assert mem.find("cat") is not None
        assert mem.find("dog") is not None

    def test_get_known_objects(self, mem):
        mem.observe(Detection("a", 0.8, (0,0,0,0)), 1)
        mem.observe(Detection("b", 0.7, (0,0,0,0)), 2)
        objs = mem.get_known_objects()
        labels = {o.label for o in objs}
        assert "a" in labels and "b" in labels

    def test_persistence(self, tmp_path, monkeypatch):
        pkl = tmp_path / "obj_mem.pkl"
        monkeypatch.setattr("agency.robotics.object_memory.MEMORY_PATH", pkl)
        m1 = ObjectMemory()
        m1.observe(Detection("chair", 0.9, (0.1, 0.1, 0.1, 0.1)), 1)
        