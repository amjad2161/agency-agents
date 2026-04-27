"""Self-learning engine — extracts lessons from every interaction and improves JARVIS over time.

This module implements continuous learning without retraining:
- Records lessons extracted from interactions
- Tracks routing accuracy and suggests corrections
- Builds a growing knowledge base of what works
- Exports capability snapshots for backup/restore
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict, dataclass, field
from datetime import timezone
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .logging import get_logger

if TYPE_CHECKING:
    from .jarvis_brain import SupremeJarvisBrain

DEFAULT_LESSONS_PATH = Path.home() / ".jarvis" / "learned_lessons.jsonl"

log = get_logger()


@dataclass
class Lesson:
    """A single extracted lesson from an interaction."""

    timestamp: str
    context: str          # brief description of what the request was about
    outcome: str          # "success" | "partial" | "failure" | "correction"
    insight: str          # the key thing learned
    applies_to: list[str] = field(default_factory=list)  # domain slugs
    confidence: float = 0.8
    routing_correction: dict[str, str] | None = None  # {request_pattern: correct_slug}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Lesson":
        return cls(**d)


class SelfLearnerEngine:
    """Extracts lessons from interactions and continuously improves JARVIS.

    Usage::

        engine = SelfLearnerEngine()
        lesson = engine.record_interaction(
            request="explain quantum tunneling",
            response="...",
            feedback="perfect depth",
        )
        lessons = engine.get_lessons_for_domain("jarvis-quantum-computing")
        report = engine.summarize_growth()
    """

    def __init__(self, lessons_path: Path | None = None) -> None:
        self._path = Path(lessons_path or DEFAULT_LESSONS_PATH)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._lessons: list[Lesson] | None = None

    # ------------------------------------------------------------------
    # Public read-only accessors
    # ------------------------------------------------------------------

    @property
    def lessons(self) -> list[Lesson]:
        """All recorded lessons (loaded lazily from disk)."""
        return list(self._load())

    @property
    def lessons_path(self) -> Path:
        """Filesystem path of the lessons ledger."""
        return self._path

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> list[Lesson]:
        if self._lessons is not None:
            return self._lessons
        lessons: list[Lesson] = []
        if self._path.exists():
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        lessons.append(Lesson.from_dict(json.loads(line)))
                    except Exception:
                        pass
        self._lessons = lessons
        return lessons

    def _append(self, lesson: Lesson) -> None:
        with self._lock:
            lessons = self._load()
            lessons.append(lesson)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(lesson.to_dict()) + "\n")

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def record_interaction(
        self,
        request: str,
        response: str,
        feedback: str | None = None,
        routed_to: str | None = None,
        correct_slug: str | None = None,
    ) -> Lesson:
        """Analyze an interaction, extract a lesson, and persist it.

        Args:
            request: The user request.
            response: JARVIS response (can be empty string for routing-only records).
            feedback: Optional human feedback ("good", "wrong domain", etc.).
            routed_to: Which domain slug was used.
            correct_slug: If routing was wrong, what the correct slug was.

        Returns:
            The extracted Lesson dataclass.
        """
        outcome = self._infer_outcome(feedback, correct_slug, routed_to)
        context = self._extract_context(request)
        insight = self._extract_insight(request, response, feedback, outcome)
        domains = self._infer_domains(request, routed_to, correct_slug)

        routing_correction: dict[str, str] | None = None
        if correct_slug and routed_to and correct_slug != routed_to:
            routing_correction = {
                "pattern": self._extract_key_terms(request),
                "was": routed_to,
                "should_be": correct_slug,
            }

        lesson = Lesson(
            timestamp=datetime.now(timezone.utc).isoformat(),
            context=context,
            outcome=outcome,
            insight=insight,
            applies_to=domains,
            confidence=self._confidence_from_feedback(feedback),
            routing_correction=routing_correction,
        )
        self._append(lesson)
        log.info("self_learner: recorded lesson — outcome=%s domain=%s", outcome, domains)
        return lesson

    def get_lessons_for_domain(self, domain_slug: str, limit: int = 10) -> list[Lesson]:
        """Return most recent lessons relevant to the given Jarvis domain slug."""
        lessons = self._load()
        relevant = [
            l for l in lessons
            if domain_slug in l.applies_to or domain_slug in l.insight.lower()
        ]
        return list(reversed(relevant))[:limit]

    def get_routing_corrections(self) -> list[dict[str, str]]:
        """Return all recorded routing corrections for use in improving slug_boosts."""
        lessons = self._load()
        return [
            l.routing_correction
            for l in lessons
            if l.routing_correction is not None
        ]

    def improve_routing_weights(self, brain: "SupremeJarvisBrain") -> dict[str, float]:
        """Analyze past routing mistakes and suggest boost weight adjustments.

        Returns a dict of {slug: adjustment_delta} — positive means boost this slug,
        negative means it was getting too much weight.
        """
        corrections = self.get_routing_corrections()
        adjustment: dict[str, float] = {}
        for c in corrections:
            was: str = c.get("was", "")
            should: str = c.get("should_be", "")
            if was and should and was != should:
                # Decrease weight for the slug that was incorrectly chosen
                adjustment[was] = adjustment.get(was, 0.0) - 1.0
                # Increase weight for the slug that should have been chosen
                adjustment[should] = adjustment.get(should, 0.0) + 1.0
        return adjustment

    def summarize_growth(self) -> str:
        """Return a markdown narrative of how the system has improved over time."""
        lessons = self._load()
        if not lessons:
            return "No lessons recorded yet. Every interaction will teach JARVIS something new."

        total = len(lessons)
        by_outcome: dict[str, int] = {}
        by_domain: dict[str, int] = {}
        corrections = 0
        for l in lessons:
            by_outcome[l.outcome] = by_outcome.get(l.outcome, 0) + 1
            for d in l.applies_to:
                by_domain[d] = by_domain.get(d, 0) + 1
            if l.routing_correction:
                corrections += 1

        top_domains = sorted(by_domain.items(), key=lambda x: x[1], reverse=True)[:5]
        successes = by_outcome.get("success", 0)
        failures = by_outcome.get("failure", 0)
        success_rate = (successes / total * 100) if total else 0

        lines = [
            "# JARVIS Self-Learning Growth Report",
            "",
            f"**Total lessons learned:** {total}",
            f"**Success rate:** {success_rate:.1f}%",
            f"**Routing corrections applied:** {corrections}",
            "",
            "## Outcome Breakdown",
            *[f"- {k}: {v}" for k, v in sorted(by_outcome.items())],
            "",
            "## Most Learned Domains",
            *[f"- `{slug}`: {count} lessons" for slug, count in top_domains],
            "",
            "## Recent Insights",
            *[f"- [{l.timestamp[:10]}] {l.insight}" for l in lessons[-5:]],
        ]
        return "\n".join(lines)

    def export_knowledge_snapshot(self) -> dict[str, Any]:
        """Full knowledge state export for backup/restore."""
        lessons = self._load()
        return {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "total_lessons": len(lessons),
            "lessons": [l.to_dict() for l in lessons],
            "routing_corrections": self.get_routing_corrections(),
            "summary": self.summarize_growth(),
        }

    def import_knowledge_snapshot(self, snapshot: dict[str, Any]) -> int:
        """Import lessons from a snapshot. Returns number of lessons imported."""
        imported = 0
        for d in snapshot.get("lessons", []):
            try:
                lesson = Lesson.from_dict(d)
                self._append(lesson)
                imported += 1
            except Exception:
                pass
        return imported

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _infer_outcome(
        self,
        feedback: str | None,
        correct_slug: str | None,
        routed_to: str | None,
    ) -> str:
        if correct_slug and routed_to and correct_slug != routed_to:
            return "correction"
        if feedback:
            fb = feedback.lower()
            if any(w in fb for w in ("wrong", "bad", "incorrect", "fail", "error")):
                return "failure"
            if any(w in fb for w in ("partial", "almost", "close")):
                return "partial"
        return "success"

    def _extract_context(self, request: str) -> str:
        words = request.strip().split()
        return " ".join(words[:12]) + ("..." if len(words) > 12 else "")

    def _extract_insight(
        self,
        request: str,
        response: str,
        feedback: str | None,
        outcome: str,
    ) -> str:
        if outcome == "correction":
            return f"Routing mistake on: '{self._extract_key_terms(request)}' — see routing_correction"
        if feedback:
            return f"User feedback: {feedback[:120]}"
        key_terms = self._extract_key_terms(request)
        return f"Handled request about [{key_terms}] successfully"

    def _extract_key_terms(self, text: str) -> str:
        words = re.findall(r'\b[a-z]{4,}\b', text.lower())
        stopwords = {"that", "this", "with", "from", "have", "will", "about", "what"}
        sig = [w for w in words if w not in stopwords][:5]
        return " ".join(sig)

    def _infer_domains(
        self,
        request: str,
        routed_to: str | None,
        correct_slug: str | None,
    ) -> list[str]:
        domains = []
        if correct_slug:
            domains.append(correct_slug)
        elif routed_to:
            domains.append(routed_to)
        return domains

    def _confidence_from_feedback(self, feedback: str | None) -> float:
        if not feedback:
            return 0.7
        fb = feedback.lower()
        if any(w in fb for w in ("perfect", "excellent", "exactly")):
            return 1.0
        if any(w in fb for w in ("good", "right", "correct")):
            return 0.9
        if any(w in fb for w in ("partial", "almost")):
            return 0.5
        return 0.6
