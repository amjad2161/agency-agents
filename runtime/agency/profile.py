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
    """Return the profile body (trimmed) or None if absent / empty / too big."""
    p = path or profile_path()
    try:
        if not p.is_file():
            return None
        raw = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    text = raw.strip()
    if not text:
        return None
    if len(text.encode("utf-8", errors="ignore")) > MAX_PROFILE_BYTES:
        # Refuse rather than silently send a giant prefix.
        return text.encode("utf-8", errors="ignore")[:MAX_PROFILE_BYTES].decode(
            "utf-8", errors="ignore"
        ) + "\n\n[profile truncated to fit]"
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
    """Create the profile file with a starter template if it doesn't exist."""
    p = path or profile_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(PROFILE_TEMPLATE, encoding="utf-8")
    return p
