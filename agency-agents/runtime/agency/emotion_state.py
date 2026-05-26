"""Emotion / State system — Pass 21.

Gives JARVIS an internal emotional model that evolves based on conversation
context and affects its response style (via JarvisPersonality).

Classes
-------
    EmotionState       — 6-value enum
    JarvisEmotion      — stateful emotion tracker with Hebrew responses

Usage (library)
---------------
    from agency.emotion_state import JarvisEmotion, EmotionState

    emotion = JarvisEmotion()
    emotion.update("question")
    print(emotion.current)        # EmotionState.CURIOUS
    print(emotion.phrase())       # "מעניין!"
    style = emotion.style_hint()  # dict used by JarvisPersonality

CLI
---
    agency emotion          show current emotional state
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------

class EmotionState(str, Enum):
    """JARVIS emotional states."""

    NEUTRAL   = "neutral"
    CURIOUS   = "curious"
    FOCUSED   = "focused"
    ALERT     = "alert"
    SATISFIED = "satisfied"
    UNCERTAIN = "uncertain"


# ---------------------------------------------------------------------------
# Trigger → state transitions
# ---------------------------------------------------------------------------

# Maps trigger keywords/types → (new_state, confidence_boost)
_TRIGGER_MAP: Dict[str, Tuple[EmotionState, float]] = {
    # Question triggers
    "question":     (EmotionState.CURIOUS,   0.85),
    "?":            (EmotionState.CURIOUS,   0.75),
    "what":         (EmotionState.CURIOUS,   0.70),
    "how":          (EmotionState.CURIOUS,   0.70),
    "why":          (EmotionState.CURIOUS,   0.80),
    "explain":      (EmotionState.CURIOUS,   0.80),
    "tell me":      (EmotionState.CURIOUS,   0.75),

    # Task / execution triggers
    "run":          (EmotionState.FOCUSED,   0.85),
    "execute":      (EmotionState.FOCUSED,   0.90),
    "build":        (EmotionState.FOCUSED,   0.85),
    "create":       (EmotionState.FOCUSED,   0.80),
    "generate":     (EmotionState.FOCUSED,   0.80),
    "write":        (EmotionState.FOCUSED,   0.75),
    "analyse":      (EmotionState.FOCUSED,   0.80),
    "analyze":      (EmotionState.FOCUSED,   0.80),
    "calculate":    (EmotionState.FOCUSED,   0.80),
    "compute":      (EmotionState.FOCUSED,   0.80),
    "task":         (EmotionState.FOCUSED,   0.75),

    # Error / alert triggers
    "error":        (EmotionState.ALERT,     0.90),
    "exception":    (EmotionState.ALERT,     0.90),
    "fail":         (EmotionState.ALERT,     0.85),
    "failed":       (EmotionState.ALERT,     0.85),
    "crash":        (EmotionState.ALERT,     0.90),
    "critical":     (EmotionState.ALERT,     0.95),
    "urgent":       (EmotionState.ALERT,     0.90),
    "warning":      (EmotionState.ALERT,     0.80),
    "danger":       (EmotionState.ALERT,     0.90),

    # Completion triggers
    "done":         (EmotionState.SATISFIED, 0.90),
    "complete":     (EmotionState.SATISFIED, 0.90),
    "completed":    (EmotionState.SATISFIED, 0.90),
    "finished":     (EmotionState.SATISFIED, 0.85),
    "task_complete":(EmotionState.SATISFIED, 0.95),
    "success":      (EmotionState.SATISFIED, 0.95),
    "solved":       (EmotionState.SATISFIED, 0.90),

    # Uncertainty triggers
    "unsure":       (EmotionState.UNCERTAIN, 0.80),
    "maybe":        (EmotionState.UNCERTAIN, 0.70),
    "not sure":     (EmotionState.UNCERTAIN, 0.75),
    "unclear":      (EmotionState.UNCERTAIN, 0.80),
    "ambiguous":    (EmotionState.UNCERTAIN, 0.80),
    "unknown":      (EmotionState.UNCERTAIN, 0.75),
    "not found":    (EmotionState.UNCERTAIN, 0.70),
}

# ---------------------------------------------------------------------------
# Hebrew phrases per state
# ---------------------------------------------------------------------------

_HEBREW_PHRASES: Dict[EmotionState, List[str]] = {
    EmotionState.NEUTRAL: [
        "כאן לשירותך",          # here to serve you
        "ממתין להוראות",         # awaiting instructions
        "מוכן",                  # ready
    ],
    EmotionState.CURIOUS: [
        "מעניין!",               # interesting!
        "שאלה טובה",             # good question
        "זה מרתק",               # this is fascinating
        "אחקור את זה",           # I'll investigate this
    ],
    EmotionState.FOCUSED: [
        "מתמקד במשימה",          # focusing on task
        "עובד על זה",            # working on it
        "ביצוע...",              # executing...
        "כל המשאבים מרוכזים",    # all resources focused
    ],
    EmotionState.ALERT: [
        "שים לב!",               # attention!
        "התראה חשובה",           # important alert
        "זוהתה בעיה",            # issue detected
        "נדרשת תשומת לב מיידית", # immediate attention required
    ],
    EmotionState.SATISFIED: [
        "כמובן",                 # of course / naturally
        "המשימה הושלמה",         # task completed
        "בוצע בהצלחה",           # executed successfully
        "עם כיף!",               # with pleasure!
    ],
    EmotionState.UNCERTAIN: [
        "איני בטוח",             # I'm not sure
        "צריך יותר מידע",        # need more information
        "יש מספר אפשרויות",      # there are several options
        "נדרש בירור נוסף",       # further clarification needed
    ],
}

# English phrases per state (fallback / bilingual)
_ENGLISH_PHRASES: Dict[EmotionState, List[str]] = {
    EmotionState.NEUTRAL:   ["Ready.", "Awaiting instructions.", "Standing by."],
    EmotionState.CURIOUS:   ["Interesting!", "Good question.", "Fascinating."],
    EmotionState.FOCUSED:   ["Focusing...", "On it.", "Executing."],
    EmotionState.ALERT:     ["Attention!", "Alert detected.", "Issue found."],
    EmotionState.SATISFIED: ["Done.", "Task complete.", "Completed successfully."],
    EmotionState.UNCERTAIN: ["Uncertain.", "Need more info.", "Clarification needed."],
}


# ---------------------------------------------------------------------------
# Emotion tracker
# ---------------------------------------------------------------------------

@dataclass
class EmotionEvent:
    """A recorded emotion transition."""
    trigger: str
    previous: EmotionState
    new_state: EmotionState
    confidence: float
    timestamp: float = field(default_factory=time.time)


class JarvisEmotion:
    """Stateful emotion tracker for JARVIS.

    Parameters
    ----------
    initial:
        Starting emotional state.
    decay_rate:
        Per-update decay toward NEUTRAL (0 = no decay, 1 = instant reset).
    language:
        ``'he'`` for Hebrew phrases, ``'en'`` for English.
    """

    def __init__(
        self,
        initial: EmotionState = EmotionState.NEUTRAL,
        decay_rate: float = 0.1,
        language: str = "he",
    ) -> None:
        self.current: EmotionState = initial
        self.confidence: float = 1.0
        self.decay_rate = decay_rate
        self.language = language
        self._history: List[EmotionEvent] = []
        self._update_count: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, trigger: str) -> EmotionState:
        """Update state based on *trigger* text/keyword.

        *trigger* can be a full sentence or a keyword.  The method scans
        for matching tokens in ``_TRIGGER_MAP`` and picks the match with the
        highest confidence.

        Returns the (possibly changed) :class:`EmotionState`.
        """
        trigger_lower = trigger.lower().strip()
        best_state: Optional[EmotionState] = None
        best_conf: float = 0.0

        # Check direct key match first
        for key, (state, conf) in _TRIGGER_MAP.items():
            if key in trigger_lower:
                if conf > best_conf:
                    best_conf = conf
                    best_state = state

        # Transition if we found a strong enough trigger (threshold: 0.60)
        if best_state is not None and best_conf >= 0.60:
            prev = self.current
            self.current = best_state
            self.confidence = best_conf
            self._history.append(EmotionEvent(
                trigger=trigger[:80],
                previous=prev,
                new_state=best_state,
                confidence=best_conf,
            ))
        else:
            # Gradual decay toward neutral when no trigger matched
            self.confidence = max(0.5, self.confidence * (1 - self.decay_rate))
            if self.confidence < 0.52:
                self.current = EmotionState.NEUTRAL
                self.confidence = 0.5

        self._update_count += 1
        return self.current

    def phrase(self, language: Optional[str] = None) -> str:
        """Return a random phrase matching the current state."""
        lang = language or self.language
        if lang == "he":
            pool = _HEBREW_PHRASES.get(self.current, [])
        else:
            pool = _ENGLISH_PHRASES.get(self.current, [])
        if not pool:
            return ""
        return random.choice(pool)

    def style_hint(self) -> Dict[str, Any]:
        """Return a style hint dict for use by JarvisPersonality.

        Example return::

            {
                "response_style": "verbose",
                "urgency": True,
                "tone": "formal",
            }
        """
        hints: Dict[str, Any] = {
            "state": self.current.value,
            "confidence": round(self.confidence, 2),
            "urgency": self.current == EmotionState.ALERT,
            "tone": "formal",
            "response_style": "concise",
        }
        if self.current == EmotionState.CURIOUS:
            hints["response_style"] = "verbose"
            hints["tone"] = "inquisitive"
        elif self.current == EmotionState.FOCUSED:
            hints["response_style"] = "concise"
            hints["tone"] = "technical"
        elif self.current == EmotionState.ALERT:
            hints["response_style"] = "concise"
            hints["tone"] = "urgent"
        elif self.current == EmotionState.SATISFIED:
            hints["response_style"] = "concise"
            hints["tone"] = "warm"
        elif self.current == EmotionState.UNCERTAIN:
            hints["response_style"] = "verbose"
            hints["tone"] = "cautious"
        return hints

    def apply_to_personality(self, personality: Any) -> None:
        """Mutate a JarvisPersonality based on the current emotional state.

        Requires a JarvisPersonality instance from agency.personality.
        No-op if the object doesn't match the expected interface.
        """
        try:
            hint = self.style_hint()
            if hasattr(personality, "response_style"):
                personality.response_style = hint.get("response_style", "concise")
        except Exception:
            pass

    def reset(self) -> None:
        """Reset to NEUTRAL state."""
        self.current = EmotionState.NEUTRAL
        self.confidence = 1.0
        self._history.clear()
        self._update_count = 0

    @property
    def history(self) -> List[EmotionEvent]:
        return list(self._history)

    @property
    def update_count(self) -> int:
        return self._update_count

    def __repr__(self) -> str:
        return (
            f"JarvisEmotion(state={self.current.value!r}, "
            f"confidence={self.confidence:.2f})"
        )
