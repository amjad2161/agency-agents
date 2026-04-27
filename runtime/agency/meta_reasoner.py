"""Meta-reasoning engine.

Wraps a multi-step ReAct-style loop (thought → action → observation)
around any callable executor. Used by the CLI `reason` command to
break a high-level goal into iterative steps with self-critique.

The engine is executor-agnostic: callers register a `step_executor`
callable that takes a thought and returns an observation. The engine
handles the loop, confidence tracking, and refinement passes.

This is *not* a planner — it's the runner for a plan that emerges as
the engine reasons. For a fixed plan, use `agency.planner` directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol


@dataclass(frozen=True)
class ReasoningStep:
    """One iteration of the reasoning loop."""

    step_id: int
    thought: str
    action: str
    observation: str
    confidence: float = 0.5


class StepExecutor(Protocol):
    """Callable that turns a thought into an action+observation pair."""

    def __call__(self, thought: str, *, history: list[ReasoningStep]) -> tuple[str, str, float]:
        """Return (action_taken, observation, confidence)."""
        ...


def _default_executor(
    thought: str, *, history: list[ReasoningStep]
) -> tuple[str, str, float]:
    """No-op executor — useful as a placeholder when the caller hasn't
    wired an LLM. Echoes the thought as the observation with low
    confidence so the loop terminates quickly."""
    return ("noop", thought, 0.1)


class MetaReasoningEngine:
    """ReAct-style multi-step reasoning with critique and refinement."""

    def __init__(
        self,
        executor: StepExecutor | None = None,
        *,
        confidence_threshold: float = 0.85,
    ) -> None:
        self._executor: StepExecutor = executor or _default_executor
        self._threshold = confidence_threshold
        self._steps: list[ReasoningStep] = []

    # ----- core loop -----

    def reason(self, goal: str, *, max_iterations: int = 8) -> list[ReasoningStep]:
        """Run the reasoning loop. Stops when confidence ≥ threshold or
        max_iterations is hit. Returns the full step list."""
        if max_iterations <= 0:
            raise ValueError("max_iterations must be positive")
        self._steps = []
        for i in range(max_iterations):
            thought = self._next_thought(goal)
            action, observation, conf = self._executor(thought, history=self._steps)
            step = ReasoningStep(
                step_id=i + 1,
                thought=thought,
                action=action,
                observation=observation,
                confidence=conf,
            )
            self._steps.append(step)
            if conf >= self._threshold:
                break
        return list(self._steps)

    def plan_and_execute(self, goal: str) -> list[ReasoningStep]:
        """Convenience: reason() with a critique+refine pass appended."""
        steps = self.reason(goal)
        critique_text = self.critique(steps)
        if critique_text:
            steps = self.refine(steps, critique=critique_text)
        return steps

    # ----- introspection -----

    def critique(self, steps: list[ReasoningStep]) -> str:
        """Inspect a step list for low-confidence stretches or
        contradictions. Returns a non-empty critique string if the
        sequence has issues; empty string if it looks clean."""
        if not steps:
            return "no steps to critique"
        notes: list[str] = []
        weak = [s for s in steps if s.confidence < 0.4]
        if weak:
            ids = ", ".join(f"#{s.step_id}" for s in weak)
            notes.append(f"low-confidence steps: {ids}")
        if len({s.action for s in steps}) == 1 and len(steps) > 2:
            notes.append("loop appears to repeat the same action — stuck?")
        last = steps[-1]
        if last.confidence < self._threshold:
            notes.append(
                f"final confidence {last.confidence:.2f} below "
                f"threshold {self._threshold:.2f}"
            )
        return "; ".join(notes)

    def refine(
        self, steps: list[ReasoningStep], *, critique: str
    ) -> list[ReasoningStep]:
        """Run one extra reasoning pass conditioned on the critique.
        Returns the original steps + at most one refinement step."""
        if not steps:
            return steps
        refine_thought = (
            f"refine based on critique: {critique}. last observation: "
            f"{steps[-1].observation}"
        )
        action, obs, conf = self._executor(refine_thought, history=steps)
        out = list(steps)
        out.append(
            ReasoningStep(
                step_id=steps[-1].step_id + 1,
                thought=refine_thought,
                action=action,
                observation=obs,
                confidence=conf,
            )
        )
        return out

    def avg_confidence(self, steps: list[ReasoningStep] | None = None) -> float:
        """Mean confidence over the given steps (or the engine's last run)."""
        seq = steps if steps is not None else self._steps
        if not seq:
            return 0.0
        return sum(s.confidence for s in seq) / len(seq)

    def last_steps(self) -> list[ReasoningStep]:
        """Return the most recent reason() output without rerunning."""
        return list(self._steps)

    # ----- helpers -----

    def _next_thought(self, goal: str) -> str:
        if not self._steps:
            return f"start working on goal: {goal}"
        last = self._steps[-1]
        return (
            f"continue toward goal: {goal}. last action={last.action!r}, "
            f"observation={last.observation[:200]!r}, confidence={last.confidence:.2f}"
        )
