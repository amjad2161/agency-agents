"""Multi-agent orchestration for JARVIS — Pass 20.

Implements a pool of specialised agents (PLANNER, EXECUTOR, CRITIC,
MEMORY, ROBOT, VISION) that communicate via a shared message queue
and cooperate to complete complex tasks.

Usage
-----
    from agency.multi_agent import MultiAgentOrchestrator

    orch = MultiAgentOrchestrator()
    result = orch.run_task("research quantum computing and write a summary")
    print(result.outputs[-1])

CLI
---
    agency multi-agent run "plan and execute: research X then write report"
    agency multi-agent status
"""

from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums & data models
# ---------------------------------------------------------------------------

class AgentRole(str, Enum):
    """Roles a specialised agent can play in the orchestration pool."""
    PLANNER  = "planner"
    EXECUTOR = "executor"
    CRITIC   = "critic"
    MEMORY   = "memory"
    ROBOT    = "robot"
    VISION   = "vision"


@dataclass
class Agent:
    """Configuration descriptor for a single agent in the pool."""
    role: AgentRole
    name: str
    model: str = "claude-sonnet-4-6"
    system_prompt: str = ""
    tools_allowed: List[str] = field(default_factory=list)


@dataclass
class AgentMessage:
    """A message passed between agents via the shared queue."""
    sender: str
    recipient: str          # agent name or "*" for broadcast
    content: str
    role: str = "user"      # "user" | "assistant" | "system"
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)


@dataclass
class TaskStep:
    """A single step produced by the PLANNER agent."""
    index: int
    description: str
    status: str = "pending"   # pending | running | done | failed
    output: str = ""


@dataclass
class OrchestratorResult:
    """Consolidated result returned from run_task()."""
    task: str
    task_id: str
    steps: List[TaskStep]
    outputs: List[str]
    critique: str
    success: bool
    elapsed: float
    agent_messages: List[AgentMessage] = field(default_factory=list)

    # Convenience
    def final_output(self) -> str:
        return self.outputs[-1] if self.outputs else ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "task_id": self.task_id,
            "steps": [{"index": s.index, "description": s.description,
                        "status": s.status, "output": s.output}
                      for s in self.steps],
            "outputs": self.outputs,
            "critique": self.critique,
            "success": self.success,
            "elapsed": round(self.elapsed, 3),
        }


# ---------------------------------------------------------------------------
# Default system prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPTS: Dict[AgentRole, str] = {
    AgentRole.PLANNER: (
        "You are the PLANNER agent. Break the given task into a numbered list "
        "of clear, atomic steps. Output ONLY the steps, one per line, prefixed "
        "with a number and dot (e.g. '1. Do X'). Be concise."
    ),
    AgentRole.EXECUTOR: (
        "You are the EXECUTOR agent. Execute the given step description and "
        "produce a concrete, actionable output. Be specific and thorough."
    ),
    AgentRole.CRITIC: (
        "You are the CRITIC agent. Review the provided output for correctness, "
        "completeness, and quality. Reply with: PASS or FAIL followed by a "
        "one-sentence justification."
    ),
    AgentRole.MEMORY: (
        "You are the MEMORY agent. Summarise and store the given information "
        "for later retrieval. Extract key facts as bullet points."
    ),
    AgentRole.ROBOT: (
        "You are the ROBOT agent. Translate the given task description into "
        "low-level robot motion commands. Output each command on a new line."
    ),
    AgentRole.VISION: (
        "You are the VISION agent. Describe what a robot's camera would see "
        "and identify relevant objects, distances, and obstacles."
    ),
}


# ---------------------------------------------------------------------------
# Mock LLM (used when ANTHROPIC_API_KEY is absent / unit tests)
# ---------------------------------------------------------------------------

class _MockLLM:
    """Deterministic stub so tests never need a live API key."""

    def __init__(self, role: AgentRole) -> None:
        self._role = role

    def complete(self, system: str, user: str) -> str:
        role = self._role
        if role == AgentRole.PLANNER:
            return (
                "1. Analyse the request\n"
                "2. Gather relevant information\n"
                "3. Synthesise findings\n"
                "4. Write the final report"
            )
        if role == AgentRole.EXECUTOR:
            return f"[EXECUTOR] Completed step: {user[:80]}"
        if role == AgentRole.CRITIC:
            return "PASS — output meets quality criteria"
        if role == AgentRole.MEMORY:
            return f"[MEMORY] Stored: {user[:60]}"
        if role == AgentRole.ROBOT:
            return "move_forward(0.5)\nrotate(90)\ngrasp()"
        if role == AgentRole.VISION:
            return "Detected: table (1.2 m), chair (2.0 m), no obstacles"
        return f"[{role.value}] Mock response for: {user[:60]}"


def _build_llm(role: AgentRole, model: str) -> "_MockLLM | _RealLLM":
    try:
        import os
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise ImportError("no key")
        return _RealLLM(role, model)
    except Exception:
        return _MockLLM(role)


class _RealLLM:
    """Thin wrapper around AnthropicLLM for agent use."""

    def __init__(self, role: AgentRole, model: str) -> None:
        self._role = role
        self._model = model

    def complete(self, system: str, user: str) -> str:
        try:
            from .llm import AnthropicLLM, LLMConfig
            llm = AnthropicLLM(LLMConfig(model=self._model, max_tokens=1024))
            resp = llm.messages_create(
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            block = resp.content[0]
            return block.text if hasattr(block, "text") else str(block)
        except Exception as exc:
            return f"[{self._role.value}] LLM error: {exc}"


# ---------------------------------------------------------------------------
# MultiAgentOrchestrator
# ---------------------------------------------------------------------------

class MultiAgentOrchestrator:
    """Coordinates a pool of specialised agents to solve complex tasks.

    Flow for ``run_task(task)``:
      1. PLANNER  → break task into steps
      2. EXECUTOR → run each step sequentially
      3. CRITIC   → review final output
      4. MEMORY   → store result summary
    Messages between agents are logged to the shared ``_message_queue``.
    """

    def __init__(self) -> None:
        self._agents: Dict[AgentRole, Agent] = {}
        self._message_queue: queue.Queue[AgentMessage] = queue.Queue()
        self._message_log: List[AgentMessage] = []
        self._results: List[OrchestratorResult] = []
        self._active: bool = False
        self._lock = threading.Lock()
        self._setup_default_agents()

    # ------------------------------------------------------------------
    # Pool management
    # ------------------------------------------------------------------

    def _setup_default_agents(self) -> None:
        """Register one agent per role with sensible defaults."""
        for role in AgentRole:
            self.add_agent(Agent(
                role=role,
                name=f"jarvis_{role.value}",
                system_prompt=_SYSTEM_PROMPTS[role],
            ))

    def add_agent(self, agent: Agent) -> None:
        """Add or replace an agent for the given role."""
        with self._lock:
            self._agents[agent.role] = agent

    def get_agent(self, role: AgentRole) -> Optional[Agent]:
        return self._agents.get(role)

    def list_agents(self) -> List[Agent]:
        return list(self._agents.values())

    # ------------------------------------------------------------------
    # Messaging helpers
    # ------------------------------------------------------------------

    def _send(self, sender: str, recipient: str, content: str,
              role: str = "user") -> AgentMessage:
        msg = AgentMessage(sender=sender, recipient=recipient,
                           content=content, role=role)
        self._message_queue.put(msg)
        self._message_log.append(msg)
        return msg

    def _drain_queue(self) -> List[AgentMessage]:
        msgs: List[AgentMessage] = []
        while not self._message_queue.empty():
            try:
                msgs.append(self._message_queue.get_nowait())
            except queue.Empty:
                break
        return msgs

    # ------------------------------------------------------------------
    # Core task execution
    # ------------------------------------------------------------------

    def _call_agent(self, role: AgentRole, user_content: str) -> str:
        agent = self._agents.get(role)
        if agent is None:
            return f"[ERROR] No agent registered for role {role.value}"
        llm = _build_llm(role, agent.model)
        return llm.complete(agent.system_prompt, user_content)

    def _plan(self, task: str) -> List[TaskStep]:
        """Ask PLANNER to decompose the task into steps."""
        self._send("orchestrator", "jarvis_planner",
                   f"Break this task into numbered steps:\n{task}")
        raw = self._call_agent(AgentRole.PLANNER, task)
        self._send("jarvis_planner", "orchestrator", raw, role="assistant")

        steps: List[TaskStep] = []
        for i, line in enumerate(raw.splitlines()):
            line = line.strip()
            if not line:
                continue
            # Strip leading "N." prefix
            if line and line[0].isdigit():
                dot = line.find(".")
                if dot != -1:
                    line = line[dot + 1:].strip()
            if line:
                steps.append(TaskStep(index=i, description=line))
        if not steps:
            steps = [TaskStep(index=0, description=task)]
        return steps

    def _execute_step(self, step: TaskStep) -> str:
        """Ask EXECUTOR to carry out one step."""
        self._send("orchestrator", "jarvis_executor",
                   f"Execute this step: {step.description}")
        output = self._call_agent(AgentRole.EXECUTOR, step.description)
        self._send("jarvis_executor", "orchestrator", output, role="assistant")
        return output

    def _critique(self, outputs: List[str]) -> str:
        """Ask CRITIC to review the combined outputs."""
        combined = "\n---\n".join(outputs[-3:])  # review last 3 outputs
        self._send("orchestrator", "jarvis_critic",
                   f"Review these outputs:\n{combined}")
        verdict = self._call_agent(AgentRole.CRITIC, combined)
        self._send("jarvis_critic", "orchestrator", verdict, role="assistant")
        return verdict

    def _memorise(self, task: str, summary: str) -> None:
        """Ask MEMORY agent to store the task result."""
        payload = f"Task: {task}\nResult: {summary}"
        self._send("orchestrator", "jarvis_memory", payload)
        self._call_agent(AgentRole.MEMORY, payload)

    def run_task(self, task: str) -> OrchestratorResult:
        """Run a task through the full PLANNER→EXECUTOR→CRITIC→MEMORY pipeline.

        Returns an OrchestratorResult with steps, outputs, critique, and timing.
        """
        t0 = time.time()
        task_id = str(uuid.uuid4())[:8]
        self._active = True

        try:
            # 1. Plan
            steps = self._plan(task)

            # 2. Execute each step
            outputs: List[str] = []
            for step in steps:
                step.status = "running"
                out = self._execute_step(step)
                step.output = out
                step.status = "done"
                outputs.append(out)

            # 3. Critique
            critique = self._critique(outputs)
            success = critique.upper().startswith("PASS") or "PASS" in critique[:20]

            # 4. Memorise
            self._memorise(task, outputs[-1] if outputs else "")

            elapsed = time.time() - t0
            result = OrchestratorResult(
                task=task,
                task_id=task_id,
                steps=steps,
                outputs=outputs,
                critique=critique,
                success=success,
                elapsed=elapsed,
                agent_messages=list(self._message_log),
            )
            with self._lock:
                self._results.append(result)
            return result

        finally:
            self._active = False

    # ------------------------------------------------------------------
    # Status / introspection
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Return a JSON-serialisable status snapshot."""
        return {
            "active": self._active,
            "agents": [
                {"role": a.role.value, "name": a.name, "model": a.model}
                for a in self._agents.values()
            ],
            "tasks_completed": len(self._results),
            "messages_total": len(self._message_log),
        }

    def recent_results(self, n: int = 5) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._results[-n:]]
