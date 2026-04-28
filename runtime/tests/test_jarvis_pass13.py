"""Pass 13 tests — batch mode, skill hot-reload, export, dead-letter queue.

Run:
    cd runtime && PYTHONPYCACHEPREFIX=/tmp/fresh_pycache \
        python -m pytest tests/test_jarvis_pass13.py -q --tb=short --timeout=60
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_script(tmp_path: Path, lines: list[str]) -> Path:
    """Write a batch script file and return its path."""
    p = tmp_path / "test_script.txt"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


# ===========================================================================
# 1. BatchRunner — core logic
# ===========================================================================

class TestBatchRunner:

    def test_parse_script_strips_comments(self, tmp_path):
        from agency.batch import _parse_script
        p = _write_script(tmp_path, [
            "# This is a comment",
            "hello jarvis",
            "",
            "# another comment",
            "summarise the news",
        ])
        prompts = _parse_script(p)
        assert prompts == ["hello jarvis", "summarise the news"]

    def test_parse_script_empty_file(self, tmp_path):
        from agency.batch import _parse_script
        p = tmp_path / "empty.txt"
        p.write_text("")
        assert _parse_script(p) == []

    def test_run_prompts_sequential(self, tmp_path):
        from agency.batch import BatchRunner

        calls: list[str] = []

        def _handler(prompt: str) -> str:
            calls.append(prompt)
            return f"reply:{prompt}"

        runner = BatchRunner(handler=_handler)
        run = runner.run_prompts(
            ["prompt one", "prompt two"],
            script_path=tmp_path / "s.txt",
        )

        assert len(run.results) == 2
        assert run.succeeded == 2
        assert run.failed == 0
        assert run.results[0].output == "reply:prompt one"
        assert run.results[1].output == "reply:prompt two"
        assert calls == ["prompt one", "prompt two"]

    def test_run_prompts_captures_errors(self, tmp_path):
        from agency.batch import BatchRunner

        def _bad_handler(prompt: str) -> str:
            raise ValueError("boom")

        runner = BatchRunner(handler=_bad_handler)
        run = runner.run_prompts(["x"], script_path=tmp_path / "s.txt")

        assert run.failed == 1
        assert "ValueError" in run.results[0].error
        assert not run.results[0].ok

    def test_run_file_writes_output_md(self, tmp_path):
        from agency.batch import BatchRunner

        script = _write_script(tmp_path, ["q1", "q2"])

        runner = BatchRunner(handler=lambda p: f"ans:{p}")
        run = runner.run_file(script)

        assert run.output_path is not None
        assert run.output_path.exists()
        content = run.output_path.read_text()
        assert "ans:q1" in content
        assert "ans:q2" in content
        assert "# Batch Run" in content

    def test_run_file_output_md_contains_errors(self, tmp_path):
        from agency.batch import BatchRunner

        script = _write_script(tmp_path, ["bad_prompt"])

        def _fail(p: str) -> str:
            raise RuntimeError("test error")

        runner = BatchRunner(handler=_fail)
        run = runner.run_file(script)

        content = run.output_path.read_text()
        assert "RuntimeError" in content or "test error" in content

    def test_run_prompts_parallel(self, tmp_path):
        from agency.batch import BatchRunner

        order: list[int] = []
        lock = threading.Lock()

        def _handler(prompt: str) -> str:
            with lock:
                order.append(int(prompt))
            return f"done:{prompt}"

        runner = BatchRunner(handler=_handler)
        run = runner.run_prompts(
            [str(i) for i in range(4)],
            script_path=tmp_path / "s.txt",
            parallel=2,
        )

        assert run.total == 4
        assert run.succeeded == 4
        # All prompts processed regardless of order
        assert {r.prompt for r in run.results} == {"0", "1", "2", "3"}

    def test_progress_callback_called(self, tmp_path):
        from agency.batch import BatchRunner

        progress_calls: list[tuple] = []

        def _progress(i, total, prompt):
            progress_calls.append((i, total, prompt))

        runner = BatchRunner(
            handler=lambda p: "ok",
            progress_cb=_progress,
        )
        runner.run_prompts(["a", "b", "c"], script_path=tmp_path / "s.txt")

        assert len(progress_calls) == 3
        assert progress_calls[0] == (1, 3, "a")
        assert progress_calls[2] == (3, 3, "c")

    def test_batch_result_index_is_1_based(self, tmp_path):
        from agency.batch import BatchRunner

        runner = BatchRunner(handler=lambda p: p)
        run = runner.run_prompts(["x", "y"], script_path=tmp_path / "s.txt")
        assert run.results[0].index == 1
        assert run.results[1].index == 2

    def test_batch_result_elapsed_positive(self, tmp_path):
        from agency.batch import BatchRunner

        runner = BatchRunner(handler=lambda p: time.sleep(0.001) or "ok")
        run = runner.run_prompts(["z"], script_path=tmp_path / "s.txt")
        assert run.results[0].elapsed_s >= 0


# ===========================================================================
# 2. SkillWatcher — hot-reload
# ===========================================================================

class TestSkillWatcher:

    def test_watcher_starts_and_stops(self, tmp_path):
        from agency.skills import SkillWatcher

        watcher = SkillWatcher(
            watch_dir=tmp_path,
            reload_fn=lambda r: None,
            poll_interval_s=0.1,
        )
        watcher.start()
        assert watcher.is_alive()
        watcher.stop()
        watcher.join(timeout=2.0)
        assert not watcher.is_alive()

    def test_watcher_detects_new_file(self, tmp_path):
        from agency.skills import SkillWatcher

        reloaded: list[int] = []

        def _on_reload(registry):
            reloaded.append(1)

        # Patch SkillRegistry.load to avoid needing a real repo
        with patch("agency.skills.SkillRegistry.load") as mock_load:
            mock_load.return_value = MagicMock()
            watcher = SkillWatcher(
                watch_dir=tmp_path,
                reload_fn=_on_reload,
                poll_interval_s=0.05,
            )
            watcher.start()
            time.sleep(0.1)

            # Create a new .md file — should trigger reload
            (tmp_path / "new_skill.md").write_text("---\nname: Test\n---\nbody")
            time.sleep(0.3)

            watcher.stop()
            watcher.join(timeout=2.0)

        assert len(reloaded) >= 1

    def test_watcher_detects_mtime_change(self, tmp_path):
        from agency.skills import SkillWatcher

        # Create file before watcher starts
        skill_file = tmp_path / "skill.md"
        skill_file.write_text("v1")

        reloaded: list[int] = []

        with patch("agency.skills.SkillRegistry.load") as mock_load:
            mock_load.return_value = MagicMock()
            watcher = SkillWatcher(
                watch_dir=tmp_path,
                reload_fn=lambda r: reloaded.append(1),
                poll_interval_s=0.05,
            )
            watcher.start()
            time.sleep(0.1)

            # Modify file
            time.sleep(0.05)
            skill_file.write_text("v2")
            time.sleep(0.3)

            watcher.stop()
            watcher.join(timeout=2.0)

        assert len(reloaded) >= 1

    def test_watcher_no_reload_when_no_change(self, tmp_path):
        from agency.skills import SkillWatcher

        (tmp_path / "static.md").write_text("unchanged")
        reloaded: list[int] = []

        with patch("agency.skills.SkillRegistry.load") as mock_load:
            mock_load.return_value = MagicMock()
            watcher = SkillWatcher(
                watch_dir=tmp_path,
                reload_fn=lambda r: reloaded.append(1),
                poll_interval_s=0.05,
            )
            watcher.start()
            time.sleep(0.3)  # 6 polls, nothing changed
            watcher.stop()
            watcher.join(timeout=2.0)

        assert len(reloaded) == 0

    def test_watcher_handles_missing_dir_gracefully(self, tmp_path):
        from agency.skills import SkillWatcher

        missing = tmp_path / "no_such_dir"
        watcher = SkillWatcher(
            watch_dir=missing,
            reload_fn=lambda r: None,
            poll_interval_s=0.05,
        )
        watcher.start()
        time.sleep(0.2)
        watcher.stop()
        watcher.join(timeout=2.0)
        # Should not raise


# ===========================================================================
# 3. Export — session rendering
# ===========================================================================

class TestExport:

    def _make_session(self, history_dir: Path, sid: str, messages: list[dict]) -> Path:
        p = history_dir / f"{sid}.jsonl"
        with p.open("w") as f:
            for m in messages:
                f.write(json.dumps(m) + "\n")
        return p

    def test_export_markdown_format(self, tmp_path):
        from agency.export import export_session

        hdir = tmp_path / "history"
        hdir.mkdir()
        sid = "2025-01-15_143022"
        self._make_session(hdir, sid, [
            {"role": "user", "content": "hello", "timestamp": "2025-01-15T14:30:22"},
            {"role": "assistant", "content": "hi there", "timestamp": "2025-01-15T14:30:23"},
        ])

        with patch("agency.export.history_dir", return_value=hdir), \
             patch("agency.export.list_sessions", return_value=[hdir / f"{sid}.jsonl"]):
            out = export_session(session_id=sid, fmt="md",
                                 output_path=tmp_path / "out.md")

        content = out.read_text()
        assert "## Session" in content
        assert "**User**" in content
        assert "hello" in content
        assert "**JARVIS**" in content
        assert "hi there" in content

    def test_export_html_format(self, tmp_path):
        from agency.export import export_session

        hdir = tmp_path / "history"
        hdir.mkdir()
        sid = "2025-01-15_143022"
        self._make_session(hdir, sid, [
            {"role": "user", "content": "test", "timestamp": ""},
        ])

        with patch("agency.export.history_dir", return_value=hdir), \
             patch("agency.export.list_sessions", return_value=[hdir / f"{sid}.jsonl"]):
            out = export_session(session_id=sid, fmt="html",
                                 output_path=tmp_path / "out.html")

        content = out.read_text()
        assert "<!DOCTYPE html>" in content
        assert "JARVIS Chat" in content
        assert "test" in content
        assert 'class="bubble"' in content

    def test_export_json_format(self, tmp_path):
        from agency.export import export_session

        hdir = tmp_path / "history"
        hdir.mkdir()
        sid = "2025-01-15_143022"
        self._make_session(hdir, sid, [
            {"role": "user", "content": "json test", "timestamp": ""},
        ])

        with patch("agency.export.history_dir", return_value=hdir), \
             patch("agency.export.list_sessions", return_value=[hdir / f"{sid}.jsonl"]):
            out = export_session(session_id=sid, fmt="json",
                                 output_path=tmp_path / "out.json")

        data = json.loads(out.read_text())
        assert data["session_id"] == sid
        assert data["messages"][0]["content"] == "json test"

    def test_export_defaults_to_most_recent(self, tmp_path):
        from agency.export import export_session

        hdir = tmp_path / "history"
        hdir.mkdir()
        sid = "2025-02-01_120000"
        session_path = self._make_session(hdir, sid, [
            {"role": "user", "content": "recent", "timestamp": ""},
        ])

        with patch("agency.export.history_dir", return_value=hdir), \
             patch("agency.export.list_sessions", return_value=[session_path]):
            out = export_session(fmt="md", output_path=tmp_path / "out.md")

        assert "recent" in out.read_text()

    def test_export_raises_when_session_not_found(self, tmp_path):
        from agency.export import export_session

        hdir = tmp_path / "history"
        hdir.mkdir()

        with patch("agency.export.history_dir", return_value=hdir):
            with pytest.raises(FileNotFoundError):
                export_session(session_id="nonexistent", fmt="md",
                               output_path=tmp_path / "out.md")

    def test_export_raises_when_no_sessions(self, tmp_path):
        from agency.export import export_session

        hdir = tmp_path / "history"
        hdir.mkdir()

        with patch("agency.export.history_dir", return_value=hdir), \
             patch("agency.export.list_sessions", return_value=[]):
            with pytest.raises(FileNotFoundError):
                export_session(fmt="md", output_path=tmp_path / "out.md")

    def test_export_html_escapes_special_chars(self, tmp_path):
        from agency.export import _to_html

        messages = [{"role": "user", "content": "<script>alert(1)</script>",
                     "timestamp": ""}]
        html = _to_html("test", messages)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_list_exportable_sessions(self, tmp_path):
        from agency.export import list_exportable_sessions

        hdir = tmp_path / "history"
        hdir.mkdir()
        for i in range(3):
            p = hdir / f"2025-01-0{i+1}_000000.jsonl"
            p.write_text(json.dumps({"role": "user", "content": f"msg{i}",
                                     "timestamp": ""}) + "\n")

        with patch("agency.export.list_sessions",
                   return_value=sorted(hdir.glob("*.jsonl"), reverse=True)):
            result = list_exportable_sessions()

        assert len(result) == 3
        for sid, count in result:
            assert count == 1


# ===========================================================================
# 4. DeadLetterQueue
# ===========================================================================

class TestDeadLetterQueue:

    def test_push_creates_entry(self, tmp_path):
        from agency.dlq import DeadLetterQueue

        dlq = DeadLetterQueue(path=tmp_path / "dlq.jsonl")
        entry = dlq.push("do something", error="TimeoutError: timed out")

        assert entry.entry_id
        assert entry.error == "TimeoutError: timed out"
        assert entry.input == "do something"
        assert entry.retry_count == 0
        assert entry.status == "failed"

    def test_push_persists_to_file(self, tmp_path):
        from agency.dlq import DeadLetterQueue

        dlq = DeadLetterQueue(path=tmp_path / "dlq.jsonl")
        dlq.push("x", error="err")

        lines = (tmp_path / "dlq.jsonl").read_text().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["input"] == "x"

    def test_list_entries_empty(self, tmp_path):
        from agency.dlq import DeadLetterQueue

        dlq = DeadLetterQueue(path=tmp_path / "dlq.jsonl")
        assert dlq.list_entries() == []

    def test_list_entries_returns_all(self, tmp_path):
        from agency.dlq import DeadLetterQueue

        dlq = DeadLetterQueue(path=tmp_path / "dlq.jsonl")
        dlq.push("a", error="e1")
        dlq.push("b", error="e2")
        dlq.push("c", error="e3")

        entries = dlq.list_entries()
        assert len(entries) == 3

    def test_retry_resolves_on_success(self, tmp_path):
        from agency.dlq import DeadLetterQueue

        dlq = DeadLetterQueue(path=tmp_path / "dlq.jsonl")
        dlq.push("prompt", error="old error")

        resolved, dead = dlq.retry_all(lambda p: None)

        assert resolved == 1
        assert dead == 0
        entries = dlq.list_entries()
        assert entries[0].status == "resolved"

    def test_retry_marks_dead_after_max_retries(self, tmp_path):
        from agency.dlq import DeadLetterQueue, MAX_RETRIES

        dlq = DeadLetterQueue(path=tmp_path / "dlq.jsonl")
        dlq.push("bad_prompt", error="initial error")

        def _always_fail(p: str) -> None:
            raise RuntimeError("still failing")

        for _ in range(MAX_RETRIES):
            dlq.retry_all(_always_fail)

        entries = dlq.list_entries()
        assert entries[0].is_dead
        assert entries[0].status == "dead"

    def test_retry_one_by_id(self, tmp_path):
        from agency.dlq import DeadLetterQueue

        dlq = DeadLetterQueue(path=tmp_path / "dlq.jsonl")
        entry = dlq.push("target", error="err")

        updated = dlq.retry_one(entry.entry_id, lambda p: None)
        assert updated is not None
        assert updated.status == "resolved"

    def test_clear_removes_file(self, tmp_path):
        from agency.dlq import DeadLetterQueue

        dlq = DeadLetterQueue(path=tmp_path / "dlq.jsonl")
        dlq.push("x", error="e")
        dlq.push("y", error="e")

        n = dlq.clear()
        assert n == 2
        assert not (tmp_path / "dlq.jsonl").exists()

    def test_summary_counts_by_status(self, tmp_path):
        from agency.dlq import DeadLetterQueue

        dlq = DeadLetterQueue(path=tmp_path / "dlq.jsonl")
        dlq.push("a", error="e")
        dlq.push("b", error="e")
        dlq.retry_all(lambda p: None)   # resolves both

        s = dlq.summary()
        assert s["resolved"] == 2
        assert s["total"] == 2

    def test_is_dead_after_max_retries(self, tmp_path):
        from agency.dlq import DLQEntry, MAX_RETRIES

        e = DLQEntry(
            entry_id="x", timestamp=0, error="e", input="p",
            retry_count=MAX_RETRIES, status="failed"
        )
        assert e.is_dead

    def test_is_retryable_when_under_max(self, tmp_path):
        from agency.dlq import DLQEntry, MAX_RETRIES

        e = DLQEntry(
            entry_id="x", timestamp=0, error="e", input="p",
            retry_count=MAX_RETRIES - 1, status="failed"
        )
        assert e.is_retryable

    def test_context_stored_in_entry(self, tmp_path):
        from agency.dlq import DeadLetterQueue

        dlq = DeadLetterQueue(path=tmp_path / "dlq.jsonl")
        dlq.push("x", error="e", context={"skill": "engineering", "turn": 3})

        entries = dlq.list_entries()
        assert entries[0].context == {"skill": "engineering", "turn": 3}


# ===========================================================================
# 5. CLI smoke tests
# ===========================================================================

def _invoke(args: list[str], input_text: str = "") -> tuple[int, str, str]:
    import subprocess
    import os
    proc = subprocess.run(
        [sys.executable, "-m", "agency"] + args,
        input=input_text,
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
        timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


class TestCLISmoke:

    def test_dlq_list_no_file(self, tmp_path):
        """agency dlq list prints empty message when no DLQ file exists."""
        with patch("agency.dlq.DEFAULT_DLQ_PATH", tmp_path / "dlq.jsonl"):
            rc, out, err = _invoke(["dlq", "list"])
        # Should not crash
        assert rc == 0

    def test_export_help(self):
        rc, out, err = _invoke(["export", "--help"])
        assert rc == 0
        assert "session" in out.lower() or "format" in out.lower()

    def test_batch_help(self):
        rc, out, err = _invoke(["batch", "--help"])
        assert rc == 0
        assert "script" in out.lower() or "parallel" in out.lower()

    def test_dlq_help(self):
        rc, out, err = _invoke(["dlq", "--help"])
        assert rc == 0
        assert "dead" in out.lower() or "queue" in out.lower()
