"""Self-learning engine.

Records interactions across sessions and surfaces high-confidence
insights as routing corrections. Distinct from `lessons.py` (a free-text
journal): this is structured, queryable, and machine-edited.

Each `Lesson` captures one observation:
  - When it happened
  - What context produced it
  - What outcome resulted (success / failure / partial)
  - The insight learned
  - Which domain slugs the insight applies to
  - Confidence in the insight
  - An optional routing correction the engine should apply

Storage: JSONL at `~/.agency/lessons.jsonl` (override via
`AGENCY_LESSONS_JSONL`). One record per line — append-only, easy to
diff, easy to grep.

The engine is intentionally not threaded: callers serialize writes via
their own session loop. `record_interaction()` is O(1) (single append),
`load_lessons()` is O(n) (full file read), `top_insights()` is
O(n log n) (sort by confidence × recency).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


DEFAULT_LESSONS_JSONL = "lessons.jsonl"


def lessons_jsonl_path() -> Path:
    """Resolve the lessons-jsonl location. May not exist yet."""
    override = os.environ.get("AGENCY_LESSONS_JSONL")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".agency" / DEFAULT_LESSONS_JSONL


@dataclass(frozen=True)
class Lesson:
    """One structured observation. Immutable — record once, never edit."""

    timestamp: float
    context: str
    outcome: str  # "success" | "failure" | "partial"
    insight: str
    applies_to: tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 0.5
    routing_correction: str | None = None

    def to_json(self) -> str:
        d = asdict(self)
        d["applies_to"] = list(self.applies_to)
        return json.dumps(d, ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> "Lesson":
        d = json.loads(line)
        d["applies_to"] = tuple(d.get("applies_to") or ())
        return cls(**d)


class SelfLearnerEngine:
    """Append-only structured-lessons store with retrieval helpers."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or lessons_jsonl_path()
        self._cache: list[Lesson] | None = None

    # ----- write side -----

    def record_interaction(
        self,
        *,
        context: str,
        outcome: str,
        insight: str,
        applies_to: Iterable[str] = (),
        confidence: float = 0.5,
        routing_correction: str | None = None,
    ) -> Lesson:
        """Append a new lesson. Returns the persisted record."""
        if outcome not in ("success", "failure", "partial"):
            raise ValueError(
                f"outcome must be success/failure/partial, got {outcome!r}"
            )
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence must be in [0,1], got {confidence}")
        lesson = Lesson(
            timestamp=time.time(),
            context=context,
            outcome=outcome,
            insight=insight,
            applies_to=tuple(applies_to),
            confidence=confidence,
            routing_correction=routing_correction,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(lesson.to_json() + "\n")
        if self._cache is not None:
            self._cache.append(lesson)
        return lesson

    def save_lessons(self, lessons: Iterable[Lesson]) -> None:
        """Replace the journal with `lessons` (atomic via tmp + rename)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for lesson in lessons:
                f.write(lesson.to_json() + "\n")
        tmp.replace(self.path)
        self._cache = list(lessons)

    # ----- read side -----

    def load_lessons(self, *, refresh: bool = False) -> list[Lesson]:
        """Return all stored lessons. Cached after first call."""
        if self._cache is not None and not refresh:
            return list(self._cache)
        out: list[Lesson] = []
        if self.path.is_file():
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(Lesson.from_json(line))
                    except (ValueError, KeyError, TypeError):
                        # Skip malformed rows rather than blow up the agent.
                        continue
        self._cache = out
        return list(out)

    def top_insights(
        self, n: int = 5, *, domain: str | None = None
    ) -> list[Lesson]:
        """Return up to `n` lessons ranked by confidence × recency.

        If `domain` is given, only lessons whose `applies_to` contains it
        are considered.
        """
        lessons = self.load_lessons()
        if domain is not None:
            lessons = [l for l in lessons if domain in l.applies_to]
        if not lessons:
            return []
        now = time.time()

        def score(l: Lesson) -> float:
            age_days = max(0.0, (now - l.timestamp) / 86400.0)
            # Half-life of ~30 days: fresh observations dominate, old
            # ones decay but never vanish.
            recency = 0.5 ** (age_days / 30.0)
            return l.confidence * recency

        return sorted(lessons, key=score, reverse=True)[:n]

    def apply_corrections(
        self, domain: str, *, min_confidence: float = 0.7
    ) -> list[str]:
        """Return routing corrections worth applying for `domain`.

        Pulls every high-confidence lesson tagged for `domain` that has a
        `routing_correction`, dedupes preserving order, returns the list.
        """
        seen: set[str] = set()
        out: list[str] = []
        for l in self.load_lessons():
            if domain not in l.applies_to:
                continue
            if l.confidence < min_confidence:
                continue
            corr = l.routing_correction
            if not corr or corr in seen:
                continue
            seen.add(corr)
            out.append(corr)
        return out
