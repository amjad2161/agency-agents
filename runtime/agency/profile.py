"""User-level profile context.

The runtime loads `~/.agency/profile.md` (or whatever `AGENCY_PROFILE`
points at) and prepends it as a system block before every persona's
body. The persona block keeps the cache_control breakpoint, so the
profile text is included in the cached prefix — stable across runs,
free on cache reads.

The profile is purely opt-in: if the file doesn't exist, nothing is
prepended and behavior is identical to before.
"""

from __future__ import annotations

import os
from pathlib import Path

PROFILE_FILENAME = "profile.md"
MAX_PROFILE_BYTES = 32_000  # safety cap


def profile_path() -> Path:
    """Resolved location of the profile file. May not exist yet."""
    override = os.environ.get("AGENCY_PROFILE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".agency" / PROFILE_FILENAME


def load_profile_text(path: Path | None = None) -> str | None:
    """Return the profile body (trimmed) or None if absent / empty / unreadable.

    If the file exceeds `MAX_PROFILE_BYTES` it's truncated and a marker is
    appended — the caller still gets text. We only read up to
    `MAX_PROFILE_BYTES + 1` bytes from disk so a giant file doesn't spike
    memory in server mode where a new Executor is instantiated per request.
    """
    p = path or profile_path()
    try:
        if not p.is_file():
            return None
        with p.open("rb") as f:
            raw = f.read(MAX_PROFILE_BYTES + 1)
    except OSError:
        return None
    truncated = len(raw) > MAX_PROFILE_BYTES
    if truncated:
        raw = raw[:MAX_PROFILE_BYTES]
    text = raw.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return None
    if truncated:
        return text + "\n\n[profile truncated to fit]"
    return text


PROFILE_TEMPLATE = """\
# About me

<!-- Edit this file. Anything you put here is sent to every agent as
     background context. Keep it tight — every byte is in every prompt. -->

- Name:
- Role / context:
- Communication style:
- Tools / stacks I use:

# Things I always want

-

# Things I never want

-
"""


def ensure_default_profile(path: Path | None = None) -> Path:
    """Create the profile file with a starter template if it doesn't exist.

    Errors out cleanly (ValueError) if the configured path exists but isn't
    a regular file (e.g. someone pointed `AGENCY_PROFILE` at a directory) —
    silently skipping creation would lead to confusing failures downstream
    in `agency profile edit`.
    """
    p = path or profile_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        if not p.is_file():
            raise ValueError(f"Profile path exists but is not a regular file: {p}")
        return p
    p.write_text(PROFILE_TEMPLATE, encoding="utf-8")
    return p
