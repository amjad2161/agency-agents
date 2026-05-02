"""Append-only audit log for sensitive agency operations.

Every sensitive action is recorded as a JSON line in
``~/.agency/audit.jsonl``.  Each entry carries:

* ``timestamp``   — ISO-8601 UTC
* ``event``       — one of the ``AuditEvent`` string constants
* ``payload``     — event-specific dict (command text, plugin name, …)
* ``hash``        — SHA-256 of (previous_hash + this_entry_without_hash)

The chain-hash makes tampering detectable: ``agency audit --verify`` walks
the file and re-derives each hash, reporting any break.

Audit events
------------
shell.execute      — shell command run by ShellSkill (includes trust_mode)
api.call           — outbound Anthropic API call (model, endpoint)
plugin.install     — plugin installed (name, source)
plugin.remove      — plugin removed (name)
config.change      — AgencyConfig written (key, old_value, new_value)
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Event constants
# ---------------------------------------------------------------------------

class AuditEvent:
    SHELL_EXECUTE  = "shell.execute"
    API_CALL       = "api.call"
    PLUGIN_INSTALL = "plugin.install"
    PLUGIN_REMOVE  = "plugin.remove"
    CONFIG_CHANGE  = "config.change"


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def audit_path() -> Path:
    d = Path.home() / ".agency"
    d.mkdir(parents=True, exist_ok=True)
    return d / "audit.jsonl"


_write_lock = threading.Lock()

# Genesis hash — the "previous hash" for the very first entry.
_GENESIS_HASH = "0" * 64


def _last_hash(path: Path) -> str:
    """Return the hash of the last entry in *path*, or GENESIS_HASH."""
    if not path.exists():
        return _GENESIS_HASH
    last_line = ""
    try:
        # Read the file and find the last non-empty line efficiently.
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if stripped:
                    last_line = stripped
    except OSError:
        return _GENESIS_HASH
    if not last_line:
        return _GENESIS_HASH
    try:
        entry = json.loads(last_line)
        return entry.get("hash", _GENESIS_HASH)
    except (json.JSONDecodeError, KeyError):
        return _GENESIS_HASH


def _compute_hash(prev_hash: str, entry_without_hash: str) -> str:
    """SHA-256(prev_hash + entry_without_hash)."""
    data = (prev_hash + entry_without_hash).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Public write API
# ---------------------------------------------------------------------------

def log_event(
    event: str,
    payload: dict[str, Any] | None = None,
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    """Append one audit entry to the log.

    Returns the serialised entry dict (useful for testing).
    """
    p = path or audit_path()
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    # Build entry without hash first so we can compute hash over its canonical form.
    entry_core: dict[str, Any] = {
        "timestamp": ts,
        "event": event,
        "payload": payload or {},
    }
    core_str = json.dumps(entry_core, sort_keys=True, default=str)

    with _write_lock:
        prev = _last_hash(p)
        entry_hash = _compute_hash(prev, core_str)
        entry_full = dict(entry_core)
        entry_full["hash"] = entry_hash
        line = json.dumps(entry_full, default=str)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    return entry_full


# Convenience wrappers ---------------------------------------------------

def log_shell(command: str, trust_mode: str, *, path: Path | None = None) -> dict[str, Any]:
    return log_event(
        AuditEvent.SHELL_EXECUTE,
        {"command": command, "trust_mode": trust_mode},
        path=path,
    )


def log_api_call(model: str, endpoint: str = "messages", *, path: Path | None = None) -> dict[str, Any]:
    return log_event(
        AuditEvent.API_CALL,
        {"model": model, "endpoint": endpoint},
        path=path,
    )


def log_plugin_install(name: str, source: str | None = None, *, path: Path | None = None) -> dict[str, Any]:
    return log_event(
        AuditEvent.PLUGIN_INSTALL,
        {"name": name, "source": source or ""},
        path=path,
    )


def log_plugin_remove(name: str, *, path: Path | None = None) -> dict[str, Any]:
    return log_event(
        AuditEvent.PLUGIN_REMOVE,
        {"name": name},
        path=path,
    )


def log_config_change(
    key: str,
    old_value: Any,
    new_value: Any,
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    return log_event(
        AuditEvent.CONFIG_CHANGE,
        {"key": key, "old_value": old_value, "new_value": new_value},
        path=path,
    )


# ---------------------------------------------------------------------------
# Read / verify API
# ---------------------------------------------------------------------------

def load_entries(
    *,
    tail: int | None = None,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return all (or last *tail*) audit entries as dicts."""
    p = path or audit_path()
    if not p.exists():
        return []
    entries: list[dict[str, Any]] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    if tail is not None:
        entries = entries[-tail:]
    return entries


def verify_integrity(path: Path | None = None) -> tuple[bool, list[str]]:
    """Verify the chain hash of the audit log.

    Returns ``(ok, errors)`` where *errors* is a list of human-readable
    problem descriptions.  An empty *errors* list means the log is intact.
    """
    p = path or audit_path()
    if not p.exists():
        return True, []

    errors: list[str] = []
    prev_hash = _GENESIS_HASH
    lineno = 0

    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return False, [f"Cannot read audit file: {exc}"]

    for lineno, raw in enumerate(lines, start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            errors.append(f"Line {lineno}: invalid JSON")
            continue

        recorded_hash = entry.get("hash", "")
        # Reconstruct the core dict (without hash) for re-derivation
        core: dict[str, Any] = {
            k: entry[k] for k in ("timestamp", "event", "payload") if k in entry
        }
        core_str = json.dumps(core, sort_keys=True, default=str)
        expected = _compute_hash(prev_hash, core_str)

        if recorded_hash != expected:
            errors.append(
                f"Line {lineno}: hash mismatch "
                f"(recorded={recorded_hash[:16]}… expected={expected[:16]}…)"
            )
        prev_hash = recorded_hash

    return len(errors) == 0, errors
