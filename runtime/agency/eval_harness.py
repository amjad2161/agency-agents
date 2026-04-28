"""Evaluation harness — score JARVIS routing + expert outputs against rubrics.

Defines a small but real eval framework:

- :class:`EvalCase` describes one test (input, expected slug, optional
  expected substrings in output).
- :class:`Rubric` exposes pluggable scorers (substring, regex,
  routing-match, structural).
- :class:`EvalSuite` runs many cases against any callable and emits a
  :class:`Report` with pass-rate, per-case breakdown, and aggregate
  diagnostics suitable for CI gating.

Designed to support both deterministic targets (the SupremeJarvisBrain
router) and stochastic targets (LLM responses) under one API. No
external dependencies; no network.
"""

from __future__ import annotations

import re
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Case + rubric definitions
# ---------------------------------------------------------------------------


@dataclass
class EvalCase:
    """One eval input + its expected outcomes."""

    case_id: str
    input: str
    expected_slug: str | None = None
    must_include: tuple[str, ...] = ()
    must_not_include: tuple[str, ...] = ()
    must_match: tuple[str, ...] = ()  # regex patterns
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    score: float       # 0..1 weighted
    checks: dict[str, bool]
    actual: Any
    duration_ms: float
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "score": round(self.score, 3),
            "checks": dict(self.checks),
            "actual": self.actual,
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
        }


@dataclass
class Report:
    suite_name: str
    cases: list[CaseResult]
    started_at: float
    finished_at: float

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def pass_rate(self) -> float:
        if not self.cases:
            return 0.0
        return self.passed / self.total

    @property
    def average_score(self) -> float:
        if not self.cases:
            return 0.0
        return statistics.mean(c.score for c in self.cases)

    @property
    def duration_seconds(self) -> float:
        return self.finished_at - self.started_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "total": self.total,
            "passed": self.passed,
            "pass_rate": round(self.pass_rate, 3),
            "average_score": round(self.average_score, 3),
            "duration_seconds": round(self.duration_seconds, 2),
            "cases": [c.to_dict() for c in self.cases],
        }

    def summary_line(self) -> str:
        return (
            f"{self.suite_name}: {self.passed}/{self.total} "
            f"({self.pass_rate * 100:.1f}%) avg_score={self.average_score:.2f} "
            f"in {self.duration_seconds:.2f}s"
        )


# ---------------------------------------------------------------------------
# Pluggable check helpers
# ---------------------------------------------------------------------------


def check_substring(actual: str, expected: str) -> bool:
    return expected.lower() in str(actual).lower()


def check_regex(actual: str, pattern: str) -> bool:
    return re.search(pattern, str(actual)) is not None


def check_routing_slug(actual: Any, expected_slug: str) -> bool:
    """Match a routing result against an expected slug.

    Handles dicts, dataclass-like objects with ``.skill`` or ``.slug``,
    and bare strings.
    """
    if actual is None:
        return False
    if isinstance(actual, str):
        return actual == expected_slug
    if isinstance(actual, dict):
        slug = actual.get("skill") or actual.get("slug")
        return slug == expected_slug
    skill = getattr(actual, "skill", None)
    if skill is not None:
        return getattr(skill, "slug", None) == expected_slug
    return getattr(actual, "slug", None) == expected_slug


# ---------------------------------------------------------------------------
# Suite runner
# ---------------------------------------------------------------------------


class EvalSuite:
    """Run a list of EvalCases against a callable and produce a Report."""

    def __init__(self, name: str, cases: list[EvalCase]):
        self.name = name
        self.cases = list(cases)

    @classmethod
    def from_dict_list(cls, name: str, raw: list[dict[str, Any]]) -> "EvalSuite":
        cases = [
            EvalCase(
                case_id=str(c.get("case_id", f"case_{i}")),
                input=str(c["input"]),
                expected_slug=c.get("expected_slug"),
                must_include=tuple(c.get("must_include", ()) or ()),
                must_not_include=tuple(c.get("must_not_include", ()) or ()),
                must_match=tuple(c.get("must_match", ()) or ()),
                weight=float(c.get("weight", 1.0)),
                metadata=dict(c.get("metadata", {}) or {}),
            )
            for i, c in enumerate(raw)
        ]
        return cls(name, cases)

    def run(self, target: Callable[[str], Any]) -> Report:
        started = time.time()
        results: list[CaseResult] = []
        for case in self.cases:
            results.append(self._run_case(case, target))
        finished = time.time()
        return Report(self.name, results, started, finished)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _run_case(self, case: EvalCase, target: Callable[[str], Any]) -> CaseResult:
        t0 = time.time()
        actual: Any = None
        error: str | None = None
        try:
            actual = target(case.input)
        except Exception as exc:
            error = str(exc)
        duration_ms = (time.time() - t0) * 1000

        if error is not None:
            return CaseResult(
                case_id=case.case_id,
                passed=False,
                score=0.0,
                checks={"executed": False},
                actual=None,
                duration_ms=duration_ms,
                error=error,
            )

        actual_text = self._stringify(actual)
        checks: dict[str, bool] = {}

        if case.expected_slug is not None:
            checks["expected_slug"] = check_routing_slug(actual, case.expected_slug)
        for needle in case.must_include:
            checks[f"must_include::{needle}"] = check_substring(actual_text, needle)
        for needle in case.must_not_include:
            checks[f"must_not_include::{needle}"] = not check_substring(actual_text, needle)
        for pat in case.must_match:
            checks[f"must_match::{pat}"] = check_regex(actual_text, pat)

        if not checks:
            # No assertions configured → pass as long as no error.
            checks["executed"] = True

        passed = all(checks.values())
        # Score = fraction of checks that passed, weighted by case.weight.
        passed_count = sum(1 for v in checks.values() if v)
        raw_score = passed_count / max(1, len(checks))
        score = raw_score * case.weight
        return CaseResult(
            case_id=case.case_id,
            passed=passed,
            score=score,
            checks=checks,
            actual=actual_text[:1000],  # avoid bloating reports
            duration_ms=duration_ms,
        )

    @staticmethod
    def _stringify(actual: Any) -> str:
        if actual is None:
            return ""
        if isinstance(actual, str):
            return actual
        if hasattr(actual, "to_dict"):
            try:
                return str(actual.to_dict())
            except Exception:
                pass
        return str(actual)


# ---------------------------------------------------------------------------
# Pre-built routing suite for the SupremeJarvisBrain
# ---------------------------------------------------------------------------


ROUTING_SUITE_CASES: tuple[dict[str, Any], ...] = (
    {"case_id": "kubernetes", "input": "Plan a kubernetes upgrade", "expected_slug": "jarvis-devops-platform"},
    {"case_id": "nlp", "input": "Tokenize and parse a multilingual NLP corpus", "expected_slug": "jarvis-linguistics-nlp"},
    {"case_id": "gdpr", "input": "Outline GDPR data subject rights", "expected_slug": "jarvis-privacy-data-governance"},
    {"case_id": "satellite", "input": "Estimate satellite orbit decay", "expected_slug": "jarvis-space-aerospace"},
    {"case_id": "quantum", "input": "Design a Qiskit quantum algorithm", "expected_slug": "jarvis-quantum-computing"},
    {"case_id": "cbt", "input": "Design a CBT-style intervention for catastrophizing", "expected_slug": "jarvis-mental-health"},
    {"case_id": "actuarial", "input": "Build an actuarial model for catastrophe insurance", "expected_slug": "jarvis-insurance-risk"},
    {"case_id": "circular", "input": "Design a circular economy program for plastics", "expected_slug": "jarvis-circular-economy"},
    {"case_id": "smart_city", "input": "Plan a smart city mobility platform", "expected_slug": "jarvis-smart-cities"},
    {"case_id": "neuro_bci", "input": "Decode EEG signals for a brain-computer interface", "expected_slug": "jarvis-neuroscience-bci"},
)



def routing_suite() -> EvalSuite:
    """Pre-built 10-case suite for the SupremeJarvisBrain router."""
    return EvalSuite.from_dict_list("routing_suite", list(ROUTING_SUITE_CASES))
