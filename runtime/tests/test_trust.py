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
    assert g.block_metadata_fetches is True


def test_on_my_machine_lifts_sandboxes_keeps_denylist(monkeypatch):
    monkeypatch.setenv("AGENCY_TRUST_MODE", "on-my-machine")
    g = gate()
    assert g.allow_shell is True
    assert g.enforce_shell_allowlist is False
    assert g.enforce_shell_denylist is True
    assert g.sandbox_paths_to_workdir is False
    assert g.block_private_ip_fetches is False
    # Metadata IPs stay blocked: even on a trusted dev box, an agent
    # reading IAM creds from 169.254.169.254 is a credential-exfil pathway.
    assert g.block_metadata_fetches is True


def test_yolo_lifts_everything(monkeypatch):
    monkeypatch.setenv("AGENCY_TRUST_MODE", "yolo")
    g = gate()
    assert g.enforce_shell_allowlist is False
    assert g.enforce_shell_denylist is False
    assert g.sandbox_paths_to_workdir is False
    assert g.block_private_ip_fetches is False
    assert g.block_metadata_fetches is False


# ----- shell denylist -----------------------------------------------------


@pytest.mark.parametrize("cmd", [
    "rm -rf /",
    "rm -rf /*",
    "rm -fr / ",
    ":(){ :|:& };:",
    "mkfs.ext4 /dev/sda1",
    "dd if=/dev/zero of=/dev/sda bs=1M",
    "chmod 000 /",
    # Recursive chmod — input is lowercased before regex, so the pattern
    # must match `r` not `R`. Catches both -R and -r forms.
    "chmod -R 000 /",
    "chmod -r 000 /",
    # Quoted variants — shlex round-trip strips the quotes so these match
    # the same patterns as their unquoted forms.
    'rm -rf "/"',
    "rm -rf '/'",
    'dd if=/dev/zero of="/dev/sda" bs=1M',
    "mkfs.ext4 '/dev/sda1'",
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
    """In trust mode, the private-IP SSRF block is lifted. Stub the
    transport so the test doesn't depend on whether port 1 happens to be
    closed (CI sandboxes have surprised us here): we just verify the
    request reached the network layer instead of being short-circuited
    by the 'Refusing to fetch' SSRF check."""
    import httpx

    from agency.tools import ToolContext, _web_fetch

    monkeypatch.setenv("AGENCY_TRUST_MODE", "on-my-machine")
    ctx = ToolContext.from_env(workdir=tmp_path)

    def fake_send(self, request, **kwargs):
        raise httpx.ConnectError("stubbed: no connection")

    monkeypatch.setattr(httpx.Client, "send", fake_send)

    res = _web_fetch({"url": "http://127.0.0.1:8080/"}, ctx)
    # We should hit a Fetch error (the stubbed ConnectError), not the SSRF refusal.
    assert res.is_error
    assert "refusing to fetch" not in res.content.lower()
    assert "fetch error" in res.content.lower()


def test_web_fetch_blocks_metadata_even_in_on_my_machine(tmp_path: Path, monkeypatch):
    """Cloud instance metadata stays blocked in on-my-machine mode.

    Lifting the private-IP gate so an agent can hit a local dev server is
    fine; lifting it so it can read IAM creds from 169.254.169.254 on an
    EC2 dev box is a credential-exfil pathway. Verify the metadata gate
    is independent and stays on by default in trust mode."""
    import httpx

    from agency.tools import ToolContext, _web_fetch

    monkeypatch.setenv("AGENCY_TRUST_MODE", "on-my-machine")
    ctx = ToolContext.from_env(workdir=tmp_path)

    # Belt-and-braces: also stub the transport so a misconfigured CI
    # box doesn't accidentally hit the real metadata endpoint if our
    # gate ever regressed. The assertion below catches the regression
    # via the ToolResult message; this stub keeps the test hermetic.
    def fake_send(self, request, **kwargs):
        raise AssertionError(
            "metadata gate failed to short-circuit — request reached the network",
        )

    monkeypatch.setattr(httpx.Client, "send", fake_send)

    res = _web_fetch({"url": "http://169.254.169.254/latest/meta-data/"}, ctx)
    assert res.is_error
    assert "metadata" in res.content.lower()


def test_web_fetch_allows_metadata_in_yolo(tmp_path: Path, monkeypatch):
    """YOLO is the documented escape hatch — no guardrails. Verify the
    metadata gate is the only thing standing between trust mode and the
    metadata endpoint, and that yolo lifts it."""
    import httpx

    from agency.tools import ToolContext, _web_fetch

    monkeypatch.setenv("AGENCY_TRUST_MODE", "yolo")
    ctx = ToolContext.from_env(workdir=tmp_path)

    def fake_send(self, request, **kwargs):
        raise httpx.ConnectError("stubbed: no connection")

    monkeypatch.setattr(httpx.Client, "send", fake_send)

    res = _web_fetch({"url": "http://169.254.169.254/latest/meta-data/"}, ctx)
    # Reaches the network (stubbed ConnectError), not refused by the gate.
    assert res.is_error
    assert "refusing to fetch" not in res.content.lower()
    assert "fetch error" in res.content.lower()


def test_web_fetch_dns_failure_in_on_my_machine_is_not_metadata(
    tmp_path: Path, monkeypatch,
):
    """Regression: the metadata gate must distinguish DNS failure from a
    confirmed metadata endpoint. In `on-my-machine` the private-IP gate is
    intentionally lifted, so a flaky `.local` hostname should surface a
    real connection error — not get masquerade-rejected as 'cloud metadata
    address'."""
    import httpx
    import socket as _socket

    from agency.tools import ToolContext, _web_fetch

    monkeypatch.setenv("AGENCY_TRUST_MODE", "on-my-machine")
    ctx = ToolContext.from_env(workdir=tmp_path)

    def fake_getaddrinfo(*args, **kwargs):
        raise _socket.gaierror("stubbed: DNS unreachable")

    monkeypatch.setattr(_socket, "getaddrinfo", fake_getaddrinfo)

    def fake_send(self, request, **kwargs):
        raise httpx.ConnectError("stubbed: no connection")

    monkeypatch.setattr(httpx.Client, "send", fake_send)

    res = _web_fetch({"url": "http://my-dev-server.local:8080/api"}, ctx)
    assert res.is_error
    # The fix: DNS failure on a non-metadata-looking host falls through.
    assert "metadata" not in res.content.lower()
    assert "fetch error" in res.content.lower()


# ----- _write_file / _edit_file display path -----------------------------


def test_write_file_outside_workdir_in_trust_mode_does_not_crash(
    tmp_path: Path, monkeypatch,
):
    """Regression: _write_file used path.relative_to(ctx.workdir) for the
    success message, which raised ValueError when trust mode lifted the
    sandbox. The agent saw a fake error after a successful write and
    retried, leading to spurious double-writes."""
    from agency.tools import ToolContext, _write_file

    monkeypatch.setenv("AGENCY_TRUST_MODE", "on-my-machine")
    ctx = ToolContext.from_env(workdir=tmp_path)

    # Pick a target outside the workdir but inside another tmp dir we can
    # write to without elevated permissions.
    other = tmp_path.parent / "other-dir-for-trust-test"
    other.mkdir(exist_ok=True)
    target = other / "out-of-workdir.txt"

    res = _write_file({"path": str(target), "content": "hi"}, ctx)
    assert not res.is_error, res.content
    assert target.read_text() == "hi"
    # Message should contain the absolute path (not crash trying to render
    # it relative to a workdir it isn't under).
    assert str(target) in res.content


def test_edit_file_outside_workdir_in_trust_mode_does_not_crash(
    tmp_path: Path, monkeypatch,
):
    """Same regression for _edit_file."""
    from agency.tools import ToolContext, _edit_file

    monkeypatch.setenv("AGENCY_TRUST_MODE", "on-my-machine")
    ctx = ToolContext.from_env(workdir=tmp_path)

    other = tmp_path.parent / "other-dir-for-trust-test-edit"
    other.mkdir(exist_ok=True)
    target = other / "out.txt"
    target.write_text("hello WORLD\n")

    res = _edit_file({
        "path": str(target),
        "old_string": "WORLD",
        "new_string": "trust",
    }, ctx)
    assert not res.is_error, res.content
    assert target.read_text() == "hello trust\n"
    assert str(target) in res.content


def test_trust_gate_no_longer_carries_dead_field():
    """Removed: TrustGate.allow_network_default. ToolContext.from_env reads
    AGENCY_NO_NETWORK directly; that field was unused in every code path
    and falsely implied per-mode network defaults."""
    from agency.trust import TrustGate
    fields = {f.name for f in TrustGate.__dataclass_fields__.values()}
    assert "allow_network_default" not in fields
