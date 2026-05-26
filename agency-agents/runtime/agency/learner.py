"""Self-learning engine — extracts facts from conversation turns.

After each conversation turn the Learner scans the exchange for:
  - Corrections  : "actually X is Y", "no, it's X", "wrong: X"
  - Preferences  : "I prefer X", "I like X", "use X instead"
  - Domain facts : "X is Y", "remember that X"
  - Name facts   : "my name is X", "call me X"

Extracted facts are stored in LongTermMemory.

Usage
-----
    learner = Learner()
    events = learner.process_turn(user_msg="Actually, the API key is abc123",
                                  assistant_msg="Noted.")
    # events is a list of LearningEvent

    # Manual trigger from CLI:
    #   agency learn
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import List, Optional

from .logging import get_logger
from .long_term_memory import LongTermMemory

log = get_logger()

# ---------------------------------------------------------------------------
# Patterns — ordered from most-specific to least-specific
# ---------------------------------------------------------------------------

_CORRECTION_PATTERNS: list[tuple[str, str]] = [
    # "actually X is Y"
    (r"actually[,\s]+(.{3,60})\s+is\s+(.{3,120})", "correction"),
    # "no,? it's X" / "no, X"
    (r"no[,!\s]+(?:it'?s\s+)?(.{3,80})", "correction"),
    # "wrong[,:]? X"
    (r"wrong[,:\s]+(.{3,80})", "correction"),
    # "not X[,;] it's Y"
    (r"not\s+(.{2,60})[,;]\s+it'?s\s+(.{3,80})", "correction"),
    # "that's wrong,? correct answer is X"
    (r"correct(?:\s+answer)?\s+is\s+(.{3,120})", "correction"),
]

_PREFERENCE_PATTERNS: list[tuple[str, str]] = [
    (r"i\s+prefer\s+(.{3,100})", "preference"),
    (r"i\s+like\s+(.{3,100})", "preference"),
    (r"use\s+(.{3,80})\s+instead", "preference"),
    (r"always\s+use\s+(.{3,80})", "preference"),
    (r"i\s+want\s+(?:you\s+to\s+)?(?:always\s+)?(.{3,100})", "preference"),
    (r"my\s+preference\s+is\s+(.{3,100})", "preference"),
    (r"i\s+hate\s+(.{3,80})", "preference"),
    (r"don'?t\s+(?:ever\s+)?(.{3,80})", "preference"),
]

_FACT_PATTERNS: list[tuple[str, str]] = [
    # "remember that X"
    (r"remember\s+that\s+(.{5,200})", "fact"),
    # "my name is X" / "call me X"
    (r"my\s+name\s+is\s+(\w+)", "profile.name"),
    (r"call\s+me\s+(\w+)", "profile.name"),
    # "I am a/an X" (role)
    (r"i\s+am\s+(?:a\s+|an\s+)(.{3,60})", "profile.role"),
    # "X is Y" (generic)
    (r"(.{3,60})\s+is\s+(.{3,120})", "fact"),
    # "the X is Y"
    (r"the\s+(.{3,60})\s+is\s+(.{3,120})", "fact"),
]

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class LearningEvent:
    fact_type: str          # correction | preference | fact | profile.name | …
    key: str                # memory key to store under
    value: str              # extracted value
    source: str             # "user" | "assistant"
    raw_text: str           # snippet that triggered this
    timestamp: float = field(default_factory=time.time)
    confidence: float = 1.0


# ---------------------------------------------------------------------------
# Learner
# ---------------------------------------------------------------------------


class Learner:
    """Extracts learnable facts from conversation turns and saves to LTM."""

    def __init__(self, memory: Optional[LongTermMemory] = None) -> None:
        self._memory = memory or LongTermMemory()
        self._total_events: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_turn(
        self,
        user_msg: str,
        assistant_msg: str = "",
        session_id: str = "",
    ) -> List[LearningEvent]:
        """Scan one conversation turn and persist extracted facts.

        Returns list of LearningEvent (empty if nothing learnable found).
        """
        events: List[LearningEvent] = []

        # Scan user message (higher priority — user is the authority)
        events.extend(self._extract(user_msg, source="user"))

        # Scan assistant message (lower priority — may contain confirmations)
        # Only extract profile/fact patterns from assistant, not corrections
        for evt in self._extract(assistant_msg, source="assistant"):
            if evt.fact_type in ("fact", "profile.name", "profile.role"):
                events.append(evt)

        # Dedup: same key → keep highest confidence
        deduped = _dedup_events(events)

        # Store to memory
        for evt in deduped:
            importance = 1.5 if evt.fact_type == "correction" else (
                1.2 if evt.fact_type.startswith("profile") else 1.0
            )
            self._memory.remember(
                key=evt.key,
                value=evt.value,
                tags=[evt.fact_type],
                importance=importance,
            )
            log.debug("learner.event type=%s key=%s", evt.fact_type, evt.key)

        self._total_events += len(deduped)
        return deduped

    def learn_from_history(self, sessions: List[dict]) -> int:
        """Process a list of history session dicts.

        Each session dict should have a "messages" list with
        {"role": "user"/"assistant", "content": str} entries.

        Returns total learning events extracted.
        """
        total = 0
        for session in sessions:
            messages = session.get("messages", [])
            for i, msg in enumerate(messages):
                if msg.get("role") == "user":
                    user_text = msg.get("content", "")
                    # find next assistant reply
                    asst_text = ""
                    if i + 1 < len(messages) and messages[i + 1].get("role") == "assistant":
                        asst_text = messages[i + 1].get("content", "")
                    evts = self.process_turn(user_text, asst_text)
                    total += len(evts)
        return total

    @property
    def total_events(self) -> int:
        return self._total_events

    # ------------------------------------------------------------------
    # Internal extraction
    # ------------------------------------------------------------------

    def _extract(self, text: str, source: str) -> List[LearningEvent]:
        if not text or len(text.strip()) < 5:
            return []

        events: List[LearningEvent] = []
        text_lower = text.lower().strip()

        # Corrections (only from user)
        if source == "user":
            for pattern, fact_type in _CORRECTION_PATTERNS:
                for m in re.finditer(pattern, text_lower):
                    groups = m.groups()
                    if len(groups) >= 2:
                        key = f"correction.{_slugify(groups[0])}"
                        value = groups[1].strip()
                    else:
                        key = f"correction.{_slugify(groups[0])}"
                        value = groups[0].strip()
                    if len(value) >= 3:
                        events.append(LearningEvent(
                            fact_type=fact_type,
                            key=key,
                            value=value,
                            source=source,
                            raw_text=m.group(0),
                            confidence=0.9,
                        ))

        # Preferences
        for pattern, fact_type in _PREFERENCE_PATTERNS:
            for m in re.finditer(pattern, text_lower):
                val = m.group(1).strip().rstrip(".,;")
                if len(val) >= 3:
                    key = f"pref.{_slugify(val)[:40]}"
                    events.append(LearningEvent(
                        fact_type=fact_type,
                        key=key,
                        value=val,
                        source=source,
                        raw_text=m.group(0),
                        confidence=0.85,
                    ))

        # Facts
        for pattern, fact_type in _FACT_PATTERNS:
            for m in re.finditer(pattern, text_lower):
                groups = m.groups()
                if fact_type == "profile.name" and groups:
                    name = groups[0].strip().title()
                    if len(name) >= 2:
                        events.append(LearningEvent(
                            fact_type=fact_type,
                            key="profile.name",
                            value=name,
                            source=source,
                            raw_text=m.group(0),
                            confidence=0.95,
                        ))
                elif fact_type == "profile.role" and groups:
                    role = groups[0].strip()
                    if len(role) >= 3:
                        events.append(LearningEvent(
                            fact_type=fact_type,
                            key="profile.role",
                            value=role,
                            source=source,
                            raw_text=m.group(0),
                            confidence=0.8,
                        ))
                elif fact_type == "fact" and len(groups) >= 2:
                    subject = groups[0].strip()
                    predicate = groups[1].strip().rstrip(".,;")
                    if len(subject) >= 2 and len(predicate) >= 2:
                        key = f"fact.{_slugify(subject)[:50]}"
                        value = f"{subject} is {predicate}"
                        events.append(LearningEvent(
                            fact_type=fact_type,
                            key=key,
                            value=value,
                            source=source,
                            raw_text=m.group(0),
                            confidence=0.7,
                        ))
                elif len(groups) == 1 and groups[0]:
                    val = groups[0].strip()
                    if len(val) >= 5:
                        key = f"fact.{_slugify(val)[:50]}"
                        events.append(LearningEvent(
                            fact_type="fact",
                            key=key,
                            value=val,
                            source=source,
                            raw_text=m.group(0),
                            confidence=0.7,
                        ))

        return events


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert text to a url/key-safe slug."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower().strip()).strip("_")[:60]


def _dedup_events(events: List[LearningEvent]) -> List[LearningEvent]:
    """Keep one event per key — highest confidence wins."""
    best: dict[str, LearningEvent] = {}
    for evt in events:
        if evt.key not in best or evt.confidence > best[evt.key].confidence:
            best[evt.key] = evt
    return list(best.values())
