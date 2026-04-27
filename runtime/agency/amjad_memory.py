"""Amjad Memory — hard-wired knowledge about the owner.

JARVIS always knows who Amjad is, what he cares about, and how he
communicates. This module provides that baseline context so every
subsystem can personalise without re-loading profile files.

Dynamic updates are persisted to ``runtime/data/jarvis_preferences.json``
so preferences survive restarts.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Default location for the dynamic preference store.
_DEFAULT_PREFS_PATH = Path(__file__).parent.parent / "data" / "jarvis_preferences.json"


class AmjadMemory:
    """Owner context — hard-coded baseline plus dynamic overrides.

    Hard-coded facts are read-only structural knowledge about Amjad.
    Dynamic overrides allow JARVIS to learn preferences at runtime and
    persist them to disk so they survive restarts.

    Usage::

        mem = AmjadMemory()
        ctx = mem.get_context()
        mem.update("preferred_language", "hebrew")
    """

    # --- Hard-coded, immutable facts about the owner ---
    _HARD_FACTS: dict[str, Any] = {
        "name": "Amjad",
        "full_name": "Amjad Mobarsham",
        "email": "mobarsham@gmail.com",
        "preferred_language": "hebrew",
        "technical_language": "english",
        "work_style": "blunt, outcome-focused, no pleasantries, no fluff",
        "communication_mode": "dense, precise, Caveman-precision expert mode",
        "response_preferences": {
            "format": "bullet points or prose — no filler",
            "length": "minimal — conclusions first",
            "language": "Hebrew primary, English for technical terms",
            "tone": "professional, authoritative, no motivation speak",
        },
        "dislikes": [
            "wasted tokens",
            "repeated explanations",
            "errors and failures without diagnosis",
            "verbose output",
            "pleasantries",
            "motivational language",
            "emojis (unless requested)",
            "apologetic preambles",
            "uncertainty without evidence",
        ],
        "loves": [
            "autonomous execution",
            "zero-touch completion",
            "results with no drama",
            "dense technical output",
            "proactive suggestions",
            "Hebrew-first responses",
        ],
        "projects": [
            {
                "name": "J.A.R.V.I.S",
                "type": "AI personal agent",
                "repo": "amjad2161/agency-agents",
                "stack": "Python, Claude API, FastAPI",
            },
            {
                "name": "G.A.N.E NAVIGATOR",
                "type": "GPS navigation system",
                "description": "Planetary data matrix and autonomous system architecture",
            },
        ],
        "expertise_areas": [
            "AI systems",
            "software architecture",
            "autonomous agents",
            "navigation systems",
        ],
        "timezone": "Asia/Jerusalem",
        "location": "Israel",
    }

    def __init__(self, prefs_path: Path | str | None = None) -> None:
        self._prefs_path = (
            Path(prefs_path) if prefs_path else self._resolve_prefs_path()
        )
        self._dynamic: dict[str, Any] = {}
        self._load_dynamic()

    # ------------------------------------------------------------------
    def get_context(self) -> dict[str, Any]:
        """Return merged context: hard facts + dynamic overrides.

        Dynamic overrides shadow hard facts for the same key.
        """
        ctx: dict[str, Any] = dict(self._HARD_FACTS)
        ctx.update(self._dynamic)
        return ctx

    def get_hard_fact(self, key: str, default: Any = None) -> Any:
        """Read a hard-coded (immutable) fact."""
        return self._HARD_FACTS.get(key, default)

    def get(self, key: str, default: Any = None) -> Any:
        """Read from dynamic overrides first, then hard facts."""
        if key in self._dynamic:
            return self._dynamic[key]
        return self._HARD_FACTS.get(key, default)

    def update(self, key: str, value: Any) -> None:
        """Persist a dynamic preference override to disk."""
        self._dynamic[key] = value
        self._save_dynamic()

    def remove(self, key: str) -> None:
        """Remove a dynamic override (does not affect hard facts)."""
        self._dynamic.pop(key, None)
        self._save_dynamic()

    def reset_dynamic(self) -> None:
        """Clear all dynamic overrides."""
        self._dynamic = {}
        self._save_dynamic()

    def owner_name(self) -> str:
        return str(self.get("name", "Amjad"))

    def owner_email(self) -> str:
        return str(self.get("email", "mobarsham@gmail.com"))

    def primary_language(self) -> str:
        return str(self.get("preferred_language", "hebrew"))

    def dislikes(self) -> list[str]:
        val = self.get("dislikes")
        return list(val) if val else []

    def loves(self) -> list[str]:
        val = self.get("loves")
        return list(val) if val else []

    def projects(self) -> list[dict]:
        val = self.get("projects")
        return list(val) if val else []

    # ------------------------------------------------------------------
    def _load_dynamic(self) -> None:
        try:
            if self._prefs_path.exists():
                raw = self._prefs_path.read_text(encoding="utf-8")
                self._dynamic = json.loads(raw) if raw.strip() else {}
        except Exception:
            self._dynamic = {}

    def _save_dynamic(self) -> None:
        try:
            self._prefs_path.parent.mkdir(parents=True, exist_ok=True)
            self._prefs_path.write_text(
                json.dumps(self._dynamic, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass  # Disk write failures must never crash the agent

    @staticmethod
    def _resolve_prefs_path() -> Path:
        env = os.environ.get("JARVIS_PREFS_PATH")
        if env:
            return Path(env)
        return _DEFAULT_PREFS_PATH


# Process-level singleton
_singleton: AmjadMemory | None = None

# ---------------------------------------------------------------------------
# Process-level singleton
# ---------------------------------------------------------------------------

_singleton: AmjadMemory | None = None


def get_amjad_memory(prefs_path: Path | str | None = None) -> AmjadMemory:
    """Return (or create) the process-level AmjadMemory singleton."""
    global _singleton
    if _singleton is None:
        _singleton = AmjadMemory(prefs_path=prefs_path)
    return _singleton


def reset_amjad_memory() -> None:
    """Reset the singleton (for testing)."""
    global _singleton
    _singleton = None
