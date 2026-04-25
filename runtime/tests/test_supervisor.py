"""Tests for the process supervisor."""

from __future__ import annotations

import sys
import time

import pytest

from agency.supervisor import (
    SupervisedResult,
    crash_message,
    run_supervised,
)

PY = sys.executable


# ----- happy path ---------------------------------------------------


def test_clean_exit():
    r = run_supervised([PY, "-c", "print('hello')"], timeout_s=5.0)
    assert r.ok
    assert "hello" in r.stdout
    assert r.returncode == 0
    assert r.killed_reason is None


def test_nonzero_exit_is_not_killed():
    r = run_supervised([PY, "-c", "import sys; sys.exit(7)"], timeout_s=5.0)
    assert r.returncode == 7
    assert r.killed_reason is None
    assert not r.ok  # ok requires returncode 0


def test_stderr_is_captured():
    r = run_supervised(
        [PY, "-c", "import sys; sys.stderr.write('boom\\n')"],
        timeout_s=5.0,
    )
    assert "boom" in r.stderr


def test_stdin_text_is_piped():
    r = run_supervised(
        [PY, "-c", "import sys; print(sys.stdin.read().upper())"],
        stdin_text="abc",
        timeout_s=5.0,
    )
    assert "ABC" in r.stdout


# ----- timeout ------------------------------------------------------


def test_timeout_kills_long_running_process():
    start = time.monotonic()
    r = run_supervised(
        [PY, "-c", "import time; time.sleep(30)"],
        timeout_s=1.0,
    )
    elapsed = time.monotonic() - start
    assert r.killed_reason == "timeout"
    assert elapsed < 5.0  # we killed it well before its 30s sleep
    assert "process killed by supervisor: timeout" in r.crash_dump
    assert "elapsed:" in r.crash_dump


def test_timeout_captures_partial_stdout_at_kill():
    """A killed process's stdout-up-to-kill should be in the result so
    the agent can read it as a crash dump."""
    r = run_supervised(
        [PY, "-c",
         "import sys, time; "
         "sys.stdout.write('PARTIAL_OUTPUT_BEFORE_KILL\\n'); "
         "sys.stdout.flush(); "
         "time.sleep(30)"],
        timeout_s=1.5,
    )
    assert r.killed_reason == "timeout"
    assert "PARTIAL_OUTPUT_BEFORE_KILL" in r.stdout
    assert "PARTIAL_OUTPUT_BEFORE_KILL" in r.crash_dump


def test_hard_timeout_caps_user_timeout(monkeypatch):
    """`timeout_s` is hard-capped by AGENCY_PROCESS_HARD_TIMEOUT."""
    monkeypatch.setenv("AGENCY_PROCESS_HARD_TIMEOUT", "0.5")
    # Reload the module so it re-reads the env var.
    import importlib
    import agency.supervisor as sup
    importlib.reload(sup)
    try:
        r = sup.run_supervised(
            [PY, "-c", "import time; time.sleep(10)"],
            timeout_s=60.0,  # asks for 60s but should be capped at 0.5s
        )
        assert r.killed_reason == "timeout"
        assert r.elapsed_s < 3.0
    finally:
        # Restore default for other tests
        monkeypatch.delenv("AGENCY_PROCESS_HARD_TIMEOUT", raising=False)
        importlib.reload(sup)


# ----- result formatting -------------------------------------------


def test_as_dict_truncates_tails():
    r = SupervisedResult(
        returncode=0, stdout="x" * 5000, stderr="y" * 5000,
        elapsed_s=1.234,
    )
    d = r.as_dict()
    assert len(d["stdout_tail"]) == 2000
    assert len(d["stderr_tail"]) == 2000
    assert d["elapsed_s"] == 1.234
    assert d["killed_reason"] is None


def test_crash_message_clean_exit_returns_stdout():
    r = SupervisedResult(returncode=0, stdout="ok", stderr="", elapsed_s=0.1)
    msg = crash_message(r, "true")
    assert msg == "ok"


def test_crash_message_clean_exit_with_stderr_appends_it():
    r = SupervisedResult(returncode=0, stdout="ok", stderr="warn", elapsed_s=0.1)
    msg = crash_message(r, "true")
    assert "ok" in msg
    assert "[stderr]" in msg
    assert "warn" in msg


def test_crash_message_failed_includes_exit_code():
    r = SupervisedResult(
        returncode=2, stdout="", stderr="boom", elapsed_s=0.1,
    )
    msg = crash_message(r, "false")
    assert "exit 2" in msg
    assert "false" in msg
    assert "boom" in msg


def test_crash_message_killed_uses_dump():
    dump = "=== killed ===\nfoo"
    r = SupervisedResult(
        returncode=-1, stdout="", stderr="", elapsed_s=1.0,
        killed_reason="timeout", crash_dump=dump,
    )
    msg = crash_message(r, "sleep 30")
    assert msg == dump
