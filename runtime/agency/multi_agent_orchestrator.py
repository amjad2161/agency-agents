"""Multi-agent orchestration: Planner → Executor → Critic pipeline.

Operates in mock mode by default (no LLM required) so it can be exercised
in offline test environments and CI.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AgentRole(str, Enum):
    PLANNER = "planner"
    EXECUTOR = "executor"
    CRITIC = "critic"
    COORDINATOR = "coordinator"


@dataclass
class AgentMessage:
    """A single message produced by an agent within a session."""

    role: AgentRole
    content: str
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role.value, "content": self.content, "ts": self.ts}


class MultiAgentOrchestrator:
    """Runs a Planner → Executor → Critic loop.

    Parameters
    ----------
    mock:
        When *True* (default) all agents return deterministic stub
        responses — no LLM calls are made.  Set to *False* to wire in
        real LLM backends (future extension).
    """

    def __init__(self, mock: bool = True) -> None:
        self.mock = mock
        self._sessions: dict[str, list[AgentMessage]] = {}

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def new_session(self) -> str:
        """Create a new session and return its ID."""
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = []
        return session_id

    def _append(self, session_id: str, role: AgentRole, content: str) -> AgentMessage:
        msg = AgentMessage(role=role, content=content)
        self._sessions.setdefault(session_id, []).append(msg)
        return msg

    # ------------------------------------------------------------------
    # Agent roles
    # ------------------------------------------------------------------

    def plan(self, goal: str, session_id: str) -> str:
        """Planner: decompose *goal* into actionable steps."""
        if self.mock:
            result = "Step 1: Analyze. Step 2: Execute. Step 3: Verify."
        else:  # pragma: no cover
            raise NotImplementedError("Real LLM planning not implemented yet.")
        self._append(session_id, AgentRole.PLANNER, result)
        return result

    def execute_step(self, step: str, session_id: str) -> str:
        """Executor: attempt to carry out *step*."""
        if self.mock:
            result = f"Executed: {step}"
        else:  # pragma: no cover
            raise NotImplementedError("Real LLM execution not implemented yet.")
        self._append(session_id, AgentRole.EXECUTOR, result)
        return result

    def critique(self, result: str, session_id: str) -> str:
        """Critic: evaluate *result* and suggest improvements."""
        if self.mock:
            feedback = "Quality: Good. Suggestion: None."
        else:  # pragma: no cover
            raise NotImplementedError("Real LLM critique not implemented yet.")
        self._append(session_id, AgentRole.CRITIC, feedback)
        return feedback

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def run_pipeline(self, goal: str) -> dict[str, Any]:
        """Run the full Planner → Executor → Critic pipeline.

        Returns a dict with keys:
        ``session_id``, ``goal``, ``plan``, ``execution``,
        ``critique``, ``status``.
        """
        session_id = self.new_session()
        self._append(session_id, AgentRole.COORDINATOR, f"Goal: {goal}")

        plan_text = self.plan(goal, session_id)

        # Execute each step from the plan (split on "Step N:").
        steps = [s.strip() for s in plan_text.split(".") if s.strip()]
        executions: list[str] = []
        for step in steps:
            executions.append(self.execute_step(step, session_id))

        execution_summary = "; ".join(executions)
        critique_text = self.critique(execution_summary, session_id)

        return {
            "session_id": session_id,
            "goal": goal,
            "plan": plan_text,
            "execution": execution_summary,
            "critique": critique_text,
            "status": "completed",
        }

    # ------------------------------------------------------------------
    # Session retrieval
    # ------------------------------------------------------------------

    def get_session(self, session_id: str) -> list[dict[str, Any]]:
        """Return all messages for *session_id* as plain dicts."""
        messages = self._sessions.get(session_id, [])
        return [m.to_dict() for m in messages]
