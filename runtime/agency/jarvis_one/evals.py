"""Evaluation harness — inspired by DeepEval + RAGAS.

Lightweight quality scorer for LLM responses. Implements three reference
metrics (relevance, factuality_overlap, answer_length_within_target) plus
a pluggable interface so users can register custom metrics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

_TOKEN = re.compile(r"[\w\u0590-\u05FF]+", re.UNICODE)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text or "")}


@dataclass
class EvalCase:
    question: str
    expected: str | list[str]
    actual: str
    context: str = ""


# A metric returns a score 0.0..1.0 plus an optional reason.
Metric = Callable[[EvalCase], tuple[float, str]]


def relevance(case: EvalCase) -> tuple[float, str]:
    q, a = _tokens(case.question), _tokens(case.actual)
    if not q or not a:
        return 0.0, "empty input"
    overlap = len(q & a) / len(q | a)
    return round(overlap, 3), f"jaccard={overlap:.2f}"


def factuality_overlap(case: EvalCase) -> tuple[float, str]:
    expected = (
        case.expected if isinstance(case.expected, list) else [case.expected]
    )
    a = _tokens(case.actual)
    scores: list[float] = []
    for ref in expected:
        e = _tokens(ref)
        if not e:
            continue
        scores.append(len(e & a) / len(e))
    if not scores:
        return 0.0, "no expected text"
    best = max(scores)
    return round(best, 3), f"recall={best:.2f}"


def length_within_target(case: EvalCase, *, target: int = 200) -> tuple[float, str]:
    n = len(case.actual)
    if n == 0:
        return 0.0, "empty"
    ratio = min(n, target) / max(n, target)
    return round(ratio, 3), f"len={n} target={target}"


@dataclass
class EvalReport:
    case: EvalCase
    scores: dict[str, float] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)

    @property
    def overall(self) -> float:
        if not self.scores:
            return 0.0
        return round(sum(self.scores.values()) / len(self.scores), 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.case.question,
            "actual": self.case.actual,
            "scores": dict(self.scores),
            "reasons": dict(self.reasons),
            "overall": self.overall,
        }


class Evaluator:
    """Run a set of metrics over a list of cases."""

    def __init__(self) -> None:
        self.metrics: dict[str, Metric] = {
            "relevance": relevance,
            "factuality_overlap": factuality_overlap,
            "length_within_target": length_within_target,
        }

    def add(self, name: str, metric: Metric) -> None:
        self.metrics[name] = metric

    def evaluate(self, case: EvalCase) -> EvalReport:
        report = EvalReport(case=case)
        for name, metric in self.metrics.items():
            score, reason = metric(case)
            report.scores[name] = score
            report.reasons[name] = reason
        return report

    def evaluate_many(self, cases: list[EvalCase]) -> dict[str, Any]:
        reports = [self.evaluate(c) for c in cases]
        return {
            "count": len(reports),
            "average": round(
                sum(r.overall for r in reports) / max(len(reports), 1), 3
            ),
            "reports": [r.to_dict() for r in reports],
        }
