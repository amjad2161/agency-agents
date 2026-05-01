"""Audit log with hash-chain for tamper detection."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_DEFAULT_PATH = Path.home() / ".agency" / "audit.jsonl"


class AuditLog:
    """Append-only audit log stored as JSONL with a running SHA-256 chain hash.

    Each entry contains:
        ts    — ISO 8601 UTC timestamp
        event — event name string
        data  — arbitrary dict payload
        hash  — SHA-256( prev_hash + JSON(ts+event+data) )

    This makes retroactive tampering detectable via ``verify_chain()``.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path else _DEFAULT_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(self, event: str, data: dict[str, Any] | None = None) -> dict:
        """Append a new entry; returns the stored entry dict."""
        data = data or {}
        prev_hash = self._last_hash()
        ts = datetime.now(timezone.utc).isoformat()
        entry_core = json.dumps({"ts": ts, "event": event, "data": data},
                                sort_keys=True)
        chain_hash = hashlib.sha256(
            (prev_hash + entry_core).encode()
        ).hexdigest()
        entry = {"ts": ts, "event": event, "data": data, "hash": chain_hash}
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def verify_chain(self) -> bool:
        """Return True if every entry's hash is consistent with its predecessor."""
        prev_hash = ""
        for line in self._read_lines():
            entry = json.loads(line)
            ts = entry["ts"]
            event = entry["event"]
            data = entry["data"]
            stored_hash = entry["hash"]
            entry_core = json.dumps({"ts": ts, "event": event, "data": data},
                                    sort_keys=True)
            expected = hashlib.sha256(
                (prev_hash + entry_core).encode()
            ).hexdigest()
            if expected != stored_hash:
                return False
            prev_hash = stored_hash
        return True

    def tail(self, n: int = 10) -> list[dict]:
        """Return the last *n* entries as dicts."""
        lines = self._read_lines()
        last = lines[-n:] if len(lines) >= n else lines
        return [json.loads(line) for line in last]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _read_lines(self) -> list[str]:
        try:
            return [
                ln for ln in self._path.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
        except FileNotFoundError:
            return []

    def _last_hash(self) -> str:
        lines = self._read_lines()
        if not lines:
            return ""
        try:
            return json.loads(lines[-1])["hash"]
        except (json.JSONDecodeError, KeyError):
            return ""
