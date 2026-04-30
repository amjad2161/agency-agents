"""Task planner (Tier 2) — decomposition, critical path, scheduling.

Pure-Python DAG planner. Takes a list of tasks with dependencies and
estimated durations, returns a topologically-ordered schedule plus the
critical path. No graphviz / networkx dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlanTask:
    id: str
    title: str
    duration: float = 1.0
    deps: tuple[str, ...] = ()
    assignee: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScheduledTask:
    task: PlanTask
    start: float
    finish: float
    is_critical: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.task.id,
            "title": self.task.title,
            "duration": self.task.duration,
            "deps": list(self.task.deps),
            "assignee": self.task.assignee,
            "start": self.start,
            "finish": self.finish,
            "is_critical": self.is_critical,
        }


@dataclass
class Plan:
    tasks: list[ScheduledTask]
    critical_path: list[str]
    makespan: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "makespan": self.makespan,
            "critical_path": list(self.critical_path),
            "tasks": [t.to_dict() for t in self.tasks],
        }


class TaskPlanner:
    """Topological scheduler with critical-path analysis."""

    def schedule(self, tasks: list[PlanTask]) -> Plan:
        by_id = {t.id: t for t in tasks}
        for t in tasks:
            for dep in t.deps:
                if dep not in by_id:
                    raise ValueError(f"unknown dependency {dep!r} on task {t.id!r}")

        order = self._toposort(tasks)
        finish: dict[str, float] = {}
        scheduled: dict[str, ScheduledTask] = {}
        for tid in order:
            task = by_id[tid]
            start = max((finish[dep] for dep in task.deps), default=0.0)
            f = start + task.duration
            finish[tid] = f
            scheduled[tid] = ScheduledTask(task=task, start=start, finish=f)

        # Critical path: walk back from the latest-finishing task.
        if not scheduled:
            return Plan(tasks=[], critical_path=[], makespan=0.0)
        end_id = max(scheduled, key=lambda i: scheduled[i].finish)
        path: list[str] = [end_id]
        current = end_id
        while by_id[current].deps:
            # Pick the dep that finishes latest (drives the makespan).
            current = max(by_id[current].deps, key=lambda d: scheduled[d].finish)
            path.append(current)
        path.reverse()
        for tid in path:
            scheduled[tid].is_critical = True

        return Plan(
            tasks=[scheduled[t.id] for t in tasks],
            critical_path=path,
            makespan=scheduled[end_id].finish,
        )

    @staticmethod
    def _toposort(tasks: list[PlanTask]) -> list[str]:
        by_id = {t.id: t for t in tasks}
        in_deg = {t.id: 0 for t in tasks}
        children: dict[str, list[str]] = {t.id: [] for t in tasks}
        for t in tasks:
            for dep in t.deps:
                in_deg[t.id] += 1
                children[dep].append(t.id)
        queue = [tid for tid, d in in_deg.items() if d == 0]
        order: list[str] = []
        while queue:
            queue.sort()  # stable ordering
            tid = queue.pop(0)
            order.append(tid)
            for child in children[tid]:
                in_deg[child] -= 1
                if in_deg[child] == 0:
                    queue.append(child)
        if len(order) != len(by_id):
            raise ValueError("dependency cycle detected")
        return order

    # ------------------------------------------------------------------
    def decompose(self, goal: str, *, steps: int = 4) -> list[PlanTask]:
        """Trivial heuristic decomposer for free-text goals."""
        verbs = ["analyze", "design", "implement", "validate", "deliver"]
        tasks: list[PlanTask] = []
        prev: tuple[str, ...] = ()
        for i in range(min(steps, len(verbs))):
            tid = f"t{i+1}"
            tasks.append(PlanTask(
                id=tid,
                title=f"{verbs[i].title()}: {goal}",
                duration=1.0,
                deps=prev,
            ))
            prev = (tid,)
        return tasks
