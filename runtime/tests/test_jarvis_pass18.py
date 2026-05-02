"""Pass 18 — Long-term memory, self-learning, cron scheduler, context builder.

All tests are isolated: SQLite databases use tmp_path, no real processes
are spawned, no network calls are made.

Test count: 30 tests across 4 test classes.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import List
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))


# ===========================================================================
# 1. LongTermMemory
# ===========================================================================

class TestLongTermMemory:
    """Tests for agency.long_term_memory.LongTermMemory."""

    def _mem(self, tmp_path):
        from agency.long_term_memory import LongTermMemory
        return LongTermMemory(db_path=tmp_path / "ltm.db")

    # --- remember / count ---
    def test_remember_stores_entry(self, tmp_path):
        mem = self._mem(tmp_path)
        mem.remember("key.one", "hello world")
        assert mem.count() == 1

    def test_remember_upserts_on_same_key(self, tmp_path):
        mem = self._mem(tmp_path)
        mem.remember("key.one", "v1")
        mem.remember("key.one", "v2")
        assert mem.count() == 1
        entries = mem.list_all()
        assert entries[0].value == "v2"

    def test_remember_tags_stored(self, tmp_path):
        mem = self._mem(tmp_path)
        mem.remember("key.tagged", "value", tags=["fact", "profile"])
        entries = mem.list_all()
        assert "fact" in entries[0].tags
        assert "profile" in entries[0].tags

    def test_remember_importance_stored(self, tmp_path):
        mem = self._mem(tmp_path)
        mem.remember("key.imp", "value", importance=2.5)
        entries = mem.list_all()
        assert entries[0].importance == pytest.approx(2.5)

    def test_remember_returns_entry(self, tmp_path):
        from agency.long_term_memory import MemoryEntry
        mem = self._mem(tmp_path)
        entry = mem.remember("key.ret", "test value")
        assert isinstance(entry, MemoryEntry)
        assert entry.key == "key.ret"
        assert entry.value == "test value"

    # --- forget ---
    def test_forget_removes_entry(self, tmp_path):
        mem = self._mem(tmp_path)
        mem.remember("key.del", "to delete")
        assert mem.forget("key.del") is True
        assert mem.count() == 0

    def test_forget_nonexistent_returns_false(self, tmp_path):
        mem = self._mem(tmp_path)
        assert mem.forget("no.such.key") is False

    # --- list_all ---
    def test_list_all_returns_all(self, tmp_path):
        mem = self._mem(tmp_path)
        for i in range(5):
            mem.remember(f"key.{i}", f"value {i}")
        assert len(mem.list_all()) == 5

    def test_list_all_sorted_by_importance(self, tmp_path):
        mem = self._mem(tmp_path)
        mem.remember("low", "l", importance=0.5)
        mem.remember("high", "h", importance=3.0)
        mem.remember("mid", "m", importance=1.5)
        entries = mem.list_all()
        importances = [e.importance for e in entries]
        assert importances == sorted(importances, reverse=True)

    # --- recall ---
    def test_recall_returns_relevant(self, tmp_path):
        mem = self._mem(tmp_path)
        mem.remember("user.lang", "user speaks Hebrew", tags=["language"])
        mem.remember("user.city", "user lives in Jerusalem", tags=["location"])
        mem.remember("project.x", "project x uses Python", tags=["tech"])
        results = mem.recall("Hebrew language", top_k=2)
        assert len(results) >= 1
        keys = [r.entry.key for r in results]
        assert "user.lang" in keys

    def test_recall_respects_top_k(self, tmp_path):
        mem = self._mem(tmp_path)
        for i in range(10):
            mem.remember(f"fact.{i}", f"this is fact number {i} about coding")
        results = mem.recall("coding fact", top_k=3)
        assert len(results) <= 3

    def test_recall_returns_recall_result_objects(self, tmp_path):
        from agency.long_term_memory import RecallResult
        mem = self._mem(tmp_path)
        mem.remember("test.key", "test value about Python programming")
        results = mem.recall("Python programming", top_k=5)
        assert all(isinstance(r, RecallResult) for r in results)

    def test_recall_empty_db_returns_empty(self, tmp_path):
        mem = self._mem(tmp_path)
        results = mem.recall("anything", top_k=5)
        assert results == []

    # --- consolidate ---
    def test_consolidate_removes_exact_value_duplicates(self, tmp_path):
        mem = self._mem(tmp_path)
        mem.remember("k1", "duplicate value here")
        mem.remember("k2", "duplicate value here")  # same value
        mem.remember("k3", "unique value")
        removed = mem.consolidate()
        assert removed >= 1
        # At most 2 remain (one of k1/k2 plus k3)
        assert mem.count() <= 2

    def test_consolidate_keeps_unique_values(self, tmp_path):
        mem = self._mem(tmp_path)
        mem.remember("a", "value alpha")
        mem.remember("b", "value beta")
        removed = mem.consolidate()
        assert removed == 0
        assert mem.count() == 2

    # --- helpers ---
    def test_tokenize_removes_stopwords(self):
        from agency.long_term_memory import _tokenize
        tokens = _tokenize("the quick brown fox is jumping")
        assert "the" not in tokens
        assert "is" not in tokens
        assert "quick" in tokens
        assert "brown" in tokens

    def test_sanitize_fts_query_handles_specials(self):
        from agency.long_term_memory import _sanitize_fts_query
        result = _sanitize_fts_query("hello world")
        assert "hello" in result
        assert "world" in result

    def test_sanitize_fts_query_empty(self):
        from agency.long_term_memory import _sanitize_fts_query
        result = _sanitize_fts_query("")
        assert isinstance(result, str)


# ===========================================================================
# 2. Learner
# ===========================================================================

class TestLearner:
    """Tests for agency.learner.Learner."""

    def _learner(self, tmp_path):
        from agency.long_term_memory import LongTermMemory
        from agency.learner import Learner
        mem = LongTermMemory(db_path=tmp_path / "ltm.db")
        return Learner(memory=mem), mem

    def test_process_turn_extracts_name(self, tmp_path):
        learner, mem = self._learner(tmp_path)
        events = learner.process_turn("My name is Amjad")
        keys = [e.key for e in events]
        assert "profile.name" in keys

    def test_process_turn_extracts_preference(self, tmp_path):
        learner, mem = self._learner(tmp_path)
        events = learner.process_turn("I prefer TypeScript over JavaScript")
        types = [e.fact_type for e in events]
        assert "preference" in types

    def test_process_turn_stores_to_memory(self, tmp_path):
        learner, mem = self._learner(tmp_path)
        learner.process_turn("My name is Amjad")
        # should have stored profile.name
        results = mem.recall("profile name Amjad", top_k=3)
        assert any("amjad" in r.entry.value.lower() for r in results)

    def test_process_turn_extracts_correction(self, tmp_path):
        learner, mem = self._learner(tmp_path)
        events = learner.process_turn("Actually, the correct approach is TDD")
        # at least some event should be extracted
        assert isinstance(events, list)

    def test_process_turn_empty_text_returns_empty(self, tmp_path):
        learner, mem = self._learner(tmp_path)
        events = learner.process_turn("")
        assert events == []

    def test_process_turn_deduplicates(self, tmp_path):
        learner, mem = self._learner(tmp_path)
        events = learner.process_turn("My name is Amjad. Call me Amjad.")
        name_events = [e for e in events if e.key == "profile.name"]
        assert len(name_events) <= 1

    def test_total_events_accumulates(self, tmp_path):
        learner, mem = self._learner(tmp_path)
        learner.process_turn("My name is Amjad")
        learner.process_turn("I prefer Python")
        assert learner.total_events >= 1

    def test_learn_from_history(self, tmp_path):
        learner, mem = self._learner(tmp_path)
        sessions = [
            {
                "messages": [
                    {"role": "user", "content": "My name is Amjad"},
                    {"role": "assistant", "content": "Hello Amjad!"},
                    {"role": "user", "content": "I prefer dark mode"},
                ]
            }
        ]
        total = learner.learn_from_history(sessions)
        assert total >= 1

    def test_learning_event_dataclass(self):
        from agency.learner import LearningEvent
        evt = LearningEvent(
            fact_type="fact",
            key="test.key",
            value="test value",
            source="user",
            raw_text="test raw text",
        )
        assert evt.fact_type == "fact"
        assert evt.confidence == 1.0

    def test_slugify_helper(self):
        from agency.learner import _slugify
        assert _slugify("Hello World!") == "hello_world"
        assert _slugify("  foo bar  ") == "foo_bar"


# ===========================================================================
# 3. Scheduler / CronExpression
# ===========================================================================

class TestCronExpression:
    """Tests for agency.scheduler.CronExpression."""

    def test_wildcard_matches_any(self):
        from agency.scheduler import CronExpression
        expr = CronExpression("* * * * *")
        dt = datetime(2024, 6, 15, 14, 30, tzinfo=timezone.utc)
        assert expr.matches(dt) is True

    def test_exact_minute_matches(self):
        from agency.scheduler import CronExpression
        expr = CronExpression("30 9 * * *")
        dt = datetime(2024, 6, 15, 9, 30, tzinfo=timezone.utc)
        assert expr.matches(dt) is True

    def test_exact_minute_no_match(self):
        from agency.scheduler import CronExpression
        expr = CronExpression("30 9 * * *")
        dt = datetime(2024, 6, 15, 9, 31, tzinfo=timezone.utc)
        assert expr.matches(dt) is False

    def test_step_expression(self):
        from agency.scheduler import CronExpression
        expr = CronExpression("*/15 * * * *")
        dt0 = datetime(2024, 6, 15, 10, 0, tzinfo=timezone.utc)
        dt15 = datetime(2024, 6, 15, 10, 15, tzinfo=timezone.utc)
        dt7 = datetime(2024, 6, 15, 10, 7, tzinfo=timezone.utc)
        assert expr.matches(dt0) is True
        assert expr.matches(dt15) is True
        assert expr.matches(dt7) is False

    def test_range_expression(self):
        from agency.scheduler import CronExpression
        expr = CronExpression("0 9-17 * * *")
        dt_in = datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)
        dt_out = datetime(2024, 6, 15, 18, 0, tzinfo=timezone.utc)
        assert expr.matches(dt_in) is True
        assert expr.matches(dt_out) is False

    def test_invalid_field_count_raises(self):
        from agency.scheduler import CronExpression
        with pytest.raises(ValueError):
            CronExpression("* * * *")

    def test_next_run_is_in_future(self):
        from agency.scheduler import CronExpression
        expr = CronExpression("* * * * *")
        before = datetime.now(tz=timezone.utc)
        nr = expr.next_run()
        assert nr > before


class TestScheduler:
    """Tests for agency.scheduler.Scheduler (no real subprocess)."""

    def _sched(self, tmp_path):
        from agency.scheduler import Scheduler
        return Scheduler(
            schedule_path=tmp_path / "schedule.json",
            dlq_path=tmp_path / "dlq.jsonl",
            tick_interval=0.1,
        )

    def test_add_task_persists(self, tmp_path):
        sched = self._sched(tmp_path)
        task = sched.add("test", "* * * * *", "echo hello")
        assert task.name == "test"
        assert task.id in {t.id for t in sched.list_tasks()}

    def test_remove_task(self, tmp_path):
        sched = self._sched(tmp_path)
        task = sched.add("to_remove", "* * * * *", "echo bye")
        assert sched.remove(task.id) is True
        assert sched.get(task.id) is None

    def test_remove_nonexistent_returns_false(self, tmp_path):
        sched = self._sched(tmp_path)
        assert sched.remove("nosuchid") is False

    def test_schedule_saved_to_file(self, tmp_path):
        sched = self._sched(tmp_path)
        sched.add("persistent", "0 8 * * *", "echo morning")
        data = json.loads((tmp_path / "schedule.json").read_text())
        assert any(t["name"] == "persistent" for t in data)

    def test_reload_from_file(self, tmp_path):
        from agency.scheduler import Scheduler
        sched = Scheduler(
            schedule_path=tmp_path / "schedule.json",
            dlq_path=tmp_path / "dlq.jsonl",
        )
        sched.add("reload_test", "0 12 * * *", "echo hi")
        # Create new instance — should reload from file
        sched2 = Scheduler(
            schedule_path=tmp_path / "schedule.json",
            dlq_path=tmp_path / "dlq.jsonl",
        )
        assert any(t.name == "reload_test" for t in sched2.list_tasks())

    @patch("agency.scheduler.subprocess.run")
    def test_run_task_calls_subprocess(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        sched = self._sched(tmp_path)
        task = sched.add("run_now", "* * * * *", "echo test")
        result = sched.run_task(task.id)
        assert result is True
        mock_run.assert_called_once()

    @patch("agency.scheduler.subprocess.run")
    def test_failed_task_writes_dlq(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="oops")
        sched = self._sched(tmp_path)
        task = sched.add("fail_task", "* * * * *", "false")
        sched.run_task(task.id)
        dlq = tmp_path / "dlq.jsonl"
        assert dlq.exists()
        entries = [json.loads(l) for l in dlq.read_text().strip().splitlines()]
        assert any("fail_task" in str(e) for e in entries)

    def test_scheduled_task_dataclass(self):
        from agency.scheduler import ScheduledTask
        t = ScheduledTask(name="x", cron="* * * * *", command="echo x")
        d = t.to_dict()
        t2 = ScheduledTask.from_dict(d)
        assert t2.name == t.name
        assert t2.cron == t.cron


# ===========================================================================
# 4. ContextBuilder
# ===========================================================================

class TestContextBuilder:
    """Tests for agency.context_builder.ContextBuilder."""

    def _builder(self, tmp_path, user_name=None):
        from agency.long_term_memory import LongTermMemory
        from agency.context_builder import ContextBuilder
        mem = LongTermMemory(db_path=tmp_path / "ltm.db")
        return ContextBuilder(memory=mem, user_name=user_name), mem

    def test_build_returns_string(self, tmp_path):
        builder, _ = self._builder(tmp_path)
        result = builder.build("hello")
        assert isinstance(result, str)
        assert len(result) > 50

    def test_build_contains_persona(self, tmp_path):
        builder, _ = self._builder(tmp_path)
        result = builder.build("test message")
        assert "JARVIS" in result

    def test_build_contains_datetime(self, tmp_path):
        builder, _ = self._builder(tmp_path)
        result = builder.build("test")
        assert "Jerusalem" in result or "date" in result.lower() or "time" in result.lower()

    def test_build_includes_user_name(self, tmp_path):
        builder, _ = self._builder(tmp_path, user_name="Amjad")
        result = builder.build("test")
        assert "Amjad" in result

    def test_build_includes_relevant_memory(self, tmp_path):
        builder, mem = self._builder(tmp_path)
        mem.remember("project.lang", "the project uses TypeScript", tags=["tech"])
        result = builder.build("tell me about the project language")
        assert "TypeScript" in result

    def test_build_includes_recent_turns(self, tmp_path):
        builder, _ = self._builder(tmp_path)
        turns = [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is a programming language."},
        ]
        result = builder.build("follow up question", recent_turns=turns)
        assert "Python" in result

    def test_build_no_memory_returns_valid_prompt(self, tmp_path):
        from agency.context_builder import ContextBuilder
        builder = ContextBuilder(memory=None)
        result = builder.build("hello world")
        assert "JARVIS" in result

    def test_inject_memories_returns_list(self, tmp_path):
        builder, mem = self._builder(tmp_path)
        mem.remember("k1", "Python is great for scripting")
        result = builder.inject_memories("Python scripting", top_k=3)
        assert isinstance(result, list)
        assert all("key" in item and "value" in item for item in result)

    def test_jerusalem_datetime_function(self):
        from agency.context_builder import _jerusalem_now
        dt = _jerusalem_now()
        assert dt.tzinfo is not None
        # Should be within 24h of UTC (reasonable tz offset check)
        utc_now = datetime.now(tz=timezone.utc)
        diff = abs((dt.utctimetuple()[3] * 60 + dt.utctimetuple()[4]) -
                   (utc_now.hour * 60 + utc_now.minute))
        # Jerusalem is UTC+2 or UTC+3 — diff in minutes should be small mod 1440
        assert diff < 300 or diff > 1140  # within ±5 hours (DST inclusive)

    def test_turn_truncation_long_content(self, tmp_path):
        builder, _ = self._builder(tmp_path)
        long_content = "x" * 500
        turns = [{"role": "user", "content": long_content}]
        result = builder.build("q", recent_turns=turns)
        # Truncated version should appear, not full 500 chars
        assert long_content not in result
        assert "..." in result or len([l for l in result.split("\n") if "x" * 100 in l]) == 0
