"""SupremeBrainCore — async directive engine + complexity-aware routing.

Receives free-form directive text, normalizes it into a registry of
tasks, classifies complexity per task, picks a model with
:class:`ModelRouter`, and tracks an evolution score that increments per
recursive cycle.

Designed to run beside the synchronous JARVIS routing layer — the
brainiac handles long-lived multi-task directives ("Optimize my
trading bot AND draft three blog posts AND prepare a Series A pitch")
where the planner must decide both *what to do* and *how big each
piece is* across many things at once.

Pure-Python; no LLM or network. Intended as the deterministic
substrate the orchestrator delegates to when the user fires
``initialize_omega_premium()`` or any directive that needs structured
decomposition.
"""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Complexity / model routing
# ---------------------------------------------------------------------------


class Complexity(str, Enum):
    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"


class ComplexityClassifier:
    """Lightweight word-heuristic complexity classifier.

    No ML — uses length, vocabulary, and structural cues. Fast and
    deterministic so it can run inside async cycles without blocking
    on a model call.
    """

    HEAVY_TERMS = (
        "design", "architect", "synthesize", "evaluate", "research",
        "compare", "trade-off", "tradeoff", "optimize", "deploy",
        "production", "system", "framework", "strategy",
    )
    LIGHT_TERMS = (
        "list", "what", "define", "translate", "rename", "format", "summarize",
    )

    def classify(self, text: str) -> Complexity:
        if not text or not text.strip():
            return Complexity.TRIVIAL
        words = re.findall(r"\w+", text)
        n = len(words)
        lower = text.lower()
        light_hits = sum(1 for t in self.LIGHT_TERMS if t in lower)
        heavy_hits = sum(1 for t in self.HEAVY_TERMS if t in lower)

        if n < 6 and light_hits > 0:
            return Complexity.TRIVIAL
        if heavy_hits >= 2 and n >= 25:
            return Complexity.VERY_COMPLEX
        if heavy_hits >= 1 and n >= 12:
            return Complexity.COMPLEX
        if n >= 18:
            return Complexity.MEDIUM
        if n >= 6:
            return Complexity.SIMPLE
        return Complexity.TRIVIAL


# Evolution score increment per cycle, by complexity bucket.
EVOLUTION_INCREMENT: dict[Complexity, float] = {
    Complexity.TRIVIAL: 0.4,
    Complexity.SIMPLE: 0.5,
    Complexity.MEDIUM: 0.7,
    Complexity.COMPLEX: 0.9,
    Complexity.VERY_COMPLEX: 1.2,
}


@dataclass
class ModelRoute:
    model: str
    rationale: str


class ModelRouter:
    """Map complexity → Anthropic model.

    Defaults reflect the canonical pairing: planner is fast (Haiku),
    executor is deep (Opus), with Sonnet as the medium tier. Model
    names are caller-overrideable so tests and downstream callers can
    pin to a specific model.
    """

    DEFAULTS: dict[Complexity, str] = {
        Complexity.TRIVIAL: "claude-haiku-4-5",
        Complexity.SIMPLE: "claude-haiku-4-5",
        Complexity.MEDIUM: "claude-sonnet-4-6",
        Complexity.COMPLEX: "claude-opus-4-7",
        Complexity.VERY_COMPLEX: "claude-opus-4-7",
    }

    def __init__(self, overrides: dict[Complexity, str] | None = None) -> None:
        self._map = dict(self.DEFAULTS)
        if overrides:
            self._map.update(overrides)

    def route(self, complexity: Complexity) -> ModelRoute:
        model = self._map.get(complexity, self.DEFAULTS[Complexity.MEDIUM])
        return ModelRoute(model=model, rationale=f"complexity={complexity.value}")

    def model_for_text(self, text: str, classifier: ComplexityClassifier | None = None) -> ModelRoute:
        clf = classifier or ComplexityClassifier()
        return self.route(clf.classify(text))


# ---------------------------------------------------------------------------
# Task registry
# ---------------------------------------------------------------------------


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class Task:
    task_id: str
    text: str
    complexity: Complexity = Complexity.SIMPLE
    model: str = ""
    status: TaskStatus = TaskStatus.QUEUED
    cycles: int = 0
    result: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "text": self.text,
            "complexity": self.complexity.value,
            "model": self.model,
            "status": self.status.value,
            "cycles": self.cycles,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class CoreStatus(str, Enum):
    IDLE = "idle"
    INITIALIZED = "initialized"
    RUNNING = "running"
    OPTIMIZED = "optimized"


# ---------------------------------------------------------------------------
# SupremeBrainCore
# ---------------------------------------------------------------------------


# Sentence splitter that copes with abbreviations only loosely — enough for directive intake.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


class SupremeBrainCore:
    """Async directive engine.

    Construct → ``ingest_directive(text)`` → ``run_recursive_cycles()``.
    Each call is async-locked so concurrent ``ingest`` calls cannot
    corrupt the registry.

    Tasks are scored at ingest time, model-routed, and queued. A
    recursive cycle iterates every queued task, runs it through the
    optional ``executor`` callable (a coroutine), increments the
    evolution score, and marks the task done.

    Without an executor, the cycle still walks every task, marks them
    as completed, and applies the evolution increment — useful for
    introspection / dry runs.
    """

    EVOLUTION_CAP: float = 100.0

    OMEGA_DIRECTIVES: tuple[str, ...] = (
        "Audit every JARVIS subsystem for completeness and reliability.",
        "Synthesize cross-domain insights between finance, engineering, and policy.",
        "Optimize the routing engine using lessons recorded so far.",
        "Expand knowledge in any domain with fewer than three stored chunks.",
        "Continuously self-heal: detect failed runs and replan automatically.",
    )

    def __init__(
        self,
        classifier: ComplexityClassifier | None = None,
        router: ModelRouter | None = None,
    ) -> None:
        self._classifier = classifier or ComplexityClassifier()
        self._router = router or ModelRouter()
        self._tasks: dict[str, Task] = {}
        self._status: CoreStatus = CoreStatus.IDLE
        self._evolution_score: float = 0.0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public state accessors
    # ------------------------------------------------------------------

    @property
    def status(self) -> CoreStatus:
        return self._status

    @property
    def evolution_score(self) -> float:
        return self._evolution_score

    @property
    def tasks(self) -> list[Task]:
        return list(self._tasks.values())

    def task_by_id(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def snapshot(self) -> dict[str, Any]:
        """Structured status snapshot for dashboards / health checks."""
        counts: dict[str, int] = {s.value: 0 for s in TaskStatus}
        for t in self._tasks.values():
            counts[t.status.value] += 1
        return {
            "status": self._status.value,
            "evolution_score": round(self._evolution_score, 3),
            "task_count": len(self._tasks),
            "task_status_breakdown": counts,
        }

    # ------------------------------------------------------------------
    # Directive ingest
    # ------------------------------------------------------------------

    async def ingest_directive(self, text: str) -> list[Task]:
        """Split free-form directive text into tasks; classify + route each."""
        async with self._lock:
            sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]
            if not sentences:
                return []
            new_tasks: list[Task] = []
            for sent in sentences:
                task = self._make_task(sent)
                self._tasks[task.task_id] = task
                new_tasks.append(task)
            if self._status == CoreStatus.IDLE:
                self._status = CoreStatus.INITIALIZED
            return new_tasks

    async def initialize_omega_premium(self) -> list[Task]:
        """Seed the registry with the five Omega directives."""
        tasks: list[Task] = []
        for directive in self.OMEGA_DIRECTIVES:
            tasks.extend(await self.ingest_directive(directive))
        return tasks

    def _make_task(self, text: str) -> Task:
        complexity = self._classifier.classify(text)
        route = self._router.route(complexity)
        return Task(
            task_id=str(uuid.uuid4())[:8],
            text=text,
            complexity=complexity,
            model=route.model,
        )

    # ------------------------------------------------------------------
    # Recursive cycles
    # ------------------------------------------------------------------

    async def run_recursive_cycles(
        self,
        cycles: int = 1,
        executor: Callable[[Task], "asyncio.Future[Any] | Any"] | None = None,
    ) -> dict[str, Any]:
        """Run *cycles* passes over every queued task.

        If *executor* is supplied it is awaited per task to produce a
        result; otherwise tasks are marked complete with a synthetic
        result. Each iteration applies the evolution score increment
        for the task's complexity bucket, capped at ``EVOLUTION_CAP``.
        """
        if cycles < 1:
            raise ValueError("cycles must be >= 1")
        async with self._lock:
            self._status = CoreStatus.RUNNING

        for _ in range(cycles):
            for task in list(self._tasks.values()):
                if task.status in (TaskStatus.DONE, TaskStatus.SKIPPED, TaskStatus.ERROR):
                    continue
                async with self._lock:
                    task.status = TaskStatus.RUNNING
                    task.cycles += 1
                try:
                    if executor is not None:
                        result = executor(task)
                        if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                            result = await result
                        task.result = str(result) if result is not None else None
                    else:
                        task.result = f"[dry-run] {task.text[:60]}"
                    async with self._lock:
                        task.status = TaskStatus.DONE
                        task.completed_at = time.time()
                        self._increment_evolution(task.complexity)
                except Exception as exc:  # pragma: no cover - defensive
                    async with self._lock:
                        task.status = TaskStatus.ERROR
                        task.error = str(exc)

        async with self._lock:
            if self._evolution_score >= self.EVOLUTION_CAP * 0.5:
                self._status = CoreStatus.OPTIMIZED
        return self.snapshot()

    def _increment_evolution(self, complexity: Complexity) -> None:
        delta = EVOLUTION_INCREMENT[complexity]
        self._evolution_score = min(self.EVOLUTION_CAP, self._evolution_score + delta)


# ---------------------------------------------------------------------------
# Convenience singleton
# ---------------------------------------------------------------------------


_global_core: SupremeBrainCore | None = None


def get_brainiac() -> SupremeBrainCore:
    """Return the global singleton, creating it if needed."""
    global _global_core
    if _global_core is None:
        _global_core = SupremeBrainCore()
    return _global_core


def reset_brainiac() -> None:
    """Reset the global singleton (useful for testing)."""
    global _global_core
    _global_core = None


__all__ = [
    "Complexity",
    "ComplexityClassifier",
    "EVOLUTION_INCREMENT",
    "ModelRoute",
    "ModelRouter",
    "Task",
    "TaskStatus",
    "CoreStatus",
    "SupremeBrainCore",
    "get_brainiac",
    "reset_brainiac",
]
