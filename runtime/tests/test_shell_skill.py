"""Tests for runtime/agency/shell_skill.py.

Covers trust-mode gating, allowlist, extra denylist, timeout, and output
capture.  Every test manipulates AGENCY_TRUST_MODE via monkeypatch so the
real ~/.agency/trust.conf (if present) is never consulted.
"""

from __future__ import annotations

import os
import sys

import pytest

from agency.shell_skill import (
    SAFE_ALLOWLIST,
    ShellResult,
    ShellSkill,
    _OFF_HEBREW,
    _extra_denied,
)
from agency.trust import TrustMode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _skill(**kwargs) -> ShellSkill:
    return ShellSkill(**kwargs)


def _set_trust(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    """Override the active trust mode via env var (highest-priority source)."""
    monkeypatch.setenv("AGENCY_TRUST_MODE", mode)
    # Ensure no conf file interferes.
    monkeypatch.setenv("AGENCY_TRUST_CONF", os.devnull)


# ===========================================================================
# OFF mode
# ===========================================================================

class TestOffMode:
    def test_refuses_all_commands(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_trust(monkeypatch, "off")
        result = _skill().execute("echo hello")
        assert result.denied
        assert not result.ok

    def test_refusal_message_is_hebrew(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_trust(monkeypatch, "off")
        result = _skill().execute("ls")
        assert result.denied_reason == _OFF_HEBREW
        # Spot-check at least one Hebrew char
        assert any("א" <= ch <= "ת" for ch in result.denied_reason)

    def test_trust_mode_recorded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_trust(monkeypatch, "off")
        result = _skill().execute("pwd")
        assert result.trust_mode is TrustMode.OFF

    def test_empty_command_also_denied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_trust(monkeypatch, "off")
        result = _skill().execute("   ")
        assert result.denied


# ===========================================================================
# ON_MY_MACHINE mode
# ===========================================================================

class TestOnMyMachineMode:
    def test_echo_hello_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_trust(monkeypatch, "on-my-machine")
        result = _skill().execute("echo hello")
        assert not result.denied
        assert result.ok
        assert "hello" in result.stdout

    def test_stdout_captured_correctly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_trust(monkeypatch, "on-my-machine")
        result = _skill().execute("echo jarvis")
        assert "jarvis" in result.stdout
        assert result.returncode == 0

    def test_allowlist_blocks_unknown_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_trust(monkeypatch, "on-my-machine")
        # 'curl' is not in SAFE_ALLOWLIST
        result = _skill(enforce_allowlist=True).execute("curl https://example.com")
        assert result.denied
        assert "allowlist" in result.denied_reason.lower()

    def test_allowlist_disabled_allows_arbitrary_safe_command(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_trust(monkeypatch, "on-my-machine")
        # With enforce_allowlist=False, only the denylist applies.
        result = _skill(enforce_allowlist=False).execute("echo bypass")
        assert not result.denied
        assert "bypass" in result.stdout

    @pytest.mark.parametrize("dangerous_cmd", [
        "rm -rf /",
        "rm -fr /",
        "rm -rf /*",
        "del /s",
        "format C:",
    ])
    def test_dangerous_commands_blocked(
        self, monkeypatch: pytest.MonkeyPatch, dangerous_cmd: str
    ) -> None:
        _set_trust(monkeypatch, "on-my-machine")
        result = _skill(enforce_allowlist=False).execute(dangerous_cmd)
        assert result.denied, f"Expected {dangerous_cmd!r} to be denied"

    def test_trust_mode_recorded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_trust(monkeypatch, "on-my-machine")
        result = _skill().execute("echo trust")
        assert result.trust_mode is TrustMode.ON_MY_MACHINE

    def test_output_property_combines_stdout_stderr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_trust(monkeypatch, "on-my-machine")
        # A command that writes to stderr (redirect in shell)
        result = _skill().execute("echo out && echo err >&2")
        assert "out" in result.output

    def test_non_zero_exit_is_not_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_trust(monkeypatch, "on-my-machine")
        # python3 is in SAFE_ALLOWLIST; sys.exit(1) guarantees returncode=1.
        result = _skill().execute("python3 -c 'import sys; sys.exit(1)'")
        assert not result.ok
        assert result.returncode != 0

    def test_error_property_for_denied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_trust(monkeypatch, "on-my-machine")
        result = _skill().execute("curl https://example.com")
        assert result.denied
        assert result.error  # non-empty


# ===========================================================================
# YOLO mode
# ===========================================================================

class TestYoloMode:
    def test_allows_any_command(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        _set_trust(monkeypatch, "yolo")
        result = _skill().execute("echo yolo_works")
        assert not result.denied
        assert "yolo_works" in result.stdout

    def test_prints_warning(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        _set_trust(monkeypatch, "yolo")
        _skill().execute("echo yolo")
        captured = capsys.readouterr()
        # The Hebrew warning should be printed to stdout
        assert "YOLO" in captured.out or "אזהרה" in captured.out

    def test_trust_mode_recorded(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        _set_trust(monkeypatch, "yolo")
        result = _skill().execute("echo mode")
        assert result.trust_mode is TrustMode.YOLO


# ===========================================================================
# Timeout
# ===========================================================================

class TestTimeout:
    @pytest.mark.slow
    def test_timeout_raises_timed_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_trust(monkeypatch, "on-my-machine")
        # python3 is in SAFE_ALLOWLIST; time.sleep(10) guarantees the process
        # outlasts the 1-second timeout without needing enforce_allowlist=False.
        result = _skill(timeout=1).execute("python3 -c 'import time; time.sleep(10)'")
        assert result.timed_out
        assert not result.ok
        assert "Timed out" in result.error

    def test_fast_command_does_not_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_trust(monkeypatch, "on-my-machine")
        result = _skill(timeout=5).execute("echo fast")
        assert not result.timed_out
        assert result.ok


# ===========================================================================
# Extra denylist unit tests (mode-independent helper)
# ===========================================================================

class TestExtraDenylist:
    @pytest.mark.parametrize("cmd,should_deny", [
        ("del /s C:\\foo", True),
        ("rd /s /q C:\\Windows", True),
        ("format C:", True),
        ("echo hello", False),
        ("git status", False),
        ("python -m pytest", False),
    ])
    def test_extra_denied_patterns(self, cmd: str, should_deny: bool) -> None:
        denied, _ = _extra_denied(cmd)
        assert denied == should_deny, f"_extra_denied({cmd!r}) expected {should_deny}"


# ===========================================================================
# SAFE_ALLOWLIST sanity checks
# ===========================================================================

class TestSafeAllowlist:
    def test_allowlist_is_frozenset(self) -> None:
        assert isinstance(SAFE_ALLOWLIST, frozenset)

    @pytest.mark.parametrize("cmd", ["ls", "cat", "git", "echo", "grep", "python3"])
    def test_common_read_commands_present(self, cmd: str) -> None:
        assert cmd in SAFE_ALLOWLIST

    @pytest.mark.parametrize("cmd", ["curl", "wget", "rm", "mv", "cp", "chmod"])
    def test_destructive_commands_absent(self, cmd: str) -> None:
        assert cmd not in SAFE_ALLOWLIST


# ===========================================================================
# ShellResult properties
# ===========================================================================

class TestShellResultProperties:
    def test_ok_true_on_clean_success(self) -> None:
        r = ShellResult(command="echo hi", stdout="hi\n", returncode=0,
                        trust_mode=TrustMode.ON_MY_MACHINE)
        assert r.ok

    def test_ok_false_when_denied(self) -> None:
        r = ShellResult(command="rm -rf /", denied=True,
                        denied_reason="nope", trust_mode=TrustMode.OFF)
        assert not r.ok

    def test_ok_false_when_timed_out(self) -> None:
        r = ShellResult(command="sleep 999", timed_out=True,
                        trust_mode=TrustMode.ON_MY_MACHINE)
        assert not r.ok

    def test_output_includes_stderr_section(self) -> None:
        r = ShellResult(command="cmd", stdout="out\n", stderr="err\n",
                        returncode=0, trust_mode=TrustMode.ON_MY_MACHINE)
        assert "out" in r.output
        assert "err" in r.output

    def test_output_includes_exit_code_on_failure(self) -> None:
        r = ShellResult(command="cmd", returncode=2,
                        trust_mode=TrustMode.ON_MY_MACHINE)
        assert "exit: 2" in r.output
