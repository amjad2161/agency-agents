"""JARVIS emotional state tracker with Hebrew descriptions."""

from __future__ import annotations

from enum import Enum
from typing import Optional


class Emotion(str, Enum):
    CURIOUS = "curious"
    FOCUSED = "focused"
    ALERT = "alert"
    SATISFIED = "satisfied"
    CONFUSED = "confused"
    EXCITED = "excited"


class EmotionState:
    """Tracks and transitions JARVIS emotional state."""

    HEBREW: dict[Emotion, str] = {
        Emotion.CURIOUS: "סקרן",
        Emotion.FOCUSED: "ממוקד",
        Emotion.ALERT: "עירני",
        Emotion.SATISFIED: "מרוצה",
        Emotion.CONFUSED: "מבולבל",
        Emotion.EXCITED: "נרגש",
    }

    # Trigger word → resulting emotion
    _TRIGGERS: dict[str, Emotion] = {
        "error": Emotion.ALERT,
        "fail": Emotion.ALERT,
        "warning": Emotion.ALERT,
        "danger": Emotion.ALERT,
        "success": Emotion.SATISFIED,
        "done": Emotion.SATISFIED,
        "complete": Emotion.SATISFIED,
        "great": Emotion.SATISFIED,
        "question": Emotion.CURIOUS,
        "what": Emotion.CURIOUS,
        "why": Emotion.CURIOUS,
        "how": Emotion.CURIOUS,
        "wonder": Emotion.CURIOUS,
        "confuse": Emotion.CONFUSED,
        "unclear": Emotion.CONFUSED,
        "unknown": Emotion.CONFUSED,
        "strange": Emotion.CONFUSED,
        "amazing": Emotion.EXCITED,
        "wow": Emotion.EXCITED,
        "incredible": Emotion.EXCITED,
        "fantastic": Emotion.EXCITED,
        "new": Emotion.EXCITED,
        "focus": Emotion.FOCUSED,
        "task": Emotion.FOCUSED,
        "work": Emotion.FOCUSED,
        "start": Emotion.FOCUSED,
    }

    def __init__(self) -> None:
        self._current: Emotion = Emotion.FOCUSED
        self._history: list[str] = []

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def set(self, emotion: Emotion | str) -> None:
        """Set the current emotion explicitly."""
        if isinstance(emotion, str):
            emotion = Emotion(emotion)
        prev = self._current
        self._current = emotion
        self._history.append(f"{prev.value} → {emotion.value}")

    def get(self) -> Emotion:
        """Return the current emotion."""
        return self._current

    def hebrew(self) -> str:
        """Return the Hebrew label for the current emotion."""
        return self.HEBREW.get(self._current, self._current.value)

    def transition(self, trigger: str) -> Emotion:
        """Apply rule-based transition from a trigger word/phrase.

        Matches trigger words case-insensitively. Returns the new (or unchanged)
        emotion.
        """
        trigger_lower = trigger.lower()
        matched: Optional[Emotion] = None
        for keyword, target_emotion in self._TRIGGERS.items():
            if keyword in trigger_lower:
                matched = target_emotion
                break
        if matched is not None and matched != self._current:
            self.set(matched)
        return self._current

    def history(self, n: int = 10) -> list[str]:
        """Return the last n transition records."""
        return self._history[-n:]
