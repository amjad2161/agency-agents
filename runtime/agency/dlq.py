"""Dead-letter queue for autonomous loop failures.

Failed iterations are appended to ~/.agency/dlq.jsonl.
Each entry records the timestamp, error, input, retry count, and status.

CLI:
    agency dlq          — list failed items
    agency dlq retry    — retry all retryable items
    agency dlq clear    — delete the DLQ file
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from .logging import get_logger

DEFAULT_DLQ_PATH = Path.home() / ".agency" / "dlq.jsonl"
MAX_RETRIES = 3

log = get_logger()


@dataclass
class DLQEntry:
    """One dead-letter record."""

    entry_id: str
    timestamp: float
    error: str
    input: str                      # the prompt / action that failed
    retry_count: int = 0
    status: str = "failed"          # failed | retrying | dead | resolved
    context: dict = field(default_factory=dict)

    @property
    def is_dead(self) -> bool:
        return self.retry_count >= MAX_RETRIES or self.status == "dead"

    @property
    def is_retryable(self) -> bool:
        return not self.is_dead and self.status != "resolved"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DLQEntry":
        return cls(
            entry_id=d.get("entry_id", str(uuid.uuid4())[:8]),
            timestamp=d.get("timestamp", time.time()),
            error=d.get("error", ""),
            input=d.get("input", ""),
            retry_count=d.get("retry_count", 0),
            status=d.get("status", "failed"),
            context=d.get("context", {}),
        )


class DeadLetterQueue:
    """Append-only dead-letter queue backed by a JSONL file.

    Usage::

        dlq = DeadLetterQueue()

        # Record a failure
        dlq.push("summarise news", error="TimeoutError: timed out")

        # List all entries
        entries = dlq.list_entries()

        # Retry all retryable entries
        def my_handler(prompt: str) -> None: ...

        dlq.retry_all(my_handler)
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or DEFAULT_DLQ_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ── public API ──────────────────────────────────────────────────────────

    def push(
        self,
        input_text: str,
        error: str,
        context: dict | None = None,
    ) -> DLQEntry:
        """Append a new failure to the DLQ and return the entry."""
        entry = DLQEntry(
            entry_id=str(uuid.uuid4())[:8],
            timestamp=time.time(),
            error=error,
            input=input_text,
            context=context or {},
        )
        self._append(entry)
        log.warning("dlq: pushed entry %s — %s", entry.entry_id, error[:80])
        return entry

    def list_entries(self, include_dead: bool = True) -> list[DLQEntry]:
        """Return all entries from the DLQ file."""
        entries: list[DLQEntry] = []
        if not self._path.exists():
            return entries
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(DLQEntry.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError):
                continue
        if not include_dead:
            entries = [e for e in entries if not e.is_dead]
        return entries

    def retry_all(
        self,
        handler: Callable[[str], None],
        max_entries: int = 100,
    ) -> tuple[int, int]:
        """Retry all retryable entries using *handler*.

        Returns (resolved_count, dead_count).
        """
        entries = self.list_entries()
        retryable = [e for e in entries if e.is_retryable][:max_entries]
        resolved = 0
        dead = 0

        updated: dict[str, DLQEntry] = {e.entry_id: e for e in entries}

        for entry in retryable:
            entry.retry_count += 1
            entry.status = "retrying"
            log.info("dlq: retrying %s (attempt %d)", entry.entry_id, entry.retry_count)
            try:
                handler(entry.input)
                entry.status = "resolved"
                resolved += 1
                log.info("dlq: resolved %s", entry.entry_id)
            except Exception as exc:  # noqa: BLE001
                entry.error = f"{type(exc).__name__}: {exc}"
                if entry.retry_count >= MAX_RETRIES:
                    entry.status = "dead"
                    dead += 1
                    log.warning("dlq: entry %s marked dead after %d retries",
                                entry.entry_id, entry.retry_count)
                else:
                    entry.status = "failed"
            updated[entry.entry_id] = entry

        self._rewrite(list(updated.values()))
        return resolved, dead

    def retry_one(
        self,
        entry_id: str,
        handler: Callable[[str], None],
    ) -> DLQEntry | None:
        """Retry a single entry by ID. Returns the updated entry or None."""
        entries = self.list_entries()
        updated: dict[str, DLQEntry] = {e.entry_id: e for e in entries}
        entry = updated.get(entry_id)
        if entry is None or not entry.is_retryable:
            return entry

        entry.retry_count += 1
        entry.status = "retrying"
        try:
            handler(entry.input)
            entry.status = "resolved"
        except Exception as exc:  # noqa: BLE001
            entry.error = f"{type(exc).__name__}: {exc}"
            entry.status = "dead" if entry.retry_count >= MAX_RETRIES else "failed"

        updated[entry_id] = entry
        self._rewrite(list(updated.values()))
        return entry

    def clear(self) -> int:
        """Delete the DLQ file. Returns number of entries that were in it."""
        entries = self.list_entries()
        n = len(entries)
        if self._path.exists():
            self._path.unlink()
        return n

    def summary(self) -> dict:
        """Return counts by status."""
        entries = self.list_entries()
        counts: dict[str, int] = {}
        for e in entries:
            counts[e.status] = counts.get(e.status, 0) + 1
        counts["total"] = len(entries)
        return counts

    # ── internals ───────────────────────────────────────────────────────────

    def _append(self, entry: DLQEntry) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    def _rewrite(self, entries: list[DLQEntry]) -> None:
        """Rewrite the entire DLQ file with updated entries."""
        with self._path.open("w", encoding="utf-8") as fh:
            for e in entries:
                fh.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")
