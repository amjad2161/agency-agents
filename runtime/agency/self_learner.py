"""Conversation-based self-learning: extracts insights and stores them in LTM."""

from __future__ import annotations

import re
from typing import Optional

from .long_term_memory import LongTermMemory

# Phrases that signal an insight worth remembering
_INSIGHT_PATTERNS = re.compile(
    r"\b(always|never|prefer|remember(?: that)?|important(?:ly)?|"
    r"note that|keep in mind|make sure|be careful|avoid|use)\b",
    re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


class ConversationLearner:
    """Extracts insights from conversation turns and stores them in LTM."""

    def __init__(self, ltm: Optional[LongTermMemory] = None) -> None:
        self._ltm = ltm or LongTermMemory()

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def extract_insights(self, user_msg: str, assistant_msg: str) -> list[str]:
        """Heuristically find sentences containing insight keywords.

        Checks both user and assistant messages; deduplicates results.
        """
        combined = f"{user_msg}\n{assistant_msg}"
        sentences = _SENTENCE_SPLIT.split(combined)
        insights: list[str] = []
        seen: set[str] = set()
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if _INSIGHT_PATTERNS.search(sentence):
                key = sentence.lower()
                if key not in seen:
                    seen.add(key)
                    insights.append(sentence)
        return insights

    def learn_from_turn(self, user_msg: str, assistant_msg: str) -> int:
        """Extract insights and persist to LTM. Returns count stored."""
        insights = self.extract_insights(user_msg, assistant_msg)
        for insight in insights:
            self._ltm.store(insight, category="conversation_insight")
        return len(insights)

    def get_relevant_context(self, query: str) -> str:
        """Search LTM for relevant memories and format as context string."""
        results = self._ltm.search(query, limit=5)
        if not results:
            # Fall back to recent memories if FTS finds nothing
            results = self._ltm.recall(limit=5)
        if not results:
            return ""
        lines = ["[Relevant context from memory:]"]
        for r in results:
            cat = r.get("category", "")
            content = r.get("content", "")
            lines.append(f"- [{cat}] {content}")
        return "\n".join(lines)
