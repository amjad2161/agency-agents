"""Pass-24 decision engine.

Confidence-based router. Given a user message, returns either a routed
intent (skill slug + confidence) or a Hebrew clarification request when the
confidence threshold is not met.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from ..skills import SkillRegistry

_HEBREW = re.compile(r"[\u0590-\u05FF]")


@dataclass
class DecisionRule:
    keywords: tuple[str, ...]
    skill_slug: str
    weight: float = 1.0


@dataclass
class Decision:
    skill: str | None
    confidence: float
    needs_clarification: bool = False
    clarification: str = ""
    candidates: list[tuple[str, float]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill": self.skill,
            "confidence": round(self.confidence, 3),
            "needs_clarification": self.needs_clarification,
            "clarification": self.clarification,
            "candidates": [{"skill": s, "score": round(c, 3)}
                           for s, c in self.candidates],
        }


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[\w\u0590-\u05FF]+", text or "")}


class DecisionEngine:
    """Confidence-based router with Hebrew-aware clarification."""

    def __init__(self, registry: SkillRegistry,
                 rules: Iterable[DecisionRule] | None = None,
                 *, threshold: float = 0.25) -> None:
        self.registry = registry
        self.threshold = threshold
        self.rules: list[DecisionRule] = list(rules or [])

    # ------------------------------------------------------------------
    def add_rule(self, rule: DecisionRule) -> None:
        self.rules.append(rule)

    def route(self, message: str) -> Decision:
        scores: dict[str, float] = {}
        msg_tokens = _tokens(message)

        # Rule-based pass.
        for rule in self.rules:
            hits = sum(1 for kw in rule.keywords if kw.lower() in msg_tokens)
            if hits:
                scores[rule.skill_slug] = scores.get(rule.skill_slug, 0.0) + (
                    hits / max(len(rule.keywords), 1)
                ) * rule.weight

        # Fallback: name/description token overlap with each skill.
        for skill in self.registry.all():
            blob = _tokens(f"{skill.name} {skill.description} {skill.slug}")
            if not blob:
                continue
            overlap = len(msg_tokens & blob) / max(len(blob | msg_tokens), 1)
            if overlap:
                scores[skill.slug] = max(scores.get(skill.slug, 0.0), overlap * 0.6)

        ranked = sorted(scores.items(), key=lambda x: -x[1])[:5]
        if not ranked:
            return Decision(
                skill=None, confidence=0.0, needs_clarification=True,
                clarification=self._clarify(message),
            )
        best_slug, best_score = ranked[0]
        if best_score < self.threshold:
            return Decision(
                skill=best_slug, confidence=best_score,
                needs_clarification=True,
                clarification=self._clarify(message),
                candidates=ranked,
            )
        return Decision(
            skill=best_slug, confidence=best_score,
            candidates=ranked,
        )

    def _clarify(self, message: str) -> str:
        if _HEBREW.search(message or ""):
            return "אני לא בטוח לאן לנתב את הבקשה. תוכל לפרט מה בדיוק לבצע?"
        return "I'm not sure where to route that. Could you add more detail?"
