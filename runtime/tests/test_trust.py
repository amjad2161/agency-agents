"""Tests for the trust-mode plumbing.

Three modes:
  off              (default) — sandboxes, allowlists, opt-ins
  on-my-machine    — agent's reach == user's reach, with a tiny denylist
  yolo             — no guards beyond what the OS itself enforces
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agency.trust import (
    TrustMode,
    current,
    gate,
    shell_command_is_denied,
)


# ----- mode resolution ----------------------------------------------------


def test_default_mode_is_off(monkeypatch):
    monkeypatch.delenv("AGENCY_TRUST_MODE", raising=False)
    assert current() is TrustMode.OFF


def test_on_my_machine_mode_recognized(monkeypatch):
    for s in ("on-my-machine", "On-My-Machine", "trust", "machine"):
        monkeypatch.setenv("AGENCY_TRUST_MODE", s)
        assert current() is TrustMode.ON_MY_MACHINE


def test_yolo_mode_recognized(monkeypatch):
    for s in ("yolo", "YOLO", "no-guards"):
        monkeypatch.setenv("AGENCY_TRUST_MODE", s)
        assert current() is TrustMode.YOLO


def test_unknown_value_falls_back_to_off(monkeypatch):
    monkeypatch.setenv("AGENCY_TRUST_MODE", "ultra-mega-supreme")
    assert current() is TrustMode.OFF


# ----- gate snapshots ------------------------------------------------------


def test_off_gate_keeps_all_existing_guards(monkeypatch):
    monkeypatch.delenv("AGENCY_TRUST_MODE", raising=False)
    g = gate()
    assert g.mode is TrustMode.OFF
    assert g.allow_shell is False  # still needs AGENCY_ALLOW_SHELL
    assert g.enforce_shell_allowlist is True
    assert g.enforce_shell_denylist is False
    assert g.sandbox_paths_to_workdir is True
    assert g.block_private_ip_fetches is True


def test_on_my_machine_lifts_sandboxes_keeps_denylist(monkeypatch):
    monkeypatch.setenv("AGENCY_TRUST_MODE", "on-my-machine")
    g = gate()
    assert g.allow_shell is True
    assert g.enforce_shell_allowlist is False
    assert g.enforce_shell_denylist is True
    assert g.sandbox_paths_to_workdir is False
    assert g.block_private_ip_fetches is False


def test_yolo_lifts_everything(monkeypatch):
    monkeypatch.setenv("AGENCY_TRUST_MODE", "yolo")
    g = gate()
    assert g.enforce_shell_allowlist is False
    assert g.enforce_shell_denylist is False
    assert g.sandbox_paths_to_workdir is False
    assert g.block_private_ip_fetches is False


# ----- shell denylist -----------------------------------------------------


@pytest.mark.parametrize("cmd", [
    "rm -rf /",
    "rm -rf /*",
    "rm -fr / ",
    ":(){ :|:& };:",
    "mkfs.ext4 /dev/sda1",
    "dd if=/dev/zero of=/dev/sda bs=1M",
    "chmod 000 /",
])
def test_denylist_catches_catastrophic_typos(cmd):
    denied, pat = shell_command_is_denied(cmd)
    assert denied, f"{cmd!r} should be denied (matched: {pat!r})"


@pytest.mark.parametrize("cmd", [
    "ls -la",
    "rm -rf ./tmp",          # relative subpath OK
    "rm -rf ~/.cache/foo",   # home-relative OK
    "git status",
    "echo $HOME",
    "python3 script.py",
    "find . -name '*.py'",
    "make test",
])
def test_denylist_allows_normal_destructive_looking_commands(cmd):
    denied, _ = shell_command_is_denied(cmd)
    assert not denied, f"{cmd!r} should NOT be denied"


# ----- _safe_path honors trust mode ---------------------------------------


def test_safe_path_blocks_escape_when_trust_off(tmp_path: Path, monkeypatch):
    from agency.tools import ToolContext, _safe_path

    monkeypatch.delenv("AGENCY_TRUST_MODE", raising=False)
    ctx = ToolContext(workdir=tmp_path.resolve())
    with pytest.raises(PermissionError):
        _safe_path(ctx, "../etc/passwd")


def test_safe_path_allows_escape_when_on_my_machine(tmp_path: Path, monkeypatch):
    from agency.tools import ToolContext, _safe_path

    monkeypatch.setenv("AGENCY_TRUST_MODE", "on-my-machine")
    ctx = ToolContext(workdir=tmp_path.resolve())
    p = _safe_path(ctx, "/etc/hostname")
    assert p == Path("/etc/hostname").resolve()


# ----- _run_shell honors trust mode ---------------------------------------


def test_run_shell_off_requires_allowlist(tmp_path: Path, monkeypatch):
    from agency.tools import ToolContext, _run_shell

    monkeypatch.delenv("AGENCY_TRUST_MODE", raising=False)
    monkeypatch.setenv("AGENCY_ALLOW_SHELL", "1")
    ctx = ToolContext.from_env(workdir=tmp_path)
    res = _run_shell({"command": "rm -rf ./test"}, ctx)
    assert res.is_error
    assert "allowlist" in res.content.lower()


def test_run_shell_on_my_machine_runs_arbitrary_commands(tmp_path: Path, monkeypatch):
    from agency.tools import ToolContext, _run_shell

    monkeypatch.setenv("AGENCY_TRUST_MODE", "on-my-machine")
    monkeypatch.delenv("AGENCY_ALLOW_SHELL", raising=False)
    (tmp_path / "marker").write_text("x")
    ctx = ToolContext.from_env(workdir=tmp_path)
    # `stat` isn't in the allowlist; in trust mode it should still run.
    res = _run_shell({"command": "stat marker"}, ctx)
    assert not res.is_error, res.content


def test_run_shell_on_my_machine_blocks_denylist(tmp_path: Path, monkeypatch):
    from agency.tools import ToolContext, _run_shell

    monkeypatch.setenv("AGENCY_TRUST_MODE", "on-my-machine")
    ctx = ToolContext.from_env(workdir=tmp_path)
    res = _run_shell({"command": "rm -rf /"}, ctx)
    assert res.is_error
    assert "denylist" in res.content.lower()


def test_run_shell_yolo_skips_denylist(tmp_path: Path, monkeypatch):
    """YOLO mode runs even denylisted commands. Verify the gate drops it
    through to the executable lookup (which then says "not found" because
    `:(){...}` isn't an executable, but the denylist did NOT block first)."""
    from agency.tools import ToolContext, _run_shell

    monkeypatch.setenv("AGENCY_TRUST_MODE", "yolo")
    ctx = ToolContext.from_env(workdir=tmp_path)
    # Use a command that the denylist would block in on-my-machine but
    # which won't actually destroy anything because the executable doesn't
    # exist. We only care that the denylist didn't intercept it.
    res = _run_shell({"command": "mkfs.fakefs /dev/null"}, ctx)
    # The error must come from "Executable not found", not the denylist.
    assert "denylist" not in res.content.lower()


# ----- _web_fetch honors trust mode ---------------------------------------


def test_web_fetch_blocks_loopback_when_trust_off(tmp_path: Path, monkeypatch):
    from agency.tools import ToolContext, _web_fetch

    monkeypatch.delenv("AGENCY_TRUST_MODE", raising=False)
    ctx = ToolContext.from_env(workdir=tmp_path)
    res = _web_fetch({"url": "http://127.0.0.1:8080/"}, ctx)
    assert res.is_error
    assert "private" in res.content.lower() or "loopback" in res.content.lower()


def test_web_fetch_allows_loopback_when_trust_on(tmp_path: Path, monkeypatch):
    """In trust mode, the SSRF block is lifted. We don't have a real
    loopback server, so we expect a connection error instead of the
    'Refusing to fetch' SSRF message."""
    from agency.tools import ToolContext, _web_fetch

    monkeypatch.setenv("AGENCY_TRUST_MODE", "on-my-machine")
    ctx = ToolContext.from_env(workdir=tmp_path)
    res = _web_fetch({"url": "http://127.0.0.1:1/"}, ctx)
    # We should hit a Fetch error (refused / unreachable), not the SSRF refusal.
    assert res.is_error
    assert "private" not in res.content.lower()
    assert "refusing to fetch" not in res.content.lower()
