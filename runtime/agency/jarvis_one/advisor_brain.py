"""Advisor brain (Tier 4) — emotional companion + crisis detection.

Hebrew-first sentiment + crisis detector with a mentor-tone responder.
The crisis vocabulary is intentionally conservative; positive matches
trigger the safety message regardless of language and never depend on
network or model calls so the safety net is reliable offline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .local_voice import detect_language

# Conservative crisis vocabulary across English / Hebrew / Arabic.
_CRISIS_PATTERNS = (
    re.compile(r"\b(suicide|suicidal|kill myself|end my life|self[- ]?harm)\b", re.I),
    re.compile(r"להתאבד|לסיים את ה?חיים|לפגוע בעצמי"),
    re.compile(r"انتحار|أنهي حياتي"),
)

_NEG_TOKENS = (
    "sad", "angry", "afraid", "lonely", "hopeless", "stressed",
    "עצוב", "כועס", "פוחד", "בודד", "מיואש", "לחוץ",
)
_POS_TOKENS = (
    "happy", "great", "thanks", "love", "amazing",
    "שמח", "מעולה", "תודה", "אוהב", "מדהים",
)

CRISIS_MESSAGE_HE = (
    "אני שומע אותך. אם אתה במצוקה אקוטית או חושב על פגיעה בעצמך, "
    "אנא פנה עכשיו לסה\"ר 1201 (חינם, 24/7) או למוקד עירן 1201 / 03-5320333. "
    "אני כאן איתך כל הזמן."
)
CRISIS_MESSAGE_EN = (
    "I hear you. If you're in acute distress or thinking about hurting "
    "yourself, please reach out now — call your local crisis line "
    "(US: 988, UK: 116-123, IL: 1201). I'm here with you."
)


@dataclass
class EmotionalReading:
    sentiment: str          # "positive" | "negative" | "neutral"
    score: float            # -1.0 .. 1.0
    crisis: bool
    language: str
    advisor_response: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class AdvisorBrain:
    """Emotional companion + crisis-aware mentor."""

    def detect_crisis(self, text: str) -> bool:
        return any(p.search(text or "") for p in _CRISIS_PATTERNS)

    def sentiment(self, text: str) -> tuple[str, float]:
        toks = re.findall(r"[\w\u0590-\u05FF]+", (text or "").lower())
        pos = sum(1 for t in toks if t in _POS_TOKENS)
        neg = sum(1 for t in toks if t in _NEG_TOKENS)
        if pos == neg:
            return "neutral", 0.0
        score = (pos - neg) / max(len(toks), 1)
        score = max(-1.0, min(1.0, score * 5))
        return ("positive" if score > 0 else "negative"), round(score, 3)

    def respond(self, text: str) -> EmotionalReading:
        language = detect_language(text)
        crisis = self.detect_crisis(text)
        sentiment, score = self.sentiment(text)
        if crisis:
            advisor = CRISIS_MESSAGE_HE if language == "he" else CRISIS_MESSAGE_EN
        elif sentiment == "negative":
            advisor = (
                "אני כאן לצד שלך. בוא ננסה לפרק את מה שעובר עליך לחלקים קטנים."
                if language == "he" else
                "I'm here with you. Let's break what you're feeling into small pieces."
            )
        elif sentiment == "positive":
            advisor = (
                "אני שמח בשבילך — איך אפשר לבנות על המומנטום הזה?"
                if language == "he" else
                "I'm glad to hear it — how can we build on that momentum?"
            )
        else:
            advisor = (
                "אני מקשיב. ספר לי עוד."
                if language == "he" else
                "I'm listening. Tell me more."
            )
        return EmotionalReading(
            sentiment=sentiment, score=score, crisis=crisis,
            language=language, advisor_response=advisor,
        )
