"""Integration tests for the runtime wiring of vector_memory,
supervisor, and managed_agents into the executor + tool layer.

These verify that each module isn't just present but actually called
from the right places end-to-end.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


# ----- run_shell uses the supervisor (timeout path) -----------------


def test_run_shell_uses_supervisor_timeout(tmp_path: Path, monkeypatch):
    """A long sleep with a tiny timeout should return crash_dump-style
    output via the supervisor, not the old bare 'Timed out after Ns'."""
    from agency.tools import ToolContext, _run_shell

    monkeypatch.setenv("AGENCY_TRUST_MODE", "yolo")
    monkeypatch.setenv("AGENCY_ALLOW_SHELL", "1")
    ctx = ToolContext.from_env(workdir=tmp_path)
    ctx.timeout_s = 1  # 1 second cap

    res = _run_shell(
        {"command": f"{sys.executable} -c 'import time; time.sleep(30)'"},
        ctx,
    )
    assert res.is_error
    # Supervisor's crash_message format includes these two markers:
    assert "process killed by supervisor" in res.content
    assert "timeout" in res.content


def test_run_shell_clean_exit_unchanged(tmp_path: Path, monkeypatch):
    """A normal command's output format should be the same as before
    (stdout + [exit: 0]) so existing tests still pass."""
    from agency.tools import ToolContext, _run_shell

    monkeypatch.setenv("AGENCY_TRUST_MODE", "yolo")
    monkeypatch.setenv("AGENCY_ALLOW_SHELL", "1")
    ctx = ToolContext.from_env(workdir=tmp_path)

    res = _run_shell(
        {"command": f"{sys.executable} -c 'print(\"hello\")'"},
        ctx,
    )
    assert not res.is_error
    assert "hello" in res.content
    assert "[exit: 0]" in res.content


# ----- recall_lesson tool exists and works --------------------------


def test_recall_lesson_tool_registered():
    from agency.tools import builtin_tools

    names = {t.name for t in builtin_tools()}
    assert "recall_lesson" in names


def test_recall_lesson_returns_top_match(tmp_path: Path, monkeypatch):
    """End-to-end: write a lessons.md, call recall_lesson, verify the
    most-relevant entry is returned at rank 1."""
    lessons_path = tmp_path / "lessons.md"
    lessons_path.write_text(
        "# Lessons\n\n"
        "## 2026-04-25 12:00 UTC · stripe webhook\n"
        "WORKED: signed webhook validates with timestamp tolerance\n\n"
        "## 2026-04-25 13:00 UTC · ranger\n"
        "WORKED: file manager works in tmux\n\n"
        "## 2026-04-25 14:00 UTC · trust mode\n"
        "WORKED: yolo mode lifts the workdir sandbox\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENCY_LESSONS", str(lessons_path))
    monkeypatch.setenv("AGENCY_VECTOR_DB", str(tmp_path / "vec.db"))

    from agency.tools import ToolContext, _recall_lesson

    ctx = ToolContext(workdir=tmp_path.resolve())
    res = _recall_lesson({"query": "stripe webhook signature timestamp"}, ctx)
    assert not res.is_error
    out = res.content.lower()
    # The first match block must have an `id=` line whose suffix
    # contains "stripe webhook" — that proves the top hit is the
    # stripe entry, not one of the other two.
    first_id_line = next(
        (line for line in out.splitlines() if line.startswith("--- #1")),
        None,
    )
    assert first_id_line is not None
    assert "stripe webhook" in first_id_line


def test_recall_lesson_empty_journal(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENCY_LESSONS", str(tmp_path / "lessons.md"))
    monkeypatch.setenv("AGENCY_VECTOR_DB", str(tmp_path / "vec.db"))
    from agency.tools import ToolContext, _recall_lesson
    ctx = ToolContext(workdir=tmp_path.resolve())
    res = _recall_lesson({"query": "anything"}, ctx)
    assert not res.is_error
    assert "empty" in res.content.lower()


def test_recall_lesson_rejects_empty_query(tmp_path: Path):
    from agency.tools import ToolContext, _recall_lesson
    ctx = ToolContext(workdir=tmp_path.resolve())
    res = _recall_lesson({"query": "  "}, ctx)
    assert res.is_error


# ----- managed_agents backend switch --------------------------------


def test_managed_agents_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AGENCY_BACKEND", raising=False)
    from agency import managed_agents
    assert not managed_agents.is_enabled()


@pytest.mark.parametrize("val", ["managed_agents", "managed-agents", "managed",
                                  "Managed_Agents", "MANAGED"])
def test_managed_agents_enabled_for_recognized_values(monkeypatch, val):
    monkeypatch.setenv("AGENCY_BACKEND", val)
    from agency import managed_agents
    assert managed_agents.is_enabled()


def test_managed_agents_disabled_for_unknown_value(monkeypatch):
    monkeypatch.setenv("AGENCY_BACKEND", "local")
    from agency import managed_agents
    assert not managed_agents.is_enabled()


def test_executor_routes_to_managed_when_enabled(monkeypatch, tmp_path):
    """When AGENCY_BACKEND=managed_agents is set, Executor.run() should
    skip the local loop entirely and call _run_via_managed_agents.
    We monkeypatch the backend so no real network call happens."""
    from agency.executor import Executor
    from agency.skills import Skill
    from unittest.mock import MagicMock

    monkeypatch.setenv("AGENCY_BACKEND", "managed_agents")

    # Stub the backend's run() to yield a single text event then stop.
    from agency import managed_agents as ma

    class _FakeBackend:
        def run(self, msg, session_id=None):
            yield ma.ManagedAgentEvent("text", "managed-agents replied")
            yield ma.ManagedAgentEvent("stop", "session_idle")

    monkeypatch.setattr(ma, "default_backend",
                        lambda **kw: _FakeBackend())

    # Build an Executor with stub deps.
    fake_skill = Skill(
        slug="test", name="Test", description="d", category="testing",
        color="white", emoji="🧪", vibe="v", body="You are a tester.",
        path=tmp_path / "test.md", extra={},
    )
    fake_registry = MagicMock()
    fake_registry.all = lambda: [fake_skill]
    fake_llm = MagicMock()
    fake_llm.config.model = "claude-opus-4-7"

    ex = Executor(fake_registry, fake_llm, profile=None, lessons=None)
    result = ex.run(fake_skill, "hello")

    assert "managed-agents replied" in result.text
    # Local LLM should NOT have been called.
    fake_llm.messages_create.assert_not_called()
