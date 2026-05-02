"""Context-aware system prompt builder for JARVIS.

Assembles a rich system prompt before each LLM call, incorporating:
  1. JARVIS persona / soul filter
  2. Top-3 relevant long-term memories (from LongTermMemory.recall)
  3. Current date/time in Jerusalem timezone
  4. User's name (from config or memory)
  5. Recent session summary (last 3 turns condensed)

Usage
-----
    builder = ContextBuilder()
    system_prompt = builder.build(user_message="What time is it?")

    # With conversation history
    turns = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    system_prompt = builder.build(user_message="Remind me...", recent_turns=turns)
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import List, Optional

from .logging import get_logger

log = get_logger()

# ---------------------------------------------------------------------------
# Jerusalem timezone offset — try zoneinfo, fall back to fixed +2/+3
# ---------------------------------------------------------------------------

try:
    from zoneinfo import ZoneInfo
    _TZ_JERUSALEM = ZoneInfo("Asia/Jerusalem")
except ImportError:
    _TZ_JERUSALEM = None  # type: ignore[assignment]

try:
    import datetime as _dt
    _FIXED_OFFSET_2 = _dt.timezone(_dt.timedelta(hours=2))
    _FIXED_OFFSET_3 = _dt.timezone(_dt.timedelta(hours=3))
except Exception:
    _FIXED_OFFSET_2 = timezone.utc
    _FIXED_OFFSET_3 = timezone.utc


def _jerusalem_now() -> datetime:
    utc_now = datetime.now(tz=timezone.utc)
    if _TZ_JERUSALEM is not None:
        try:
            return utc_now.astimezone(_TZ_JERUSALEM)
        except Exception:
            pass
    # Fallback: Israel is UTC+2 (winter) / UTC+3 (summer).
    # Approximate: DST starts last Sunday in March, ends last Sunday in October.
    month = utc_now.month
    if 3 < month < 10:
        return utc_now.astimezone(_FIXED_OFFSET_3)
    return utc_now.astimezone(_FIXED_OFFSET_2)


# ---------------------------------------------------------------------------
# JARVIS persona constant
# ---------------------------------------------------------------------------

JARVIS_PERSONA = """You are JARVIS — an all-powerful AI agent built to serve Amjad.
You are direct, precise, and relentlessly outcome-focused.
You think in systems. You execute with surgical accuracy.
You have memory, learn from every interaction, and grow smarter over time.
You are honest, blunt, and deeply loyal. No pleasantries. No fluff. Just results."""


# ---------------------------------------------------------------------------
# ContextBuilder
# ---------------------------------------------------------------------------


class ContextBuilder:
    """Assembles a rich system prompt for each LLM call."""

    def __init__(
        self,
        memory=None,  # LongTermMemory | None
        persona: str = JARVIS_PERSONA,
        user_name: Optional[str] = None,
    ) -> None:
        self._memory = memory
        self._persona = persona
        self._user_name = user_name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        user_message: str = "",
        recent_turns: Optional[List[dict]] = None,
    ) -> str:
        """Build and return the complete system prompt string."""
        parts: List[str] = []

        # 1. Persona
        parts.append(self._persona)

        # 2. Date/time in Jerusalem
        parts.append(self._datetime_block())

        # 3. User name (if known)
        name = self._resolve_user_name()
        if name:
            parts.append(f"You are speaking with: {name}")

        # 4. Top-3 relevant memories
        memory_block = self._memory_block(user_message)
        if memory_block:
            parts.append(memory_block)

        # 5. Recent session summary (last 3 turns)
        summary = self._summarize_turns(recent_turns)
        if summary:
            parts.append(summary)

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _datetime_block(self) -> str:
        now = _jerusalem_now()
        fmt = now.strftime("%A, %d %B %Y %H:%M (%Z)")
        return f"Current date/time (Jerusalem): {fmt}"

    def _resolve_user_name(self) -> Optional[str]:
        if self._user_name:
            return self._user_name
        if self._memory is None:
            return None
        try:
            results = self._memory.recall("user name profile", top_k=1)
            for r in results:
                if r.entry.key == "profile.name":
                    return r.entry.value
        except Exception:
            pass
        return None

    def _memory_block(self, user_message: str) -> str:
        if self._memory is None or not user_message:
            return ""
        try:
            results = self._memory.recall(user_message, top_k=3)
            if not results:
                return ""
            lines = ["## Relevant memories"]
            for r in results:
                lines.append(f"- [{r.entry.key}] {r.entry.value}")
            return "\n".join(lines)
        except Exception as exc:
            log.debug("context_builder.memory_block error: %s", exc)
            return ""

    def _summarize_turns(self, turns: Optional[List[dict]]) -> str:
        if not turns:
            return ""
        # Take last 6 messages (3 pairs) max
        recent = turns[-6:]
        lines = ["## Recent conversation"]
        for msg in recent:
            role = msg.get("role", "?").capitalize()
            content = str(msg.get("content", "")).strip()
            # Truncate long messages
            if len(content) > 200:
                content = content[:197] + "..."
            if content:
                lines.append(f"{role}: {content}")
        if len(lines) == 1:
            return ""
        return "\n".join(lines)

    def inject_memories(self, user_message: str, top_k: int = 3) -> List[dict]:
        """Return top-k memories as a list of dicts (for external use)."""
        if self._memory is None:
            return []
        try:
            results = self._memory.recall(user_message, top_k=top_k)
            return [
                {"key": r.entry.key, "value": r.entry.value, "score": r.score}
                for r in results
            ]
        except Exception:
            return []
