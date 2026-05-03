"""Cross-session lessons journal.

Companion to `profile.py`. Where the profile says *who the user is and
how they want to work*, the lessons file says *what we've learned
together over time*: standing corrections, things that worked,
things that cost more than they should have, never-agains.

`~/.agency/lessons.md` (or wherever `AGENCY_LESSONS` points) is loaded
on every executor instantiation — same lazy-load pattern as the
profile — and injected as an additional system block. The persona
keeps the cache_control breakpoint, so lessons are part of the cached
prefix: free on cache reads, growing slowly over time.

The agent can append to this file with the regular `write_file` /
shell tools; there's no separate "memory" tool. That's by design —
the lessons are just text in a file, the user can edit them in any
editor, and the same trust-mode rules apply as for any other path
under `~/.agency/`.
"""

from __future__ import annotations

import os
from pathlib import Path

LESSONS_FILENAME = "lessons.md"
# Larger cap than the profile because lessons accumulate. Still bounded so
# a runaway journal doesn't make every API call expensive.
MAX_LESSONS_BYTES = 64_000


def lessons_path() -> Path:
    """Resolved location of the lessons file. May not exist yet."""
    override = os.environ.get("AGENCY_LESSONS")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".agency" / LESSONS_FILENAME


def load_lessons_text(path: Path | None = None) -> str | None:
    """Return the lessons body (trimmed) or None if absent / empty / unreadable.

    If the file exceeds `MAX_LESSONS_BYTES` we keep the *tail* (the most
    recent lessons matter more than ancient ones) and prepend a marker
    so the agent knows there's history beyond what it sees.
    """
    p = path or lessons_path()
    try:
        if not p.is_file():
            return None
        size = p.stat().st_size
        with p.open("rb") as f:
            if size > MAX_LESSONS_BYTES:
                # Read the last MAX_LESSONS_BYTES bytes — recency wins.
                f.seek(size - MAX_LESSONS_BYTES)
                raw = f.read()
                truncated = True
            else:
                raw = f.read()
                truncated = False
    except OSError:
        return None
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    if truncated:
        return (
            "[lessons file truncated — older entries omitted, "
            "showing most recent]\n\n" + text
        )
    return text


LESSONS_TEMPLATE = """\
# Lessons learned

<!-- Cross-session memory for the agent. The agent reads this at the
     start of every session and may append to it at the end. You can
     edit any entry by hand. Newer entries at the bottom; the agent
     auto-trims the file from the front when it gets too big. -->

## <YYYY-MM-DD HH:MM> · example entry — delete me

WORKED:    The format `## <date> · <topic>` is what the loader expects.
COST:      —
NEVER-AGAIN: —
NEXT-TIME: Replace this stub with real lessons after the first session.
"""


def ensure_default_lessons(path: Path | None = None) -> Path:
    """Create the lessons file with a starter template if it doesn't exist."""
    p = path or lessons_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        if not p.is_file():
            raise ValueError(
                f"Lessons path exists but is not a regular file: {p}"
            )
        return p
    p.write_text(LESSONS_TEMPLATE, encoding="utf-8")
    return p
