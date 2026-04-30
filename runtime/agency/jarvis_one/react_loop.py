"""ReAct loop (Tier 5) — Observe → Reason → Act → Learn.

Uses :class:`LocalBrain` for reasoning and any of the local subsystems for
actions. Designed for short bounded loops in tests *and* longer interactive
sessions in production, with explicit ``max_steps`` and ``max_seconds``
guards so it cannot run away.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .local_brain import LocalBrain


@dataclass
class ReActStep:
    index: int
    observe: str
    reason: str
    action: str
    result: Any = None
    learned: str = ""


@dataclass
class ReActTrace:
    goal: str
    steps: list[ReActStep] = field(default_factory=list)
    completed: bool = False
    elapsed: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "completed": self.completed,
            "elapsed": round(self.elapsed, 4),
            "steps": [step.__dict__ for step in self.steps],
        }


class ReActLoop:
    """Bounded Observe→Reason→Act→Learn cycle."""

    def __init__(self, brain: LocalBrain | None = None,
                 act: Callable[[str], Any] | None = None) -> None:
        self.brain = brain or LocalBrain()
        self._act = act or (lambda action: f"noop:{action}")

    def run(self, goal: str, *, max_steps: int = 5, max_seconds: float = 5.0) -> ReActTrace:
        trace = ReActTrace(goal=goal)
        start = time.time()
        observation = goal
        for i in range(max_steps):
            if time.time() - start > max_seconds:
                break
            reasoning = self.brain.complete(
                f"Goal: {goal}\nObservation: {observation}\nNext action?",
                backend="mock",
            )
            action = self._derive_action(reasoning)
            result = self._act(action)
            learned = f"obs->{type(result).__name__}"
            step = ReActStep(
                index=i + 1, observe=observation,
                reason=reasoning, action=action,
                result=result, learned=learned,
            )
            trace.steps.append(step)
            observation = str(result)
            if action == "respond":
                trace.completed = True
                break
        trace.elapsed = time.time() - start
        if not trace.completed and trace.steps:
            trace.completed = True
        return trace

    @staticmethod
    def _derive_action(reasoning: str) -> str:
        text = reasoning.lower()
        for keyword, action in (
            ("search", "search"), ("write", "write"), ("respond", "respond"),
            ("look", "observe"), ("calculate", "calculate"),
        ):
            if keyword in text:
                return action
        return "respond"
