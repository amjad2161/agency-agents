"""Multi-agent orchestrator (Tier 2).

Splits a complex request into independent sub-tasks, fans them out to
expert personas via :class:`TaskExecutor`, and merges the results into a
single structured response. Pure-Python; the executor's ``workers=0``
mode keeps tests deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .expert_personas import ALL_PERSONAS, ExpertPersona, ExpertPersonaIndex
from .task_executor import Task, TaskExecutor


_SPLIT_RE = re.compile(r"(?:^|\n)\s*(?:[-*\u2022]|\d+[.)])\s+(.+)")


@dataclass
class AgentJob:
    persona: str
    sub_request: str
    result: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class OrchestrationResult:
    request: str
    jobs: list[AgentJob] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "summary": self.summary,
            "jobs": [j.to_dict() for j in self.jobs],
        }


# A handler is called with (persona, sub_request) and must return text.
Handler = Callable[[ExpertPersona, str], str]


def _default_handler(persona: ExpertPersona, sub: str) -> str:
    return f"[{persona.role}] {sub.strip()}"


class MultiAgentOrchestrator:
    """Split → fan out → merge."""

    def __init__(self, *, personas: tuple[ExpertPersona, ...] = ALL_PERSONAS,
                 handler: Handler | None = None,
                 executor: TaskExecutor | None = None) -> None:
        self.index = ExpertPersonaIndex(personas)
        self.handler = handler or _default_handler
        # workers=0 → drain() executes synchronously, which is what
        # tests want and is also fine in production single-shot calls.
        self.executor = executor or TaskExecutor(workers=0)

    # ------------------------------------------------------------------
    def split(self, request: str) -> list[str]:
        bullets = [m.group(1).strip() for m in _SPLIT_RE.finditer(request or "")]
        if bullets:
            return bullets
        # Fallback: split on double newline / sentence boundaries.
        chunks = [c.strip() for c in re.split(r"\n\n+|(?<=[.?!])\s+", request or "")
                  if c.strip()]
        return chunks or ([request.strip()] if request.strip() else [])

    def assign(self, sub_requests: list[str]) -> list[AgentJob]:
        return [
            AgentJob(persona=self.index.best_for(sub).slug, sub_request=sub)
            for sub in sub_requests
        ]

    def run(self, request: str) -> OrchestrationResult:
        sub_reqs = self.split(request)
        jobs = self.assign(sub_reqs)
        tasks: list[tuple[Task, AgentJob]] = []
        for job in jobs:
            persona = self.index.by_slug(job.persona)
            assert persona is not None  # by construction
            t = self.executor.submit(self.handler, persona, job.sub_request)
            tasks.append((t, job))
        self.executor.drain()
        for t, job in tasks:
            if t.status == "done":
                job.result = str(t.result)
            else:
                job.error = t.error or "unknown error"
        summary = "\n".join(
            f"• [{j.persona}] {j.result or j.error}" for j in jobs
        )
        return OrchestrationResult(request=request, jobs=jobs, summary=summary)
