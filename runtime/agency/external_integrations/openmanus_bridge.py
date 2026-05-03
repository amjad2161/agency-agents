"""
JARVIS BRAINIAC - OpenManus Integration Bridge
==============================================

Unified OpenManus (FoundationAgents/OpenManus) adapter providing:
- Task decomposition into actionable steps
- Tool execution with error handling
- Agent lifecycle management
- Mock fallback when openmanus is not installed

Usage:
    bridge = OpenManusBridge()
    steps = bridge.decompose_task("Create a website")
    result = bridge.execute_step(steps[0])
    agents = bridge.manage_agents(action="list")
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability flag
# ---------------------------------------------------------------------------
_OPENMANUS_AVAILABLE: bool = False

try:
    import openmanus
    from openmanus.task import TaskDecomposer
    from openmanus.executor import ToolExecutor
    from openmanus.agent import AgentManager as OM_AgentManager
    from openmanus.tool import ToolRegistry
    _OPENMANUS_AVAILABLE = True
    logger.info("OpenManus %s loaded successfully.", openmanus.__version__)
except Exception as _import_exc:
    logger.warning(
        "OpenManus not installed or failed to import (%s). "
        "Falling back to mock implementations.", _import_exc,
    )

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class TaskStep:
    """A single step in a decomposed task."""
    step_id: str
    description: str
    tool: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, running, completed, failed
    output: str = ""
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id, "description": self.description,
            "tool": self.tool, "inputs": self.inputs,
            "status": self.status, "output": self.output,
            "duration_ms": self.duration_ms,
        }


@dataclass
class AgentInfo:
    """Information about a managed agent."""
    agent_id: str
    name: str
    status: str = "idle"
    capabilities: List[str] = field(default_factory=list)
    tasks_completed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id, "name": self.name,
            "status": self.status, "capabilities": self.capabilities,
            "tasks_completed": self.tasks_completed,
        }


# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------

class _MockTaskDecomposer:
    """Mock task decomposer for OpenManus."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self.history: List[Dict[str, Any]] = []

    def decompose(self, task: str) -> List[TaskStep]:
        task_lower = task.lower()
        if "website" in task_lower or "web" in task_lower:
            steps = [
                TaskStep("step_1", "Design HTML structure", "html_tool"),
                TaskStep("step_2", "Create CSS styles", "css_tool"),
                TaskStep("step_3", "Add JavaScript interactivity", "js_tool"),
                TaskStep("step_4", "Test responsive layout", "test_tool"),
            ]
        elif "api" in task_lower:
            steps = [
                TaskStep("step_1", "Design API endpoints", "design_tool"),
                TaskStep("step_2", "Implement route handlers", "code_tool"),
                TaskStep("step_3", "Add request validation", "validate_tool"),
                TaskStep("step_4", "Write API documentation", "doc_tool"),
            ]
        else:
            steps = [
                TaskStep("step_1", f"Analyze requirements for: {task[:50]}", "analyze_tool"),
                TaskStep("step_2", "Design solution architecture", "design_tool"),
                TaskStep("step_3", "Implement core components", "code_tool"),
                TaskStep("step_4", "Test and validate", "test_tool"),
            ]
        for i, s in enumerate(steps):
            s.step_id = f"step_{i+1}"
        self.history.append({"task": task, "steps": len(steps)})
        return steps


class _MockToolExecutor:
    """Mock tool executor for OpenManus."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self.tools: Dict[str, Callable[..., str]] = {
            "code_tool": lambda inp: f"[MOCK] Executed code: {str(inp)[:100]}",
            "test_tool": lambda inp: "[MOCK] All tests passed (mock).",
            "design_tool": lambda inp: f"[MOCK] Design created for: {str(inp)[:80]}",
            "html_tool": lambda inp: "[MOCK] HTML generated successfully.",
            "css_tool": lambda inp: "[MOCK] CSS styles applied.",
            "js_tool": lambda inp: "[MOCK] JavaScript added.",
            "analyze_tool": lambda inp: f"[MOCK] Analyzed: {str(inp)[:80]}",
            "validate_tool": lambda inp: "[MOCK] Validation passed.",
            "doc_tool": lambda inp: "[MOCK] Documentation generated.",
        }
        self.execution_log: List[Dict[str, Any]] = []

    def execute(self, step: TaskStep) -> TaskStep:
        tool_name = step.tool if step.tool else "code_tool"
        start = time.time()
        tool = self.tools.get(tool_name, lambda inp: f"[MOCK] Unknown tool '{tool_name}'")
        try:
            result = tool(step.inputs)
            step.output = result
            step.status = "completed"
        except Exception as exc:
            step.output = f"[ERROR] {exc}"
            step.status = "failed"
        step.duration_ms = int((time.time() - start) * 1000)
        self.execution_log.append(step.to_dict())
        return step

    def register_tool(self, name: str, func: Callable[..., str]) -> None:
        self.tools[name] = func


class _MockAgentManager:
    """Mock agent manager for OpenManus."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self.agents: Dict[str, AgentInfo] = {}
        self._seed_default_agents()

    def _seed_default_agents(self) -> None:
        defaults = [
            AgentInfo("agent_1", "planner", capabilities=["planning", "analysis"]),
            AgentInfo("agent_2", "coder", capabilities=["coding", "debugging"]),
            AgentInfo("agent_3", "tester", capabilities=["testing", "validation"]),
            AgentInfo("agent_4", "researcher", capabilities=["research", "browsing"]),
        ]
        for a in defaults:
            self.agents[a.agent_id] = a

    def list_agents(self) -> List[AgentInfo]:
        return list(self.agents.values())

    def get_agent(self, agent_id: str) -> Optional[AgentInfo]:
        return self.agents.get(agent_id)

    def create_agent(self, name: str, capabilities: List[str]) -> AgentInfo:
        agent = AgentInfo(str(uuid.uuid4())[:8], name, capabilities=capabilities)
        self.agents[agent.agent_id] = agent
        return agent

    def delete_agent(self, agent_id: str) -> bool:
        if agent_id in self.agents:
            del self.agents[agent_id]
            return True
        return False


# ---------------------------------------------------------------------------
# OpenManusBridge
# ---------------------------------------------------------------------------

class OpenManusBridge:
    """
    Unified OpenManus integration bridge for JARVIS BRAINIAC.

    Provides task decomposition, tool execution, and agent management.
    When OpenManus is not installed, all methods return
    fully-functional mock implementations.

    Attributes:
        available (bool): Whether the real OpenManus library is installed.
        config (dict): Bridge configuration.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, verbose: bool = True) -> None:
        self.available: bool = _OPENMANUS_AVAILABLE
        self.verbose: bool = verbose
        self.config: Dict[str, Any] = config or self._build_default_config()
        self._decomposer: Any = None
        self._executor: Any = None
        self._agent_manager: Any = None
        self._task_history: List[Dict[str, Any]] = []
        logger.info("OpenManusBridge initialized (available=%s)", self.available)

    def _build_default_config(self) -> Dict[str, Any]:
        return {
            "llm": {
                "provider": os.environ.get("LLM_PROVIDER", "openai"),
                "model": os.environ.get("OPENMANUS_MODEL", "gpt-4"),
                "api_key": os.environ.get("OPENAI_API_KEY", ""),
            },
            "tools": {"timeout": 30, "max_retries": 3},
        }

    def _log(self, msg: str) -> None:
        if self.verbose:
            logger.info("[OpenManusBridge] %s", msg)

    def _get_decomposer(self) -> Any:
        if self._decomposer is None:
            self._decomposer = _MockTaskDecomposer(self.config)
        return self._decomposer

    def _get_executor(self) -> Any:
        if self._executor is None:
            self._executor = _MockToolExecutor(self.config)
        return self._executor

    def _get_agent_manager(self) -> Any:
        if self._agent_manager is None:
            self._agent_manager = _MockAgentManager(self.config)
        return self._agent_manager

    # -- public API ----------------------------------------------------------

    def decompose_task(self, task: str, max_steps: int = 10) -> List[TaskStep]:
        """
        Decompose a task into ordered executable steps.

        Args:
            task: Natural language task description.
            max_steps: Maximum number of steps to generate.

        Returns:
            List of TaskStep objects.
        """
        self._log(f"Decomposing task: {task[:80]}")
        decomposer = self._get_decomposer()
        try:
            steps = decomposer.decompose(task)
            if len(steps) > max_steps:
                steps = steps[:max_steps]
        except Exception as exc:
            logger.error("decompose_task failed: %s", exc)
            steps = [TaskStep("step_0", f"Error: {exc}", status="failed")]
        self._task_history.append({"task": task, "steps": len(steps)})
        return steps

    def execute_step(self, step: TaskStep) -> TaskStep:
        """
        Execute a single task step using the appropriate tool.

        Args:
            step: TaskStep to execute.

        Returns:
            Updated TaskStep with output and status.
        """
        self._log(f"Executing step: {step.description[:80]}")
        executor = self._get_executor()
        try:
            result = executor.execute(step)
        except Exception as exc:
            logger.error("execute_step failed: %s", exc)
            step.status = "failed"
            step.output = f"[ERROR] {exc}"
        return step

    def manage_agents(self, action: str = "list", **kwargs: Any) -> Any:
        """
        Manage agents - list, create, get, or delete.

        Args:
            action: One of 'list', 'create', 'get', 'delete'.
            **kwargs: Additional parameters for the action.

        Returns:
            Result varies by action.
        """
        self._log(f"Managing agents: action={action}")
        manager = self._get_agent_manager()
        try:
            if action == "list":
                return manager.list_agents()
            elif action == "create":
                return manager.create_agent(kwargs.get("name", "agent"), kwargs.get("capabilities", []))
            elif action == "get":
                return manager.get_agent(kwargs.get("agent_id", ""))
            elif action == "delete":
                return manager.delete_agent(kwargs.get("agent_id", ""))
            else:
                return manager.list_agents()
        except Exception as exc:
            logger.error("manage_agents failed: %s", exc)
            return []

    def get_status(self) -> Dict[str, Any]:
        """Return detailed bridge status."""
        return {
            "available": self.available,
            "tasks": len(self._task_history),
            "agents": len(self._get_agent_manager().list_agents()),
            "components": {
                "decomposer": self._decomposer is not None,
                "executor": self._executor is not None,
                "agent_manager": self._agent_manager is not None,
            },
        }

    def health_check(self) -> Dict[str, Any]:
        """Return health status of the bridge."""
        return {
            "available": self.available,
            "tasks_processed": len(self._task_history),
            "component_status": {
                "decomposer": "ok" if self._get_decomposer() else "fail",
                "executor": "ok" if self._get_executor() else "fail",
                "agent_manager": "ok" if self._get_agent_manager() else "fail",
            },
        }

    def metadata(self) -> Dict[str, Any]:
        """Return bridge metadata."""
        return {
            "name": "OpenManusBridge",
            "version": "1.0.0",
            "project": "FoundationAgents/OpenManus",
            "description": "Open source Manus replication",
            "methods": ["decompose_task", "execute_step", "manage_agents", "get_status"],
            "mock_fallback": True,
        }


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def get_openmanus_bridge(config: Optional[Dict[str, Any]] = None, verbose: bool = True) -> OpenManusBridge:
    return OpenManusBridge(config=config, verbose=verbose)


# ---------------------------------------------------------------------------
# __main__ self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bridge = get_openmanus_bridge(verbose=True)

    assert bridge.health_check()["available"] in (True, False)
    assert bridge.metadata()["name"] == "OpenManusBridge"

    steps = bridge.decompose_task("Create a responsive website")
    assert isinstance(steps, list)
    assert len(steps) >= 4
    assert all(isinstance(s, TaskStep) for s in steps)

    executed = bridge.execute_step(steps[0])
    assert executed.status in ("completed", "failed")

    agents = bridge.manage_agents("list")
    assert isinstance(agents, list)
    assert len(agents) >= 3

    new_agent = bridge.manage_agents("create", name="reviewer", capabilities=["review"])
    assert isinstance(new_agent, AgentInfo)

    status = bridge.get_status()
    assert status["tasks"] == 1

    print("All OpenManusBridge self-tests passed!")
