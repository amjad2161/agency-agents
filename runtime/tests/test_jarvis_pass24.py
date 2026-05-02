"""
test_jarvis_pass24.py — JARVIS Pass 24
65+ tests covering:
  DecisionEngine, APIGateway, HotReloader, TaskExecutor,
  ContextManager, WorldModel
All tests run without real hardware/network/API.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

# Ensure repo root on path
sys.path.insert(0, str(Path(__file__).parents[2]))


# ===========================================================================
# 1.  DecisionEngine
# ===========================================================================

class TestDecisionDataclass:
    def test_decision_fields(self):
        from runtime.agency.decision_engine import Decision
        d = Decision(action="llm_fallback", confidence=0.5,
                     reasoning="test", fallback="llm")
        assert d.action == "llm_fallback"
        assert d.confidence == 0.5
        assert d.reasoning == "test"
        assert d.fallback == "llm"
        assert d.clarification_prompt == ""

    def test_decision_to_dict(self):
        from runtime.agency.decision_engine import Decision
        d = Decision("robot_brain", 0.9, "reason", "llm")
        dct = d.to_dict()
        assert dct["action"] == "robot_brain"
        assert "confidence" in dct
        assert "reasoning" in dct
        assert "fallback" in dct


class TestDecisionEngineRouting:
    @pytest.fixture
    def engine(self):
        from runtime.agency.decision_engine import DecisionEngine
        return DecisionEngine()

    def test_robot_intent_routes_to_robot_brain(self, engine):
        d = engine.decide({"intent": "robot_command", "confidence": 0.95})
        assert d.action == "robot_brain"

    def test_skill_intent_routes_to_skill(self, engine):
        d = engine.decide({"intent": "skill_request", "confidence": 0.95})
        assert d.action == "skill"

    def test_memory_store_routes_to_memory(self, engine):
        d = engine.decide({"intent": "memory_store", "confidence": 0.95})
        assert d.action == "memory_store"

    def test_unknown_intent_routes_to_llm(self, engine):
        d = engine.decide({"intent": "totally_unknown", "confidence": 0.95})
        assert d.action == "llm_fallback"

    def test_navigate_is_robot_intent(self, engine):
        d = engine.decide({"intent": "navigate", "confidence": 0.9})
        assert d.action == "robot_brain"

    def test_remember_is_memory_intent(self, engine):
        d = engine.decide({"intent": "remember", "confidence": 0.9})
        assert d.action == "memory_store"

    def test_automation_is_skill_intent(self, engine):
        d = engine.decide({"intent": "automation", "confidence": 0.9})
        assert d.action == "skill"

    def test_unavailable_skill_falls_back_to_llm(self):
        from runtime.agency.decision_engine import DecisionEngine
        engine = DecisionEngine(available_skills=["web_search"])
        d = engine.decide(
            {"intent": "skill_request", "skill_name": "nonexistent_skill", "confidence": 0.95}
        )
        assert d.action == "llm_fallback"

    def test_available_skill_routes_correctly(self):
        from runtime.agency.decision_engine import DecisionEngine
        engine = DecisionEngine(available_skills=["web_search"])
        d = engine.decide(
            {"intent": "skill_request", "skill_name": "web_search", "confidence": 0.95}
        )
        assert d.action == "skill"


class TestDecisionEngineConfidenceThresholds:
    @pytest.fixture
    def engine(self):
        from runtime.agency.decision_engine import DecisionEngine
        return DecisionEngine()

    def test_high_confidence_no_clarification(self, engine):
        d = engine.decide({"intent": "robot_command", "confidence": 0.95})
        assert d.confidence >= 0.8
        assert d.clarification_prompt == ""

    def test_mid_confidence_has_hebrew_clarification(self, engine):
        d = engine.decide({"intent": "robot_command", "confidence": 0.7})
        assert 0.5 <= d.confidence < 0.8
        assert d.clarification_prompt != ""
        # Should be Hebrew text
        assert any(0x0590 <= ord(c) <= 0x05FF for c in d.clarification_prompt)

    def test_low_confidence_forces_llm_fallback(self, engine):
        d = engine.decide({"intent": "robot_command", "confidence": 0.3})
        assert d.action == "llm_fallback"
        assert d.clarification_prompt != ""

    def test_confidence_clamped_to_zero(self, engine):
        d = engine.decide({"intent": "unknown", "confidence": -5.0})
        assert d.confidence == 0.0
        assert d.action == "llm_fallback"

    def test_confidence_clamped_to_one(self, engine):
        d = engine.decide({"intent": "robot_command", "confidence": 999.0})
        assert d.confidence == 1.0

    def test_nlu_result_used_when_provided(self, engine):
        from runtime.agency.decision_engine import NLUResult
        nlu = NLUResult(intent="navigate", confidence=0.95, entities={}, lang="he")
        d = engine.decide({}, nlu=nlu)
        assert d.action == "robot_brain"

    def test_emotion_high_arousal_reduces_confidence(self, engine):
        from runtime.agency.decision_engine import EmotionState
        emotion = EmotionState(label="angry", valence=-0.5, arousal=0.9)
        d_no_emotion = engine.decide({"intent": "robot_command", "confidence": 0.82})
        d_with_emotion = engine.decide({"intent": "robot_command", "confidence": 0.82}, emotion=emotion)
        assert d_with_emotion.confidence <= d_no_emotion.confidence


class TestMockDecisionEngine:
    def test_always_returns_llm_fallback(self):
        from runtime.agency.decision_engine import MockDecisionEngine
        m = MockDecisionEngine()
        d = m.decide({"intent": "robot_command", "confidence": 0.99})
        assert d.action == "llm_fallback"
        assert d.confidence == 0.5
        assert d.reasoning == "mock"

    def test_mock_available_skills_empty(self):
        from runtime.agency.decision_engine import MockDecisionEngine
        assert MockDecisionEngine.available_skills == []


# ===========================================================================
# 2.  APIGateway
# ===========================================================================

class TestAPIGatewayBasic:
    @pytest.fixture
    def gw(self):
        from runtime.agency.api_gateway import APIGateway
        from runtime.agency.decision_engine import MockDecisionEngine
        return APIGateway(decision_engine=MockDecisionEngine())

    def test_process_returns_gateway_response(self, gw):
        from runtime.agency.api_gateway import GatewayResponse
        resp = gw.process("שלום")
        assert isinstance(resp, GatewayResponse)

    def test_response_text_is_string(self, gw):
        resp = gw.process("שלום")
        assert isinstance(resp.text, str)
        assert len(resp.text) > 0

    def test_action_taken_is_string(self, gw):
        resp = gw.process("שלום")
        assert isinstance(resp.action_taken, str)

    def test_latency_ms_positive(self, gw):
        resp = gw.process("בדיקה")
        assert resp.latency_ms > 0

    def test_emotion_is_string(self, gw):
        resp = gw.process("שמחה")
        assert isinstance(resp.emotion, str)

    def test_sources_is_list(self, gw):
        resp = gw.process("מה השעה")
        assert isinstance(resp.sources, list)

    def test_skill_used_is_string(self, gw):
        resp = gw.process("הפעל כלי")
        assert isinstance(resp.skill_used, str)

    def test_call_id_present(self, gw):
        resp = gw.process("ping")
        assert resp.call_id and len(resp.call_id) > 0

    def test_to_dict_has_all_keys(self, gw):
        resp = gw.process("בדיקה")
        d = resp.to_dict()
        for key in ("call_id", "text", "action_taken", "skill_used",
                    "emotion", "sources", "latency_ms"):
            assert key in d

    def test_context_passed_through(self, gw):
        resp = gw.process("שלום", context={"user_id": "test_user"})
        assert isinstance(resp, object)  # no crash

    def test_empty_text_handled(self, gw):
        resp = gw.process("")
        assert isinstance(resp.text, str)


class TestAPIGatewayAsync:
    def test_process_async_returns_response(self):
        from runtime.agency.api_gateway import APIGateway
        from runtime.agency.decision_engine import MockDecisionEngine
        gw = APIGateway(decision_engine=MockDecisionEngine())

        async def run():
            return await gw.process_async("שלום אסינכרוני")

        resp = asyncio.run(run())
        assert resp.latency_ms > 0

    def test_concurrent_async_calls_safe(self):
        from runtime.agency.api_gateway import APIGateway
        from runtime.agency.decision_engine import MockDecisionEngine
        gw = APIGateway(decision_engine=MockDecisionEngine())

        async def run():
            tasks = [gw.process_async(f"msg {i}") for i in range(5)]
            return await asyncio.gather(*tasks)

        results = asyncio.run(run())
        assert len(results) == 5
        assert all(r.latency_ms > 0 for r in results)

    def test_thread_safe_sync(self):
        from runtime.agency.api_gateway import APIGateway
        from runtime.agency.decision_engine import MockDecisionEngine
        gw = APIGateway(decision_engine=MockDecisionEngine())
        responses = []
        errors = []

        def call():
            try:
                r = gw.process("thread test")
                responses.append(r)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=call) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0
        assert len(responses) == 8


# ===========================================================================
# 3.  HotReloader
# ===========================================================================

class TestHotReloaderMock:
    def test_mock_watcher_no_op(self):
        from runtime.agency.hot_reload import MockWatcher
        mw = MockWatcher(["some/path"], lambda p: None)
        mw.start()  # should not raise
        mw.stop()   # should not raise

    def test_hotreloader_with_mock_starts_and_stops(self):
        from runtime.agency.hot_reload import HotReloader
        hr = HotReloader(use_mock=True)
        hr.watch(["runtime/agency"], lambda p: None)
        hr.stop()

    def test_stop_idempotent(self):
        from runtime.agency.hot_reload import HotReloader
        hr = HotReloader(use_mock=True)
        hr.watch(["runtime/agency"], lambda p: None)
        hr.stop()
        hr.stop()  # second call must not raise

    def test_stop_without_watch_is_safe(self):
        from runtime.agency.hot_reload import HotReloader
        hr = HotReloader(use_mock=True)
        hr.stop()  # never watched; should be safe

    def test_reload_module_known_module(self):
        from runtime.agency.hot_reload import HotReloader
        hr = HotReloader(use_mock=True)
        # json is a stdlib module guaranteed to exist
        result = hr.reload_module("json")
        assert result is True

    def test_reload_module_nonexistent_returns_false(self):
        from runtime.agency.hot_reload import HotReloader
        hr = HotReloader(use_mock=True)
        result = hr.reload_module("nonexistent_module_xyz_99")
        assert result is False

    def test_watch_replaces_existing_watcher(self):
        from runtime.agency.hot_reload import HotReloader
        hr = HotReloader(use_mock=True)
        hr.watch(["path_a"], lambda p: None)
        hr.watch(["path_b"], lambda p: None)  # must not raise
        hr.stop()

    def test_path_to_module_unknown_path(self):
        from runtime.agency.hot_reload import HotReloader
        result = HotReloader._path_to_module("/totally/unknown/path/foo.py")
        assert isinstance(result, str)  # may be empty string, that's fine


# ===========================================================================
# 4.  TaskExecutor
# ===========================================================================

class TestMockTaskExecutor:
    def test_execute_returns_task_result(self):
        from runtime.agency.robotics.task_executor import MockTaskExecutor, make_task
        ex = MockTaskExecutor()
        task = make_task("move forward")
        result = ex.execute(task)
        assert result.success is True
        assert result.task_id == task.task_id

    def test_queue_task_returns_id(self):
        from runtime.agency.robotics.task_executor import MockTaskExecutor, make_task
        ex = MockTaskExecutor()
        task = make_task("turn left")
        tid = ex.queue_task(task)
        assert tid == task.task_id

    def test_cancel_current_no_op(self):
        from runtime.agency.robotics.task_executor import MockTaskExecutor
        ex = MockTaskExecutor()
        ex.cancel_current()  # must not raise

    def test_get_status_returns_idle(self):
        from runtime.agency.robotics.task_executor import MockTaskExecutor, ExecutorStatus
        ex = MockTaskExecutor()
        assert ex.get_status() == ExecutorStatus.IDLE


class TestRealTaskExecutor:
    def test_execute_simple_task(self):
        from runtime.agency.robotics.task_executor import TaskExecutor, make_task
        ex = TaskExecutor()
        task = make_task("test step", steps=["do_nothing"])
        result = ex.execute(task)
        assert result.task_id == task.task_id
        assert isinstance(result.success, bool)
        assert result.duration_s >= 0

    def test_cancel_on_idle_does_not_raise(self):
        from runtime.agency.robotics.task_executor import TaskExecutor
        ex = TaskExecutor()
        ex.cancel_current()  # IDLE — must not raise

    def test_queue_task_adds_to_heap(self):
        from runtime.agency.robotics.task_executor import TaskExecutor, make_task
        ex = TaskExecutor()
        t1 = make_task("low priority", priority=5)
        t2 = make_task("high priority", priority=1)
        ex.queue_task(t1)
        ex.queue_task(t2)
        # Just confirm no crash; heap ordering is internal
        time.sleep(0.2)

    def test_priority_ordering_high_before_low(self):
        from runtime.agency.robotics.task_executor import RobotTask
        t_high = RobotTask("h", "high", 1, [], 5.0)
        t_low  = RobotTask("l", "low",  5, [], 5.0)
        assert t_high < t_low  # priority 1 < priority 5

    def test_task_result_fields(self):
        from runtime.agency.robotics.task_executor import TaskResult
        r = TaskResult("abc", True, 3, "", 0.5)
        assert r.task_id == "abc"
        assert r.success is True
        assert r.steps_completed == 3
        assert r.duration_s == 0.5

    def test_make_task_generates_id(self):
        from runtime.agency.robotics.task_executor import make_task
        t = make_task("go forward")
        assert t.task_id != ""
        assert t.description == "go forward"
        assert t.priority == 3  # default

    def test_get_status_initial_idle(self):
        from runtime.agency.robotics.task_executor import TaskExecutor, ExecutorStatus
        ex = TaskExecutor()
        assert ex.get_status() == ExecutorStatus.IDLE


# ===========================================================================
# 5.  ContextManager
# ===========================================================================

class TestContextManagerBasic:
    @pytest.fixture(autouse=True)
    def fresh_ctx(self):
        from runtime.agency.context_manager import ContextManager
        ctx = ContextManager()
        ctx.reset()
        yield ctx
        ctx.reset()

    def test_push_and_get(self, fresh_ctx):
        fresh_ctx.push("user_id", "amjad")
        assert fresh_ctx.get("user_id") == "amjad"

    def test_get_missing_returns_default(self, fresh_ctx):
        assert fresh_ctx.get("nonexistent", "default_val") == "default_val"

    def test_pop_removes_key(self, fresh_ctx):
        fresh_ctx.push("emotion", "happy")
        val = fresh_ctx.pop("emotion")
        assert val == "happy"
        assert fresh_ctx.get("emotion") is None

    def test_pop_missing_returns_none(self, fresh_ctx):
        assert fresh_ctx.pop("totally_missing") is None

    def test_push_overwrites(self, fresh_ctx):
        fresh_ctx.push("x", 1)
        fresh_ctx.push("x", 2)
        assert fresh_ctx.get("x") == 2

    def test_snapshot_is_deep_copy(self, fresh_ctx):
        fresh_ctx.push("data", [1, 2, 3])
        snap = fresh_ctx.snapshot()
        snap["data"].append(99)
        assert fresh_ctx.get("data") == [1, 2, 3]

    def test_restore_replaces_frame(self, fresh_ctx):
        fresh_ctx.push("a", 1)
        snap = fresh_ctx.snapshot()
        fresh_ctx.push("b", 2)
        fresh_ctx.restore(snap)
        assert fresh_ctx.get("b") is None
        assert fresh_ctx.get("a") == 1

    def test_clear_empties_frame(self, fresh_ctx):
        fresh_ctx.push("k", "v")
        fresh_ctx.clear()
        assert fresh_ctx.get("k") is None

    def test_all_returns_dict(self, fresh_ctx):
        fresh_ctx.push("x", 10)
        result = fresh_ctx.all()
        assert isinstance(result, dict)
        assert result["x"] == 10


class TestContextManagerScope:
    @pytest.fixture(autouse=True)
    def fresh_ctx(self):
        from runtime.agency.context_manager import ContextManager
        ctx = ContextManager()
        ctx.reset()
        yield ctx
        ctx.reset()

    def test_scope_sets_values_inside(self, fresh_ctx):
        with fresh_ctx.scope(active_skill="web_search"):
            assert fresh_ctx.get("active_skill") == "web_search"

    def test_scope_restores_after_exit(self, fresh_ctx):
        fresh_ctx.push("active_skill", "old")
        with fresh_ctx.scope(active_skill="new"):
            pass
        assert fresh_ctx.get("active_skill") == "old"

    def test_scope_restores_on_exception(self, fresh_ctx):
        fresh_ctx.push("key", "before")
        try:
            with fresh_ctx.scope(key="inside"):
                raise ValueError("boom")
        except ValueError:
            pass
        assert fresh_ctx.get("key") == "before"

    def test_scope_auto_increments_turn_number(self, fresh_ctx):
        with fresh_ctx.scope(active_skill="s1"):
            t1 = fresh_ctx.get("turn_number")
        with fresh_ctx.scope(active_skill="s2"):
            t2 = fresh_ctx.get("turn_number")
        assert t2 > t1

    def test_scope_explicit_turn_number(self, fresh_ctx):
        with fresh_ctx.scope(turn_number=42):
            assert fresh_ctx.get("turn_number") == 42

    def test_initial_frame_auto_fields(self, fresh_ctx):
        fresh_ctx.push("user_id", "test")
        all_ctx = fresh_ctx.all()
        assert "session_id" in all_ctx
        assert "user_id"    in all_ctx
        assert "turn_number" in all_ctx
        assert "emotion"    in all_ctx
        assert "active_skill" in all_ctx
        assert "robot_mode" in all_ctx

    def test_thread_isolation(self, fresh_ctx):
        results = {}

        def worker(name, val):
            from runtime.agency.context_manager import ContextManager
            ctx = ContextManager()
            ctx.reset()
            ctx.push("user_id", val)
            time.sleep(0.05)
            results[name] = ctx.get("user_id")

        t1 = threading.Thread(target=worker, args=("a", "alice"))
        t2 = threading.Thread(target=worker, args=("b", "bob"))
        t1.start(); t2.start()
        t1.join(); t2.join()

        # Each thread has its own local context
        assert results["a"] == "alice"
        assert results["b"] == "bob"


# ===========================================================================
# 6.  WorldModel
# ===========================================================================

class TestMockWorldModel:
    @pytest.fixture
    def wm(self):
        from runtime.agency.robotics.world_model import MockWorldModel
        return MockWorldModel()

    def test_empty_on_init(self, wm):
        assert wm.get_objects() == []

    def test_update_adds_object(self, wm):
        from runtime.agency.robotics.world_model import Detection
        d = Detection("chair", 1.0, 2.0, 0.0, 1.5, 0.9)
        wm.update(d)
        objects = wm.get_objects()
        assert len(objects) == 1
        assert objects[0].label == "chair"

    def test_get_nearest_returns_object(self, wm):
        from runtime.agency.robotics.world_model import Detection
        wm.update(Detection("table", 0.5, 0.5, 0.0, 0.7, 0.95))
        obj = wm.get_nearest("table")
        assert obj is not None
        assert obj.label == "table"

    def test_get_nearest_missing_returns_none(self, wm):
        assert wm.get_nearest("nonexistent") is None

    def test_to_dict_structure(self, wm):
        from runtime.agency.robotics.world_model import Detection
        wm.update(Detection("lamp", 1.0, 1.0, 0.0, 1.2, 0.8))
        d = wm.to_dict()
        assert "lamp" in d
        assert "x" in d["lamp"]
        assert "y" in d["lamp"]
        assert "label" in d["lamp"]

    def test_stop_is_noop(self, wm):
        wm.stop()  # must not raise


class TestRealWorldModel:
    @pytest.fixture
    def wm(self, tmp_path):
        from runtime.agency.robotics.world_model import WorldModel
        wm = WorldModel(decay_s=5.0, persist_path=tmp_path / "world.json")
        yield wm
        wm.stop()

    def test_update_and_get(self, wm):
        from runtime.agency.robotics.world_model import Detection
        wm.update(Detection("box", 1.0, 2.0, 0.5, 2.2, 0.88))
        objects = wm.get_objects()
        assert any(o.label == "box" for o in objects)

    def test_get_nearest_found(self, wm):
        from runtime.agency.robotics.world_model import Detection
        wm.update(Detection("door", 3.0, 0.0, 0.0, 3.0, 1.0))
        obj = wm.get_nearest("door")
        assert obj is not None
        assert obj.distance_m == pytest.approx(3.0)

    def test_decay_removes_old_objects(self, tmp_path):
        from runtime.agency.robotics.world_model import WorldModel, Detection, WorldObject
        import time
        wm = WorldModel(decay_s=0.1, persist_path=tmp_path / "decay_world.json")
        # Manually insert an old object
        old_obj = WorldObject("old_chair", 1.0, 1.0, 0.0, 1.0, 0.9,
                              last_update=time.time() - 1.0)  # 1 second old > 0.1 decay
        wm._objects["old_chair"] = old_obj
        # Trigger decay via get_objects
        objects = wm.get_objects()
        assert not any(o.label == "old_chair" for o in objects)
        wm.stop()

    def test_fresh_object_survives_decay(self, wm):
        from runtime.agency.robotics.world_model import Detection
        wm.update(Detection("fresh", 0.0, 0.0, 0.0, 0.1, 1.0))
        time.sleep(0.05)
        objects = wm.get_objects()
        assert any(o.label == "fresh" for o in objects)

    def test_world_object_to_dict(self):
        from runtime.agency.robotics.world_model import WorldObject
        obj = WorldObject("cup", 0.1, 0.2, 0.3, 0.4, 0.99, last_update=1000.0)
        d = obj.to_dict()
        assert d["label"] == "cup"
        assert d["x"] == pytest.approx(0.1)
        assert d["distance_m"] == pytest.approx(0.4)

    def test_world_object_from_dict(self):
        from runtime.agency.robotics.world_model import WorldObject
        d = {"label": "pen", "x": 0.0, "y": 0.0, "z": 0.0,
             "distance_m": 0.5, "confidence": 0.7, "last_update": 1234.5}
        obj = WorldObject.from_dict(d)
        assert obj.label == "pen"
        assert obj.last_update == pytest.approx(1234.5)

    def test_multiple_objects_tracked(self, wm):
        from runtime.agency.robotics.world_model import Detection
        wm.update(Detection("a", 0.0, 0.0, 0.0, 1.0, 1.0))
        wm.update(Detection("b", 1.0, 0.0, 0.0, 1.5, 0.8))
        wm.update(Detection("c", 2.0, 0.0, 0.0, 2.0, 0.6))
        assert len(wm.get_objects()) == 3

    def test_update_overwrites_same_label(self, wm):
        from runtime.agency.robotics.world_model import Detection
        wm.update(Detection("obj", 1.0, 0.0, 0.0, 1.0, 0.5))
        wm.update(Detection("obj", 2.0, 0.0, 0.0, 2.0, 0.9))
        obj = wm.get_nearest("obj")
        assert obj.x == pytest.approx(2.0)
        assert obj.confidence == pytest.approx(0.9)
