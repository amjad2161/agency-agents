"""Evaluation framework — metrics, suite, report.

Inspired by DeepEval + RAGAS. Each metric returns a [0,1] score. The
suite runs all metrics over a list of cases and produces a report
with overall pass/fail based on a configurable threshold.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from .logging import get_logger

log = get_logger()


@dataclass
class EvalCase:
    """One evaluation case."""

    input: str
    expected_output: str = ""
    actual_output: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    latency_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvalMetric:
    """Base metric. Subclasses implement `score`."""

    name: str = "metric"

    def score(self, case: EvalCase) -> float:
        raise NotImplementedError

    def passes(self, score: float, threshold: float = 0.5) -> bool:
        return score >= threshold


class ExactMatch(EvalMetric):
    name = "exact_match"

    def __init__(self, case_sensitive: bool = False) -> None:
        self.case_sensitive = case_sensitive

    def score(self, case: EvalCase) -> float:
        a = case.actual_output if self.case_sensitive else case.actual_output.lower()
        b = case.expected_output if self.case_sensitive else case.expected_output.lower()
        return 1.0 if a.strip() == b.strip() else 0.0


class Contains(EvalMetric):
    name = "contains"

    def __init__(self, case_sensitive: bool = False) -> None:
        self.case_sensitive = case_sensitive

    def score(self, case: EvalCase) -> float:
        if not case.expected_output:
            return 1.0
        a = case.actual_output if self.case_sensitive else case.actual_output.lower()
        b = case.expected_output if self.case_sensitive else case.expected_output.lower()
        return 1.0 if b.strip() in a else 0.0


class LengthCheck(EvalMetric):
    name = "length_check"

    def __init__(self, min_chars: int = 0, max_chars: int = 100_000) -> None:
        self.min_chars = min_chars
        self.max_chars = max_chars

    def score(self, case: EvalCase) -> float:
        n = len(case.actual_output or "")
        return 1.0 if self.min_chars <= n <= self.max_chars else 0.0


class LatencyCheck(EvalMetric):
    name = "latency_check"

    def __init__(self, max_ms: float = 1000.0) -> None:
        self.max_ms = max_ms

    def score(self, case: EvalCase) -> float:
        if case.latency_ms is None:
            return 1.0
        return 1.0 if case.latency_ms <= self.max_ms else 0.0


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


class TokenOverlap(EvalMetric):
    """Jaccard similarity between expected and actual tokens."""

    name = "token_overlap"

    def score(self, case: EvalCase) -> float:
        a = _tokens(case.actual_output)
        b = _tokens(case.expected_output)
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)


class LLMJudge(EvalMetric):
    """LLM-as-judge metric. Defaults to a heuristic judge — pass a
    callable `judge_fn(case) -> float` to plug in a real LLM."""

    name = "llm_judge"

    def __init__(self, judge_fn: Callable[[EvalCase], float] | None = None) -> None:
        self.judge_fn = judge_fn or self._heuristic

    @staticmethod
    def _heuristic(case: EvalCase) -> float:
        if not case.expected_output:
            return 1.0 if case.actual_output else 0.0
        a = _tokens(case.actual_output)
        b = _tokens(case.expected_output)
        if not b:
            return 1.0
        return len(a & b) / len(b)

    def score(self, case: EvalCase) -> float:
        try:
            return max(0.0, min(1.0, float(self.judge_fn(case))))
        except Exception as e:
            log.warning("LLMJudge error: %s", e)
            return 0.0


@dataclass
class EvalReport:
    """Result of running an EvalSuite."""

    cases: list[EvalCase]
    scores: dict[str, list[float]]  # metric_name -> per-case scores
    overall_pass: bool
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cases": [c.to_dict() for c in self.cases],
            "scores": self.scores,
            "overall_pass": self.overall_pass,
            "summary": self.summary,
        }

    def metric_avg(self, metric_name: str) -> float:
        vals = self.scores.get(metric_name, [])
        if not vals:
            return 0.0
        return sum(vals) / len(vals)


class EvalSuite:
    """Runs metrics over a list of cases, produces a report."""

    def __init__(self, threshold: float = 0.5) -> None:
        self.metrics: list[EvalMetric] = []
        self.threshold = threshold

    def add_metric(self, metric: EvalMetric) -> "EvalSuite":
        self.metrics.append(metric)
        return self

    def run(self, cases: list[EvalCase]) -> EvalReport:
        scores: dict[str, list[float]] = {m.name: [] for m in self.metrics}
        for case in cases:
            for m in self.metrics:
                t0 = time.time()
                s = m.score(case)
                if case.latency_ms is None:
                    case.latency_ms = (time.time() - t0) * 1000.0
                scores[m.name].append(s)
        summary: dict[str, Any] = {}
        all_pass = True
        for mname, vals in scores.items():
            if vals:
                avg = sum(vals) / len(vals)
                summary[mname] = {
                    "avg": avg,
                    "min": min(vals),
                    "max": max(vals),
                    "count": len(vals),
                }
                if avg < self.threshold:
                    all_pass = False
            else:
                summary[mname] = {"avg": 0.0, "min": 0.0, "max": 0.0, "count": 0}
        summary["threshold"] = self.threshold
        summary["case_count"] = len(cases)
        return EvalReport(
            cases=cases,
            scores=scores,
            overall_pass=all_pass and bool(cases),
            summary=summary,
        )


__all__ = [
    "EvalCase",
    "EvalMetric",
    "ExactMatch",
    "Contains",
    "LengthCheck",
    "LatencyCheck",
    "TokenOverlap",
    "LLMJudge",
    "EvalReport",
    "EvalSuite",
]
