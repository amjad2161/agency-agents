"""Chat history persistence for agency runtime.

After each `agency chat` session, conversations are saved to
~/.agency/history/YYYY-MM-DD_HHMMSS.jsonl — one JSON object per line
with keys: role, content, timestamp.

The `agency history` command lists recent sessions and lets the user
replay one.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def history_dir() -> Path:
    """Return ~/.agency/history, creating it if absent."""
    d = Path.home() / ".agency" / "history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_session_path() -> Path:
    """Return a path for a new session file, named with current UTC timestamp."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    return history_dir() / f"{stamp}.jsonl"


# ---------------------------------------------------------------------------
# Session writer (used inside chat loop)
# ---------------------------------------------------------------------------

class HistoryWriter:
    """Appends messages to a JSONL file for one chat session.

    Usage::

        with HistoryWriter() as hw:
            hw.append("user", "hello")
            hw.append("assistant", "hi!")
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path: Path = path or new_session_path()
        self._fh = None

    @property
    def path(self) -> Path:
        return self._path

    def __enter__(self) -> "HistoryWriter":
        self._fh = self._path.open("a", encoding="utf-8")
        return self

    def __exit__(self, *_: object) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def append(self, role: str, content: str) -> None:
        """Append one message to the session file."""
        record = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        line = json.dumps(record, ensure_ascii=False)
        if self._fh is not None:
            self._fh.write(line + "\n")
            self._fh.flush()
        else:
            # Fallback: append without context manager
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


# ---------------------------------------------------------------------------
# Reading / listing history
# ---------------------------------------------------------------------------

def list_sessions(limit: int = 20) -> list[Path]:
    """Return the most recent *limit* session files, newest first."""
    files = sorted(history_dir().glob("*.jsonl"), reverse=True)
    return files[:limit]


def read_session(path: Path) -> list[dict]:
    """Parse a JSONL session file and return a list of message dicts."""
    messages: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return messages


def session_summary(path: Path) -> str:
    """Return a one-line summary of a session file.

    Format:  YYYY-MM-DD HH:MM  (N turns)  first user message…
    """
    msgs = read_session(path)
    n = len(msgs)
    first_user = next(
        (m.get("content", "")[:60] for m in msgs if m.get("role") == "user"),
        "",
    )
    stem = path.stem  # YYYY-MM-DD_HHMMSS
    date_part = stem.replace("_", " ").replace("-", "-")
    return f"{date_part}  ({n} turns)  {first_user!r}"
