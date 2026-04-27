"""Character State — live runtime state for the JARVIS persona.

Tracks current operating mode, session context, interaction history,
mood, and per-domain expertise usage. Persisted to disk so state
survives restarts (e.g. total_interactions counter, expertise_history).

Usage::

    state = CharacterState.get_instance()
    state.set_mode("executor")
    state.record_interaction("mathematics")
    print(state.snapshot())
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_STATE_PATH = Path(__file__).parent.parent / "data" / "character_state.json"

# Valid moods and modes
VALID_MOODS = frozenset({"focused", "alert", "standby", "engaged", "guardian"})
VALID_MODES = frozenset(
    {"supreme_brainiac", "academic", "executor", "guardian", "casual", "default"}
)


@dataclass
class CharacterState:
    """Mutable JARVIS runtime state (singleton pattern).

    Attributes
    ----------
    current_mode:
        Active persona mode (``"supreme_brainiac"``, ``"academic"``,
        ``"executor"``, ``"guardian"``, ``"casual"``).
    session_context:
        Recent interaction dicts ``{"role": ..., "content": ...}``.
    owner_name:
        Always ``"Amjad"`` unless explicitly overridden.
    active_since:
        Datetime the current session started.
    total_interactions:
        Persisted count of all-time interactions.
    expertise_history:
        Domain → count of times routed to that domain.
    mood:
        Current emotional baseline (``"focused"``, ``"alert"``,
        ``"standby"``, ``"engaged"``, ``"guardian"``).
    state_path:
        Path where state is persisted.
    """

    current_mode: str = "supreme_brainiac"
    session_context: list[dict[str, Any]] = field(default_factory=list)
    owner_name: str = "Amjad"
    active_since: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    total_interactions: int = 0
    expertise_history: dict[str, int] = field(default_factory=dict)
    mood: str = "focused"
    state_path: Path = field(default_factory=lambda: _DEFAULT_STATE_PATH)

    # --- Singleton ---
    _instance: "CharacterState | None" = field(
        default=None, init=False, repr=False, compare=False
    )

    # ------------------------------------------------------------------
    @classmethod
    def get_instance(
        cls,
        state_path: Path | str | None = None,
        *,
        force_new: bool = False,
    ) -> "CharacterState":
        """Return (or create) the process-level singleton.

        Parameters
        ----------
        state_path:
            Override the default persistence path.
        force_new:
            If ``True``, discard any existing singleton and create a
            fresh one (useful in tests).
        """
        if force_new or cls._instance is None:
            resolved = (
                Path(state_path)
                if state_path
                else cls._resolve_state_path()
            )
            inst = cls(state_path=resolved)
            inst._load()
            cls._instance = inst
        return cls._instance  # type: ignore[return-value]

    @classmethod
    def reset_singleton(cls) -> None:
        """Clear the singleton (test helper)."""
        cls._instance = None

    # ------------------------------------------------------------------
    def set_mode(self, mode: str) -> None:
        """Switch active persona mode."""
        if mode not in VALID_MODES:
            raise ValueError(
                f"Unknown mode {mode!r}. Valid: {sorted(VALID_MODES)}"
            )
        self.current_mode = mode

    def set_mood(self, mood: str) -> None:
        """Set mood; must be one of VALID_MOODS."""
        if mood not in VALID_MOODS:
            raise ValueError(
                f"Unknown mood {mood!r}. Valid: {sorted(VALID_MOODS)}"
            )
        self.mood = mood

    def add_context(self, role: str, content: str, max_ctx: int = 50) -> None:
        """Append an interaction to session_context (rolling window)."""
        self.session_context.append({"role": role, "content": content})
        if len(self.session_context) > max_ctx:
            self.session_context = self.session_context[-max_ctx:]

    def record_interaction(self, domain: str = "general") -> None:
        """Increment total_interactions and expertise_history for domain."""
        self.total_interactions += 1
        self.expertise_history[domain] = (
            self.expertise_history.get(domain, 0) + 1
        )
        self._save()

    def top_domains(self, n: int = 5) -> list[tuple[str, int]]:
        """Return the top-n domains by interaction count."""
        sorted_items = sorted(
            self.expertise_history.items(), key=lambda x: x[1], reverse=True
        )
        return sorted_items[:n]

    def session_length(self) -> int:
        """Number of turns in the current session context."""
        return len(self.session_context)

    def clear_session(self) -> None:
        """Wipe in-memory session context (does not touch persisted data)."""
        self.session_context = []

    def uptime_seconds(self) -> float:
        """Seconds since active_since."""
        return (datetime.now(timezone.utc).replace(tzinfo=None) - self.active_since).total_seconds()

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serialisable snapshot of current state."""
        return {
            "current_mode": self.current_mode,
            "owner_name": self.owner_name,
            "active_since": self.active_since.isoformat(),
            "total_interactions": self.total_interactions,
            "expertise_history": dict(self.expertise_history),
            "mood": self.mood,
            "session_length": self.session_length(),
            "top_domains": self.top_domains(3),
        }

    # ------------------------------------------------------------------
    def _save(self) -> None:
        """Persist counters to disk (non-fatal on failure)."""
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "total_interactions": self.total_interactions,
                "expertise_history": self.expertise_history,
                "mood": self.mood,
                "current_mode": self.current_mode,
                "owner_name": self.owner_name,
                "active_since": self.active_since.isoformat(),
            }
            self.state_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _load(self) -> None:
        """Load persisted counters from disk."""
        try:
            if self.state_path.exists():
                raw = self.state_path.read_text(encoding="utf-8")
                data = json.loads(raw) if raw.strip() else {}
                self.total_interactions = int(
                    data.get("total_interactions", 0)
                )
                self.expertise_history = dict(
                    data.get("expertise_history", {})
                )
                mood = data.get("mood", "focused")
                self.mood = mood if mood in VALID_MOODS else "focused"
                mode = data.get("current_mode", "supreme_brainiac")
                self.current_mode = (
                    mode if mode in VALID_MODES else "supreme_brainiac"
                )
                self.owner_name = data.get("owner_name", "Amjad")
                raw_ts = data.get("active_since")
                if raw_ts:
                    try:
                        self.active_since = datetime.fromisoformat(raw_ts)
                    except Exception:
                        pass
        except Exception:
            pass  # Corrupt state file — start fresh

    @staticmethod
    def _resolve_state_path() -> Path:
        env = os.environ.get("JARVIS_STATE_PATH")
        if env:
            return Path(env)
        return _DEFAULT_STATE_PATH


__all__ = ["CharacterState", "VALID_MODES", "VALID_MOODS"]
