"""Pass 6: Security, edge cases, robustness, production-readiness tests.

Covers:
- Error handling (file I/O failures, corrupt data, fallback paths)
- Routing edge cases (empty, very long, non-ASCII, Hebrew-only)
- Security: shell injection vectors absent
- Soul filter edge cases
- Planner brain-failure fallback now logs (not silently swallows)
- knowledge_expansion warn-on-failure paths
- SelfLearnerEngine malformed snapshot handling
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_agency_logger(monkeypatch):
    """Ensure the 'agency' logger is in a clean state before every test.

    Other test modules call agency.logging.configure() which sets
    propagate=False and attaches a StreamHandler.  That breaks caplog
    (which relies on propagation to the root logger).  Reset to a
    pristine state and restore it after the test.

    Additionally, patch agency.logging.configure (and agency.cli.configure_logging)
    so that any call during this test is forced back to propagate=True immediately.
    This guards against pollution from CliRunner-based tests in earlier modules.
    """
    import agency.logging as alog

    log = logging.getLogger("agency")
    original_propagate = log.propagate
    original_level = log.level
    original_handlers = list(log.handlers)

    log.propagate = True
    log.setLevel(logging.DEBUG)
    for h in list(log.handlers):
        log.removeHandler(h)

    _orig_configure = alog.configure

    def _safe_configure(*args, **kwargs):
        result = _orig_configure(*args, **kwargs)
        log.propagate = True
        return result

    monkeypatch.setattr(alog, "configure", _safe_configure)
    try:
        import agency.cli
        monkeypatch.setattr(agency.cli, "configure_logging", _safe_configure)
    except (ImportError, AttributeError):
        pass

    yield

    # Restore
    log.propagate = original_propagate
    log.setLevel(original_level)
    for h in list(log.handlers):
        log.removeHandler(h)
    for h in original_handlers:
        log.addHandler(h)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SKILL_DEFAULTS = dict(color="#fff", emoji="🤖", vibe="blunt", body="You help.")


def _make_skill(slug: str, name: str, description: str, category: str = "engineering"):
    from agency.skills import Skill

    return Skill(
        slug=slug,
        name=name,
        description=description,
        category=category,
        path=Path(f"/tmp/{slug}.md"),
        **_SKILL_DEFAULTS,
    )


def _make_registry(*skills):
    from agency.skills import SkillRegistry

    return SkillRegistry(list(skills))


def _two_skill_registry():
    return _make_registry(
        _make_skill("jarvis-coder", "Coder", "Write Python code"),
        _make_skill("jarvis-analyst", "Analyst", "Data analysis", category="data"),
    )


# ---------------------------------------------------------------------------
# 1. Planner brain-failure now logs
# ---------------------------------------------------------------------------


class TestPlannerBrainFailureLogs:
    """When SupremeJarvisBrain raises, Planner logs a warning and falls back."""

    def test_brain_exception_logs_warning(self, caplog):
        from agency.planner import Planner

        reg = _two_skill_registry()
        planner = Planner(reg)

        with patch("agency.planner.SupremeJarvisBrain") as mock_brain_cls:
            mock_brain_cls.return_value.top_k.side_effect = RuntimeError("boom")
            with caplog.at_level(logging.WARNING):
                result = planner.plan("write some Python code")

        assert any(
            "brain" in r.message.lower() or "boom" in r.message
            for r in caplog.records
        ), "Expected warning log when brain raises"
        assert result.skill is not None

    def test_brain_exception_still_returns_skill(self):
        from agency.planner import Planner

        reg = _two_skill_registry()
        planner = Planner(reg)

        with patch("agency.planner.SupremeJarvisBrain") as mock_brain_cls:
            mock_brain_cls.return_value.top_k.side_effect = ValueError("bad")
            result = planner.plan("data analysis task")

        assert result.skill is not None


# ---------------------------------------------------------------------------
# 2. Routing edge cases
# ---------------------------------------------------------------------------


class TestRoutingEdgeCases:
    def test_empty_string_routes_without_crash(self):
        from agency.planner import Planner

        result = Planner(_two_skill_registry()).plan("")
        assert result.skill is not None

    def test_very_long_string_routes_without_crash(self):
        from agency.planner import Planner

        long_req = "write python code " * 500
        result = Planner(_two_skill_registry()).plan(long_req)
        assert result.skill is not None

    def test_hebrew_only_routes_without_crash(self):
        from agency.planner import Planner

        result = Planner(_two_skill_registry()).plan("כתוב קוד פייתון")
        assert result.skill is not None

    def test_non_ascii_unicode_routes_without_crash(self):
        from agency.planner import Planner

        result = Planner(_two_skill_registry()).plan(
            "сделай анализ данных 数据分析 تحليل البيانات"
        )
        assert result.skill is not None

    def test_only_whitespace_routes_without_crash(self):
        from agency.planner import Planner

        result = Planner(_two_skill_registry()).plan("     \t\n  ")
        assert result.skill is not None

    def test_special_chars_routes_without_crash(self):
        from agency.planner import Planner

        result = Planner(_two_skill_registry()).plan("!@#$%^&*()[]{}|\\;<>?,./`~")
        assert result.skill is not None

    def test_control_chars_in_request_routes_without_crash(self):
        from agency.planner import Planner

        # control chars (BEL, TAB, NUL via chr) should not crash the tokeniser
        req = "write" + chr(0) + "code" + chr(7) + "please"
        result = Planner(_two_skill_registry()).plan(req)
        assert result.skill is not None


# ---------------------------------------------------------------------------
# 3. Soul filter edge cases
# ---------------------------------------------------------------------------


class TestSoulFilterEdgeCases:
    def test_empty_string_does_not_crash(self):
        from agency.jarvis_soul import filter_response

        result = filter_response("")
        assert isinstance(result, str)

    def test_unicode_text_preserved(self):
        from agency.jarvis_soul import filter_response

        text = "ניתוח נתונים — analysis complete. Δ ≠ ∞"
        result = filter_response(text)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_clean_text_passes_through(self):
        from agency.jarvis_soul import filter_response

        clean = "Query executed. 3 rows returned."
        result = filter_response(clean)
        assert "Query executed" in result or "3 rows" in result

    def test_has_forbidden_phrase_on_empty(self):
        from agency.jarvis_soul import has_forbidden_phrase

        assert has_forbidden_phrase("") is False

    def test_has_forbidden_phrase_returns_true_for_sycophancy(self):
        from agency.jarvis_soul import has_forbidden_phrase

        result = has_forbidden_phrase("Certainly! I'd be happy to help you with that!")
        assert result is True

    def test_has_forbidden_phrase_returns_bool(self):
        from agency.jarvis_soul import has_forbidden_phrase

        assert isinstance(has_forbidden_phrase("normal text"), bool)

    def test_filter_does_not_raise_on_very_long_input(self):
        from agency.jarvis_soul import filter_response

        big = "analysis result: " * 2000
        result = filter_response(big)
        assert isinstance(result, str)

    def test_filter_hebrew_only_input(self):
        from agency.jarvis_soul import filter_response

        result = filter_response("הנה הניתוח שלך: נתוני מכירות Q1")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# 4. Security — shell injection vectors
# ---------------------------------------------------------------------------


class TestShellSecurity:
    def test_shell_disabled_by_default(self, tmp_path, monkeypatch):
        """ToolContext.allow_shell is False when AGENCY_ALLOW_SHELL is unset."""
        from agency.tools import ToolContext

        monkeypatch.delenv("AGENCY_ALLOW_SHELL", raising=False)
        monkeypatch.delenv("AGENCY_TRUST_MODE", raising=False)
        monkeypatch.setenv("AGENCY_TRUST_CONF", str(tmp_path / "absent.conf"))

        ctx = ToolContext.from_env(workdir=tmp_path)
        assert ctx.allow_shell is False

    def test_run_shell_returns_error_when_disabled(self, tmp_path):
        """_run_shell returns ToolResult.is_error=True when allow_shell=False."""
        from agency.tools import ToolContext, _run_shell

        ctx = ToolContext(workdir=tmp_path, allow_shell=False)
        result = _run_shell({"command": "echo hi"}, ctx)
        assert result.is_error is True

    def test_run_shell_uses_list_not_string(self, tmp_path, monkeypatch):
        """Verify supervisor is called with a list (no shell=True expansion)."""
        from agency.supervisor import SupervisedResult
        from agency.tools import ToolContext, _run_shell

        monkeypatch.setenv("AGENCY_ALLOW_SHELL", "1")
        ctx = ToolContext(workdir=tmp_path, allow_shell=True, shell_allowlist=("echo",))

        captured: dict = {}

        def fake_run_supervised(args, **kwargs):
            captured["args"] = args
            captured["shell"] = kwargs.get("shell", False)
            return SupervisedResult(returncode=0, stdout="hi\n", stderr="", elapsed_s=0.01)

        with patch("agency.supervisor.run_supervised", fake_run_supervised):
            _run_shell({"command": "echo hi"}, ctx)

        assert isinstance(captured.get("args"), list), "args must be a list"
        assert captured.get("shell") is False, "shell must be False"

    def test_empty_command_returns_error(self, tmp_path):
        from agency.tools import ToolContext, _run_shell

        ctx = ToolContext(workdir=tmp_path, allow_shell=True)
        result = _run_shell({"command": ""}, ctx)
        assert result.is_error is True

    def test_whitespace_command_returns_error(self, tmp_path):
        from agency.tools import ToolContext, _run_shell

        ctx = ToolContext(workdir=tmp_path, allow_shell=True)
        result = _run_shell({"command": "   \t  "}, ctx)
        assert result.is_error is True

    def test_nonexistent_executable_returns_error(self, tmp_path, monkeypatch):
        """Commands not on PATH return is_error=True, no crash."""
        from agency.tools import ToolContext, _run_shell

        monkeypatch.setenv("AGENCY_ALLOW_SHELL", "1")
        ctx = ToolContext(
            workdir=tmp_path,
            allow_shell=True,
            shell_allowlist=("__nonexistent_cmd_xyz123__",),
        )
        result = _run_shell({"command": "__nonexistent_cmd_xyz123__"}, ctx)
        assert result.is_error is True


# ---------------------------------------------------------------------------
# 5. ToolContext safe-path sandbox enforcement
# ---------------------------------------------------------------------------


class TestToolContextSafePath:
    def test_path_outside_workdir_raises(self, tmp_path):
        from agency.tools import ToolContext, _safe_path

        ctx = ToolContext(workdir=tmp_path / "work")
        ctx.workdir.mkdir(parents=True, exist_ok=True)

        with pytest.raises(PermissionError):
            _safe_path(ctx, "../../../etc/passwd")

    def test_path_inside_workdir_ok(self, tmp_path):
        from agency.tools import ToolContext, _safe_path

        ctx = ToolContext(workdir=tmp_path)
        p = _safe_path(ctx, "subdir/file.txt")
        assert str(tmp_path) in str(p)

    def test_absolute_path_outside_workdir_raises(self, tmp_path):
        from agency.tools import ToolContext, _safe_path

        ctx = ToolContext(workdir=tmp_path / "work")
        ctx.workdir.mkdir(parents=True, exist_ok=True)

        with pytest.raises(PermissionError):
            _safe_path(ctx, "/etc/passwd")


# ---------------------------------------------------------------------------
# 6. Knowledge expansion — log on storage failure
# ---------------------------------------------------------------------------


class TestKnowledgeExpansionErrorLogging:
    def test_vector_store_add_failure_logs_warning(self, caplog):
        from agency.knowledge_expansion import KnowledgeChunk, KnowledgeExpansion

        engine = KnowledgeExpansion()
        bad_store = MagicMock()
        bad_store.add.side_effect = OSError("disk full")
        engine._vector_store = bad_store

        chunk = KnowledgeChunk(
            chunk_id="c1",
            source="test",
            text="some text",
            summary="summary",
            tags=[],
            domain="general",
        )

        with caplog.at_level(logging.WARNING):
            engine._store_chunk(chunk)

        assert any(
            "vector_store" in r.message or "add" in r.message
            for r in caplog.records
        )

    def test_context_manager_store_failure_logs_warning(self, caplog):
        from agency.knowledge_expansion import KnowledgeChunk, KnowledgeExpansion

        engine = KnowledgeExpansion()
        bad_cm = MagicMock()
        bad_cm.store.side_effect = RuntimeError("context broken")
        engine._context_manager = bad_cm

        chunk = KnowledgeChunk(
            chunk_id="c2",
            source="test",
            text="text",
            summary="",
            tags=[],
            domain="general",
        )

        with caplog.at_level(logging.WARNING):
            engine._store_chunk(chunk)

        assert any(
            "context_manager" in r.message or "store" in r.message
            for r in caplog.records
        )


# ---------------------------------------------------------------------------
# 7. SelfLearnerEngine — malformed snapshot import logs and skips
# ---------------------------------------------------------------------------


class TestSelfLearnerImport:
    def _valid_lesson_dict(self, id_: str) -> dict:
        return {
            "timestamp": f"2025-01-0{id_}T00:00:00",
            "context": "writing code",
            "outcome": "success",
            "insight": f"Lesson {id_}",
        }

    def test_malformed_lesson_logs_and_skips(self, tmp_path, caplog):
        from agency.self_learner_engine import SelfLearnerEngine

        eng = SelfLearnerEngine(lessons_path=tmp_path / "lessons.jsonl")
        snapshot = {
            "lessons": [
                self._valid_lesson_dict("1"),
                {"broken": True},            # malformed — unknown kwargs
                self._valid_lesson_dict("2"),
            ]
        }

        with caplog.at_level(logging.WARNING):
            count = eng.import_knowledge_snapshot(snapshot)

        assert count == 2  # 2 valid, 1 skipped
        assert any(
            "lesson" in r.message.lower() or "malformed" in r.message.lower()
            for r in caplog.records
        )

    def test_all_malformed_returns_zero(self, tmp_path):
        from agency.self_learner_engine import SelfLearnerEngine

        eng = SelfLearnerEngine(lessons_path=tmp_path / "lessons.jsonl")
        snapshot = {"lessons": [{"x": 1}, {"y": 2}, {"z": 3}]}
        assert eng.import_knowledge_snapshot(snapshot) == 0

    def test_empty_lessons_list_returns_zero(self, tmp_path):
        from agency.self_learner_engine import SelfLearnerEngine

        eng = SelfLearnerEngine(lessons_path=tmp_path / "lessons.jsonl")
        assert eng.import_knowledge_snapshot({"lessons": []}) == 0

    def test_missing_lessons_key_returns_zero(self, tmp_path):
        from agency.self_learner_engine import SelfLearnerEngine

        eng = SelfLearnerEngine(lessons_path=tmp_path / "lessons.jsonl")
        assert eng.import_knowledge_snapshot({}) == 0


# -------