"""Meta-reasoning engine — ReAct-style chain-of-thought for JARVIS.

Think → Act → Observe → Repeat until goal is reached or max iterations hit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .logging import get_logger

log = get_logger()

MAX_ITERATIONS = 8


@dataclass
class ReasoningStep:
    """One step in a ReAct reasoning chain."""

    step_id: int
    thought: str
    action: str | None = None
    observation: str | None = None
    confidence: float = 0.7

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "thought": self.thought,
            "action": self.action,
            "observation": self.observation,
            "confidence": self.confidence,
        }


class MetaReasoningEngine:
    """ReAct-style meta-reasoner for multi-step goal decomposition and critique.

    Usage::

        engine = MetaReasoningEngine()
        steps = engine.reason("Explain how to design a rate limiter")
        final = engine.plan_and_execute("Debug this stack trace: ...")
        score, critique = engine.critique(response, goal)
        refined = engine.refine(response, goal, iterations=2)
    """

    def __init__(self) -> None:
        self._steps: list[ReasoningStep] = []

    # ------------------------------------------------------------------
    # Core reasoning loop
    # ------------------------------------------------------------------

    def reason(
        self,
        goal: str,
        context: str = "",
        max_iterations: int = MAX_ITERATIONS,
    ) -> list[ReasoningStep]:
        """Run ReAct loop for *goal*, returning all reasoning steps.

        This is a lightweight symbolic reasoner — no LLM call required.
        It decomposes the goal into sub-questions and generates a structured
        thinking trace that a downstream model can follow.
        """
        steps: list[ReasoningStep] = []
        sub_goals = self._decompose(goal)
        context_summary = self._summarize_context(context)

        for i, sub in enumerate(sub_goals[:max_iterations]):
            thought = self._generate_thought(sub, context_summary, i)
            action = self._generate_action(sub)
            observation = self._generate_observation(sub, action)
            confidence = self._score_step(thought, action, observation)

            step = ReasoningStep(
                step_id=i + 1,
                thought=thought,
                action=action,
                observation=observation,
                confidence=confidence,
            )
            steps.append(step)
            log.debug("meta_reasoner: step %d — confidence=%.2f", i + 1, confidence)

        self._steps = steps
        return steps

    def plan_and_execute(
        self,
        goal: str,
        tools: list[dict[str, Any]] | None = None,
        context: str = "",
    ) -> str:
        """Produce a structured execution plan string for *goal*.

        If *tools* is provided, steps are annotated with the best-fit tool name.
        """
        steps = self.reason(goal, context=context)
        tool_index = {t.get("name", "").lower(): t for t in (tools or [])}

        lines = [f"## Execution Plan: {goal[:80]}", ""]
        for s in steps:
            tool_hint = ""
            if tools:
                matched = self._match_tool(s.action or "", tool_index)
                tool_hint = f" [tool: {matched}]" if matched else ""
            lines.append(
                f"**Step {s.step_id}** (confidence={s.confidence:.0%}){tool_hint}"
            )
            lines.append(f"- *Thought:* {s.thought}")
            if s.action:
                lines.append(f"- *Action:* {s.action}")
            if s.observation:
                lines.append(f"- *Expected:* {s.observation}")
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Critique & refinement
    # ------------------------------------------------------------------

    def critique(self, response: str, goal: str) -> tuple[float, str]:
        """Score *response* against *goal* and return (score, feedback).

        Score is 0.0–1.0. Feedback explains what's missing.
        """
        issues: list[str] = []
        score = 1.0

        # Length heuristic
        if len(response.split()) < 20:
            issues.append("Response is too brief — expand reasoning.")
            score -= 0.2

        # Goal keyword coverage
        goal_terms = set(re.findall(r'\b[a-z]{4,}\b', goal.lower()))
        resp_lower = response.lower()
        missing = [t for t in goal_terms if t not in resp_lower]
        if len(missing) > len(goal_terms) * 0.4:
            issues.append(f"Missing coverage of: {', '.join(list(missing)[:5])}")
            score -= 0.15 * (len(missing) / max(len(goal_terms), 1))

        # Structure check
        if "?" in goal and "?" not in response and len(response.split()) < 50:
            issues.append("Question may not be fully answered.")
            score -= 0.1

        # Code/example expectation
        code_words = {"implement", "code", "function", "write", "example", "show"}
        if code_words & set(goal.lower().split()) and "```" not in response:
            issues.append("Code example expected but not present.")
            score -= 0.15

        score = max(0.0, min(1.0, score))
        feedback = "; ".join(issues) if issues else "Response looks complete."
        log.debug("meta_reasoner: critique score=%.2f", score)
        return score, feedback

    def refine(self, response: str, goal: str, iterations: int = 2) -> str:
        """Iteratively apply self-critique to produce refinement notes.

        Returns a string describing what improvements should be made.
        Does *not* call an LLM — produces actionable instructions for the caller.
        """
        current_score, current_feedback = self.critique(response, goal)
        notes: list[str] = []

        for i in range(iterations):
            if current_score >= 0.9:
                break
            notes.append(f"Iteration {i + 1}: {current_feedback}")
            # Simulate improvement — in real use the caller would apply changes
            current_score = min(1.0, current_score + 0.15)
            if current_score >= 0.9:
                current_feedback = "Refinement complete."
            else:
                _, current_feedback = self.critique(response, goal)

        if not notes:
            return "No refinement needed — response meets quality bar."
        return "\n".join(notes)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def last_steps(self) -> list[ReasoningStep]:
        return list(self._steps)

    def avg_confidence(self) -> float:
        if not self._steps:
            return 0.0
        return sum(s.confidence for s in self._steps) / len(self._steps)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _decompose(self, goal: str) -> list[str]:
        """Break goal into sub-questions / reasoning targets."""
        goal = goal.strip()
        # If the goal already contains numbered steps, use them
        numbered = re.findall(r'\d+[\.\)]\s+(.+)', goal)
        if len(numbered) >= 2:
            return numbered[:MAX_ITERATIONS]

        # Heuristic decomposition
        subs = []
        if len(goal.split()) > 15:
            subs.append(f"Clarify intent: what is the core ask of '{goal[:60]}'?")
        subs.append(f"What domain knowledge is required to address: '{goal[:60]}'?")
        subs.append(f"What are the key constraints or edge cases for: '{goal[:60]}'?")
        subs.append(f"What is the best structure/format for answering: '{goal[:60]}'?")
        subs.append(f"Draft a complete answer to: '{goal[:60]}'")
        return subs

    def _summarize_context(self, context: str) -> str:
        if not context:
            return ""
        words = context.split()
        if len(words) <= 30:
            return context
        return " ".join(words[:30]) + "..."

    def _generate_thought(self, sub: str, context: str, step_idx: int) -> str:
        prefix = {
            0: "First, I need to understand",
            1: "The key insight here is",
            2: "I should consider the constraints around",
            3: "The best approach would be to",
            4: "Synthesizing the above,",
        }.get(step_idx, "Next,")
        clean = sub.replace("'", "").strip("?.")
        suffix = f" (context: {context})" if context and step_idx == 0 else ""
        return f"{prefix} {clean}{suffix}."

    def _generate_action(self, sub: str) -> str | None:
        sub_lower = sub.lower()
        if any(w in sub_lower for w in ("clarify", "understand", "intent")):
            return "Analyze request structure and identify key requirements"
        if any(w in sub_lower for w in ("domain", "knowledge", "required")):
            return "Route to relevant expert domain module"
        if any(w in sub_lower for w in ("constraint", "edge case", "limit")):
            return "Enumerate failure modes and boundary conditions"
        if any(w in sub_lower for w in ("structure", "format", "best approach")):
            return "Select response format: prose / code / table / step-by-step"
        if any(w in sub_lower for w in ("draft", "answer", "complete")):
            return "Generate comprehensive response"
        return None

    def _generate_observation(self, sub: str, action: str | None) -> str | None:
        if not action:
            return None
        return f"After '{action}', the goal '{sub[:50]}' should be addressed."

    def _score_step(
        self, thought: str, action: str | None, observation: str | None
    ) -> float:
        score = 0.6
        if action:
            score += 0.2
        if observation:
            score += 0.1
        if len(thought.split()) > 8:
            score += 0.1
        return min(1.0, score)

    def _match_tool(self, action: str, tool_index: dict[str, Any]) -> str | None:
        action_lower = action.lower()
        for name in tool_index:
            if any(w in action_lower for w in name.split("_")):
                return name
        return None
