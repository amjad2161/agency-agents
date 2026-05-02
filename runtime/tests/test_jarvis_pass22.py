"""
test_jarvis_pass22.py — Pass 22
55+ tests for: FaceRecognizer, JarvisTelegramBot, GestureRecognizer,
               TTSEngine, JointPlanner.
Zero real hardware / API calls — all external deps mocked.
"""
from __future__ import annotations

import importlib
import math
import os
import sys
import threading
import types
from dataclasses import dataclass
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ── helpers to inject path ─────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]  # agency/
AGENCY = ROOT / "runtime" / "agency"
# Only add runtime/ to sys.path — NOT runtime/agency/, which would cause
# our own face_recognition.py to shadow the real face_recognition library.
if str(AGENCY.parent) not in sys.path:
    sys.path.insert(0, str(AGENCY.parent))


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1 — FaceRecognizer
# ═══════════════════════════════════════════════════════════════════════════════

class TestFaceMatch:
    def test_facematch_fields(self):
        from agency.face_recognition import FaceMatch
        fm = FaceMatch("alice", 0.95, (0.1, 0.2, 0.3, 0.4))
        assert fm.name == "alice"
        assert fm.confidence == pytest.approx(0.95)
        assert fm.bbox == (0.1, 0.2, 0.3, 0.4)

    def test_facematch_default_unknown(self):
        from agency.face_recognition import FaceMatch
        fm = FaceMatch("unknown", 0.0, (0, 0, 1, 1))
        assert fm.name == "unknown"
        assert fm.confidence == 0.0


class TestMockFaceRecognizer:
    def _get_mock(self):
        from agency.face_recognition import MockFaceRecognizer
        return MockFaceRecognizer()

    def test_load_known_faces_returns_zero(self, tmp_path):
        m = self._get_mock()
        assert m.load_known_faces(str(tmp_path)) == 0

    def test_recognize_frame_returns_list(self):
        m = self._get_mock()
        results = m.recognize_frame(None)
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_recognize_frame_unknown_face(self):
        from agency.face_recognition import FaceMatch
        m = self._get_mock()
        results = m.recognize_frame(None)
        assert all(isinstance(r, FaceMatch) for r in results)
        assert results[0].name == "unknown"
        assert results[0].confidence == 0.0

    def test_recognize_frame_bbox_valid(self):
        m = self._get_mock()
        result = m.recognize_frame(None)[0]
        assert len(result.bbox) == 4

    def test_identify_person_returns_unknown(self):
        m = self._get_mock()
        assert m.identify_person("fake_path.jpg") == "unknown"

    def test_identify_person_array_input(self):
        m = self._get_mock()
        assert m.identify_person([[0, 0, 0]]) == "unknown"


class TestFaceRecognizerFacade:
    def test_facade_has_backend_name(self):
        from agency.face_recognition import FaceRecognizer
        rec = FaceRecognizer()
        assert rec.backend_name in ("face_recognition", "opencv_dnn", "mock")

    def test_facade_load_known_faces(self, tmp_path):
        from agency.face_recognition import FaceRecognizer
        rec = FaceRecognizer()
        result = rec.load_known_faces(str(tmp_path))
        assert isinstance(result, int)
        assert result >= 0

    def test_facade_recognize_frame_returns_list(self):
        from agency.face_recognition import FaceRecognizer
        rec = FaceRecognizer()
        results = rec.recognize_frame(None)
        assert isinstance(results, list)

    def test_facade_identify_person_returns_str(self, tmp_path):
        from agency.face_recognition import FaceRecognizer
        fake_img = tmp_path / "face.jpg"
        fake_img.write_bytes(b"")
        rec = FaceRecognizer()
        result = rec.identify_person(str(fake_img))
        assert isinstance(result, str)

    def test_mock_backend_selected_when_no_libs(self):
        """Force mock backend by patching availability flags."""
        import agency.face_recognition as fr_mod
        with patch.object(fr_mod, "_FACE_RECOGNITION_AVAILABLE", False), \
             patch.object(fr_mod, "_OPENCV_DNN_AVAILABLE", False):
            rec = fr_mod.FaceRecognizer()
            assert rec.backend_name == "mock"

    def test_facade_recognize_frame_facematch_type(self):
        from agency.face_recognition import FaceRecognizer, FaceMatch
        rec = FaceRecognizer()
        matches = rec.recognize_frame(None)
        for m in matches:
            assert isinstance(m, FaceMatch)


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2 — JarvisTelegramBot
# ═══════════════════════════════════════════════════════════════════════════════

class TestMockTelegramBot:
    def _get(self):
        from agency.telegram_bot import MockTelegramBot
        return MockTelegramBot("MOCK_TOKEN")

    def test_start_sets_running(self):
        bot = self._get()
        bot.start()
        assert bot.is_running is True

    def test_stop_clears_running(self):
        bot = self._get()
        bot.start()
        bot.stop()
        assert bot.is_running is False

    def test_send_message_appends_log(self):
        bot = self._get()
        bot.start()
        bot.send_message(123, "שלום עולם")
        assert any("שלום עולם" in entry for entry in bot.log)

    def test_send_message_contains_chat_id(self):
        bot = self._get()
        bot.send_message(999, "test")
        assert any("999" in entry for entry in bot.log)

    def test_start_appends_start_log(self):
        bot = self._get()
        bot.start()
        assert len(bot.log) >= 1

    def test_stop_appends_stop_log(self):
        bot = self._get()
        bot.start()
        bot.stop()
        assert any("stopped" in e for e in bot.log)

    def test_log_is_copy(self):
        bot = self._get()
        log1 = bot.log
        bot.send_message(1, "x")
        log2 = bot.log
        assert len(log2) > len(log1)


class TestJarvisTelegramBotFacade:
    def test_no_token_uses_mock(self):
        import agency.telegram_bot as tb
        with patch.object(tb, "_PTB_AVAILABLE", False), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)
            bot = tb.JarvisTelegramBot(token="")
            assert bot.backend_name == "mock"

    def test_missing_token_graceful(self):
        import agency.telegram_bot as tb
        with patch.object(tb, "_PTB_AVAILABLE", True):
            # No real token → should still fall back to mock
            bot = tb.JarvisTelegramBot(token="")
            assert bot.backend_name == "mock"

    def test_send_message_mock(self):
        import agency.telegram_bot as tb
        with patch.object(tb, "_PTB_AVAILABLE", False):
            bot = tb.JarvisTelegramBot(token="")
            bot.start()
            bot.send_message(42, "hello")
            assert bot.is_running

    def test_stop_after_start(self):
        import agency.telegram_bot as tb
        with patch.object(tb, "_PTB_AVAILABLE", False):
            bot = tb.JarvisTelegramBot(token="")
            bot.start()
            bot.stop()
            assert not bot.is_running


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3 — GestureRecognizer
# ═══════════════════════════════════════════════════════════════════════════════

class TestGestureResult:
    def test_skill_slug_assigned_on_init(self):
        from agency.robotics.gesture import GestureResult, Gesture
        gr = GestureResult(Gesture.WAVE, 0.9, [])
        assert gr.skill_slug == "wave_hand"

    def test_thumbs_up_skill(self):
        from agency.robotics.gesture import GestureResult, Gesture
        gr = GestureResult(Gesture.THUMBS_UP, 0.8, [])
        assert gr.skill_slug == "stand_up"

    def test_thumbs_down_skill(self):
        from agency.robotics.gesture import GestureResult, Gesture
        gr = GestureResult(Gesture.THUMBS_DOWN, 0.8, [])
        assert gr.skill_slug == "sit_down"

    def test_point_skill(self):
        from agency.robotics.gesture import GestureResult, Gesture
        gr = GestureResult(Gesture.POINT, 0.9, [])
        assert gr.skill_slug == "reach_forward"

    def test_unknown_skill(self):
        from agency.robotics.gesture import GestureResult, Gesture
        gr = GestureResult(Gesture.UNKNOWN, 0.0, [])
        assert gr.skill_slug == "unknown"


class TestAllGestureNames:
    def test_all_eight_gestures_defined(self):
        from agency.robotics.gesture import Gesture
        names = {g.value for g in Gesture}
        expected = {"WAVE", "THUMBS_UP", "THUMBS_DOWN", "POINT", "OPEN_PALM", "FIST", "PEACE", "UNKNOWN"}
        assert names == expected

    def test_gesture_skill_map_covers_all(self):
        from agency.robotics.gesture import Gesture, GESTURE_SKILL_MAP
        for g in Gesture:
            assert g in GESTURE_SKILL_MAP or g.value in GESTURE_SKILL_MAP


class TestMockGestureRecognizer:
    def test_recognize_returns_gesture_result(self):
        from agency.robotics.gesture import MockGestureRecognizer, GestureResult
        m = MockGestureRecognizer()
        result = m.recognize(None)
        assert isinstance(result, GestureResult)

    def test_recognize_returns_unknown(self):
        from agency.robotics.gesture import MockGestureRecognizer, Gesture
        m = MockGestureRecognizer()
        result = m.recognize(None)
        assert result.gesture_name == Gesture.UNKNOWN

    def test_recognize_zero_confidence(self):
        from agency.robotics.gesture import MockGestureRecognizer
        m = MockGestureRecognizer()
        result = m.recognize(None)
        assert result.confidence == 0.0

    def test_recognize_empty_landmarks(self):
        from agency.robotics.gesture import MockGestureRecognizer
        m = MockGestureRecognizer()
        result = m.recognize(None)
        assert result.landmarks == []

    def test_camera_loop_fires_callback(self):
        from agency.robotics.gesture import MockGestureRecognizer
        m = MockGestureRecognizer()
        called = []
        m.start_camera_loop(called.append)
        assert len(called) == 1

    def test_stop_no_error(self):
        from agency.robotics.gesture import MockGestureRecognizer
        m = MockGestureRecognizer()
        m.stop()  # should not raise


class TestGestureRecognizerFacade:
    def test_backend_name_in_valid_set(self):
        from agency.robotics.gesture import GestureRecognizer
        rec = GestureRecognizer()
        assert rec.backend_name in ("mediapipe", "opencv_contour", "mock")

    def test_mock_selected_when_no_libs(self):
        import agency.robotics.gesture as gmod
        with patch.object(gmod, "_MEDIAPIPE_AVAILABLE", False), \
             patch.object(gmod, "_OPENCV_AVAILABLE", False):
            rec = gmod.GestureRecognizer()
            assert rec.backend_name == "mock"

    def test_gesture_to_skill(self):
        from agency.robotics.gesture import GestureRecognizer, Gesture
        rec = GestureRecognizer()
        assert rec.gesture_to_skill(Gesture.WAVE) == "wave_hand"
        assert rec.gesture_to_skill(Gesture.THUMBS_UP) == "stand_up"
        assert rec.gesture_to_skill(Gesture.THUMBS_DOWN) == "sit_down"
        assert rec.gesture_to_skill(Gesture.POINT) == "reach_forward"


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4 — TTSEngine
# ═══════════════════════════════════════════════════════════════════════════════

class TestHebrewDetection:
    def test_detects_hebrew_char(self):
        from agency.tts_engine import _is_hebrew
        assert _is_hebrew("שלום") is True

    def test_detects_mixed(self):
        from agency.tts_engine import _is_hebrew
        assert _is_hebrew("hello שלום") is True

    def test_no_hebrew_in_latin(self):
        from agency.tts_engine import _is_hebrew
        assert _is_hebrew("hello world") is False

    def test_empty_string(self):
        from agency.tts_engine import _is_hebrew
        assert _is_hebrew("") is False


class TestVoiceSelection:
    def test_hebrew_text_selects_avri(self):
        from agency.tts_engine import _select_voice
        lang, voice = _select_voice("שלום עולם", "he")
        assert "AvriNeural" in voice or voice == "he-IL-AvriNeural"
        assert lang == "he"

    def test_english_text_selects_aria(self):
        from agency.tts_engine import _select_voice
        lang, voice = _select_voice("Hello world", "en")
        assert "Aria" in voice or "en" in voice

    def test_hebrew_override_by_content(self):
        from agency.tts_engine import _select_voice
        lang, voice = _select_voice("שלום", "en")  # content overrides
        assert lang == "he"


class TestMockTTSBackend:
    def test_speak_no_exception(self):
        from agency.tts_engine import _MockTTSBackend
        m = _MockTTSBackend()
        m.speak("test")  # must not raise

    def test_list_voices_returns_list(self):
        from agency.tts_engine import _MockTTSBackend
        m = _MockTTSBackend()
        voices = m.list_voices()
        assert isinstance(voices, list)
        assert len(voices) >= 1


class TestTTSEngineFacade:
    def _get_mock_engine(self):
        """Force mock backend."""
        import agency.tts_engine as tmod
        with patch.object(tmod, "_EDGE_TTS_AVAILABLE", False), \
             patch.object(tmod, "_COQUI_AVAILABLE", False), \
             patch.object(tmod, "_PYTTSX3_AVAILABLE", False), \
             patch.object(tmod, "_GTTS_AVAILABLE", False):
            return tmod.TTSEngine()

    def test_mock_backend_selected(self):
        engine = self._get_mock_engine()
        assert engine.backend_name == "mock"

    def test_speak_no_raise(self):
        engine = self._get_mock_engine()
        engine.speak("שלום")  # must not raise

    def test_speak_hebrew_no_raise(self):
        engine = self._get_mock_engine()
        engine.speak("בוקר טוב JARVIS")  # must not raise

    def test_list_voices_returns_list(self):
        engine = self._get_mock_engine()
        voices = engine.list_voices()
        assert isinstance(voices, list)

    def test_speak_async_returns_thread(self):
        engine = self._get_mock_engine()
        t = engine.speak_async("test")
        assert isinstance(t, threading.Thread)
        t.join(timeout=2)

    def test_speak_async_completes(self):
        engine = self._get_mock_engine()
        t = engine.speak_async("עברית")
        t.join(timeout=5)
        assert not t.is_alive()


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5 — JointPlanner
# ═══════════════════════════════════════════════════════════════════════════════

class TestHumanoidJoints:
    def test_all_joints_present(self):
        from agency.robotics.joint_planner import HUMANOID_JOINTS
        expected = [
            "head_pan", "head_tilt",
            "left_shoulder_pitch", "left_shoulder_roll", "left_elbow",
            "right_shoulder_pitch", "right_shoulder_roll", "right_elbow",
            "left_hip_pitch", "left_hip_roll", "left_knee",
            "right_hip_pitch", "right_hip_roll", "right_knee",
            "left_ankle", "right_ankle",
        ]
        for j in expected:
            assert j in HUMANOID_JOINTS, f"Missing joint: {j}"

    def test_16_joints_minimum(self):
        from agency.robotics.joint_planner import HUMANOID_JOINTS
        assert len(HUMANOID_JOINTS) >= 16


class TestJointPlanner:
    def _planner(self):
        from agency.robotics.joint_planner import JointPlanner
        return JointPlanner()

    def test_plan_trajectory_returns_object(self):
        from agency.robotics.joint_planner import JointTrajectory
        p = self._planner()
        traj = p.plan_trajectory({}, {}, steps=10)
        assert isinstance(traj, JointTrajectory)

    def test_trajectory_correct_step_count(self):
        p = self._planner()
        traj = p.plan_trajectory({}, {}, steps=50)
        assert traj.steps == 50
        assert len(traj.waypoints) == 50

    def test_trajectory_minimum_2_steps(self):
        p = self._planner()
        traj = p.plan_trajectory({}, {}, steps=1)  # clamped to 2
        assert len(traj.waypoints) >= 2

    def test_trajectory_contains_all_joints(self):
        from agency.robotics.joint_planner import HUMANOID_JOINTS
        p = self._planner()
        traj = p.plan_trajectory({}, {}, steps=5)
        for wp in traj.waypoints:
            for j in HUMANOID_JOINTS:
                assert j in wp

    def test_linear_start_matches_first_waypoint(self):
        p = self._planner()
        start = {"head_pan": 1.0}
        goal  = {"head_pan": 2.0}
        traj = p.plan_trajectory(start, goal, steps=5)
        assert traj.waypoints[0]["head_pan"] == pytest.approx(1.0, abs=0.05)

    def test_linear_end_matches_last_waypoint(self):
        p = self._planner()
        start = {"head_tilt": 0.0}
        goal  = {"head_tilt": 1.0}
        traj = p.plan_trajectory(start, goal, steps=10)
        assert traj.waypoints[-1]["head_tilt"] == pytest.approx(1.0, abs=0.05)

    def test_midpoint_approximately_half(self):
        """With smooth-step, midpoint is exactly 0.5."""
        p = self._planner()
        start = {"left_elbow": 0.0}
        goal  = {"left_elbow": 2.0}
        traj = p.plan_trajectory(start, goal, steps=3)
        # index 1 of 3 → t=0.5 → smooth_step(0.5)=0.5 → value=1.0
        assert traj.waypoints[1]["left_elbow"] == pytest.approx(1.0, abs=0.01)

    def test_duration_stored(self):
        p = self._planner()
        traj = p.plan_trajectory({}, {}, steps=5, duration_s=3.5)
        assert traj.duration_s == pytest.approx(3.5)

    def test_joints_list_in_trajectory(self):
        from agency.robotics.joint_planner import HUMANOID_JOINTS
        p = self._planner()
        traj = p.plan_trajectory({}, {}, steps=5)
        assert set(traj.joints) == set(HUMANOID_JOINTS)

    def test_zero_pose_all_zero(self):
        p = self._planner()
        pose = p.zero_pose()
        assert all(v == 0.0 for v in pose.values())

    def test_stand_pose_knees_nonzero(self):
        p = self._planner()
        pose = p.stand_pose()
        assert pose["left_knee"] > 0.0
        assert pose["right_knee"] > 0.0

    def test_execute_trajectory_calls_bridge(self):
        p = self._planner()
        traj = p.plan_trajectory({}, {}, steps=3, duration_s=0.0)
        bridge = MagicMock()
        p.execute_trajectory(traj, bridge, blocking=False)
        assert bridge.send_joint_command.call_count == 3

    def test_execute_trajectory_empty_traj(self):
        from agency.robotics.joint_planner import JointTrajectory
        p = self._planner()
        traj = JointTrajectory(joints=[], waypoints=[], duration_s=0.0)
        bridge = MagicMock()
        p.execute_trajectory(traj, bridge, blocking=False)
        bridge.send_joint_command.assert_not_called()

    def test_execute_trajectory_bridge_error_no_crash(self):
        p = self._planner()
        traj = p.plan_trajectory({}, {}, steps=3, duration_s=0.0)
        bridge = MagicMock()
        bridge.send_joint_command.side_effect = RuntimeError("sim error")
        # Should not propagate
        p.execute_trajectory(traj, bridge, blocking=False)
