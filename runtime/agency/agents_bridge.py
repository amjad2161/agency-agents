"""
================================================================================
                       JARVIS BRAINIAC — Agents Bridge
================================================================================

Production-grade integration adapter between **JARVIS BRAINIAC** and
**Agent-S / OpenAI Agents** (the ``openai-agents`` / ``agents`` SDK).

Provides a unified, async-first interface for:
    - Creating LLM agents with custom instructions & model selection
    - Registering tools (functions) that agents can invoke
    - Running agents end-to-end with full input / output handling
    - Handoff orchestration between specialised agents
    - Complete execution tracing for observability & debugging

If ``openai-agents`` / ``agents`` is not installed every method degrades
gracefully to a **mock implementation** that logs calls, returns sensible
sentinel objects, and never raises ``ImportError`` so downstream code stays
stable.

Design principles
-----------------
1. **Single-responsibility** — one class orchestrates the agent graph.
2. **Fail-soft** — missing SDK → mock, never ``ImportError``.
3. **Type-safe** — full type hints + generics.
4. **Observable** — structured logging + optional tracing callbacks.
5. **Composable** — agents, tools, and handoffs are plain Python objects.

================================================================================
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    runtime_checkable,
)

# ---------------------------------------------------------------------------
# Structured logger
# ---------------------------------------------------------------------------
_LOGGER = logging.getLogger("jarvis.runtime.agency.agents_bridge")

# ---------------------------------------------------------------------------
# Optional dependency discovery — OpenAI Agents (a.k.a. Agent-S)
# ---------------------------------------------------------------------------
try:
    import agents  # type: ignore[import-untyped]
    from agents import Agent, Runner, RunResult  # type: ignore[import-untyped]
    from agents.tool import FunctionTool  # type: ignore[import-untyped]

    _AGENTS_SDK_AVAILABLE = True
    _AGENTS_SDK_VERSION = getattr(agents, "__version__", "unknown")
    _LOGGER.info("agents-sdk %s loaded", _AGENTS_SDK_VERSION)
except ImportError:
    try:
        import openai.agents  # type: ignore[import-untyped]

        _AGENTS_SDK_AVAILABLE = True
        _AGENTS_SDK_VERSION = getattr(openai.agents, "__version__", "unknown")
        _LOGGER.info("openai-agents %s loaded", _AGENTS_SDK_AVAILABLE)
    except ImportError:
        _AGENTS_SDK_AVAILABLE = False
        _AGENTS_SDK_VERSION = None
        _LOGGER.warning(
            "openai-agents / agents SDK not installed — falling back to mock bridge"
        )


# =============================================================================
#  Domain models
# =============================================================================


class RunStatus(Enum):
    """High-level lifecycle status of an agent run."""

    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    HANDOFF = auto()
    CANCELLED = auto()


@dataclass
class ToolDefinition:
    """Portable description of a tool that can be attached to an agent."""

    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    handler: Optional[Callable[..., Any]] = None
    is_async: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "is_async": self.is_async,
        }


@dataclass
class AgentDescriptor:
    """Lightweight handle returned by :meth:`AgentsBridge.create_agent`."""

    agent_id: str
    name: str
    instructions: str
    model: str
    tools: List[str] = field(default_factory=list)
    handoff_targets: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    raw_agent: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "instructions": self.instructions[:200],
            "model": self.model,
            "tools": self.tools,
            "handoff_targets": self.handoff_targets,
            "created_at": self.created_at,
        }


@dataclass
class ToolResult:
    """Structured result produced by a tool invocation."""

    tool_name: str
    output: Any
    duration_ms: float = 0.0
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    @property
    def is_error(self) -> bool:
        return self.error is not None


@dataclass
class RunTrace:
    """Full execution trace of a single agent run."""

    trace_id: str
    agent_id: str
    agent_name: str
    input_text: str
    status: RunStatus
    started_at: float
    finished_at: Optional[float] = None
    final_output: Optional[str] = None
    tool_calls: List[ToolResult] = field(default_factory=list)
    handoff_path: List[str] = field(default_factory=list)
    raw_events: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def duration_ms(self) -> float:
        if self.finished_at is None:
            return (time.time() - self.started_at) * 1000.0
        return (self.finished_at - self.started_at) * 1000.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "input_text": self.input_text,
            "status": self.status.name,
            "duration_ms": self.duration_ms,
            "final_output": self.final_output,
            "tool_calls": [asdict(tc) for tc in self.tool_calls],
            "handoff_path": self.handoff_path,
            "error": self.error,
        }


@dataclass
class BridgeMetrics:
    """Runtime counters surfaced for observability."""

    agents_created: int = 0
    runs_started: int = 0
    runs_completed: int = 0
    runs_failed: int = 0
    handoffs_performed: int = 0
    tool_calls_total: int = 0
    tool_calls_failed: int = 0
    total_run_duration_ms: float = 0.0
    start_time: float = field(default_factory=time.time)

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.start_time


# =============================================================================
#  Callback protocols
# =============================================================================


@runtime_checkable
class RunStartedCallback(Protocol):
    """Called when an agent run begins."""

    async def __call__(self, trace: RunTrace) -> None:
        ...


@runtime_checkable
class ToolCallCallback(Protocol):
    """Called immediately before a tool is invoked."""

    async def __call__(self, tool_name: str, arguments: Dict[str, Any]) -> None:
        ...


@runtime_checkable
class HandoffCallback(Protocol):
    """Called when a handoff between agents is about to happen."""

    async def __call__(self, from_agent: str, to_agent: str, context: str) -> None:
        ...


# =============================================================================
#  Internal helpers
# =============================================================================

def _generate_id(prefix: str = "ag") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now() -> float:
    return time.time()


# =============================================================================
#  AgentsBridge
# =============================================================================


class AgentsBridge:
    """Unified async bridge to the OpenAI Agents (Agent-S) ecosystem.

    Parameters
    ----------
    default_model :
        Model identifier used when an agent is created without an explicit
        ``model`` argument.  Defaults to ``gpt-4o``.

    Usage
    -----
    .. code-block:: python

        bridge = AgentsBridge()
        greeter = await bridge.create_agent(
            name="Greeter",
            instructions="You are a friendly greeter. Keep responses short.",
            model="gpt-4o-mini",
        )

        bridge.add_tool(my_weather_tool)
        result = await bridge.run_agent(greeter, "Say hi to the team")

        # Handoff
        expert = await bridge.create_agent(name="Expert", instructions="...")
        handoff_result = await bridge.handoff(greeter, expert, "deep question")

        # Full trace
        trace = await bridge.trace_run(greeter, "Hello")
        print(trace.to_dict())
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def __init__(self, default_model: str = "gpt-4o") -> None:
        self._default_model = default_model

        # Registry
        self._agents: Dict[str, AgentDescriptor] = {}
        self._tools: Dict[str, ToolDefinition] = {}
        self._raw_tools: Dict[str, Any] = {}  # SDK tool objects when available

        # Metrics
        self._metrics = BridgeMetrics()

        # Callbacks
        self._run_started_callbacks: List[RunStartedCallback] = []
        self._tool_call_callbacks: List[ToolCallCallback] = []
        self._handoff_callbacks: List[HandoffCallback] = []

        # Traces
        self._traces: Dict[str, RunTrace] = {}

        _LOGGER.info(
            "AgentsBridge created — default_model=%s agents_sdk_available=%s",
            self._default_model,
            _AGENTS_SDK_AVAILABLE,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def default_model(self) -> str:
        return self._default_model

    @property
    def metrics(self) -> BridgeMetrics:
        return self._metrics

    @property
    def is_mock(self) -> bool:
        return not _AGENTS_SDK_AVAILABLE

    @property
    def agent_count(self) -> int:
        return len(self._agents)

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    # ------------------------------------------------------------------
    # create_agent
    # ------------------------------------------------------------------
    async def create_agent(
        self,
        name: str,
        instructions: str,
        model: Optional[str] = None,
        handoff_description: Optional[str] = None,
    ) -> AgentDescriptor:
        """Create a new agent and register it in the bridge.

        Parameters
        ----------
        name :
            Human-readable agent name (must be unique within this bridge).
        instructions :
            System prompt / persona text given to the LLM.
        model :
            Model override, e.g. ``gpt-4o``, ``gpt-4o-mini``, ``o3-mini``.
        handoff_description :
            Optional description used by *upstream* agents to decide whether
            to hand off to this one.

        Returns
        -------
        AgentDescriptor
            Handle containing metadata and (when available) the raw SDK agent.
        """
        agent_id = _generate_id("agent")
        chosen_model = model or self._default_model

        raw_agent: Optional[Any] = None

        if _AGENTS_SDK_AVAILABLE:
            try:
                raw_agent = self._build_sdk_agent(
                    name=name,
                    instructions=instructions,
                    model=chosen_model,
                    handoff_description=handoff_description,
                )
            except Exception as exc:
                _LOGGER.warning("SDK agent creation failed (%s) — using stub", exc)
                raw_agent = None

        descriptor = AgentDescriptor(
            agent_id=agent_id,
            name=name,
            instructions=instructions,
            model=chosen_model,
            raw_agent=raw_agent,
        )
        self._agents[agent_id] = descriptor
        self._metrics.agents_created += 1

        _LOGGER.info(
            "create_agent: %s (%s) model=%s", name, agent_id, chosen_model
        )
        return descriptor

    def _build_sdk_agent(
        self,
        name: str,
        instructions: str,
        model: str,
        handoff_description: Optional[str] = None,
    ) -> Any:
        """Construct a real ``agents.Agent`` instance."""
        kwargs: Dict[str, Any] = {
            "name": name,
            "instructions": instructions,
            "model": model,
        }
        if handoff_description:
            kwargs["handoff_description"] = handoff_description

        # Attach any tools that have already been registered globally
        sdk_tools = list(self._raw_tools.values())
        if sdk_tools:
            kwargs["tools"] = sdk_tools

        agent = Agent(**kwargs)
        _LOGGER.debug("SDK Agent built for '%s' with model %s", name, model)
        return agent

    # ------------------------------------------------------------------
    # add_tool
    # ------------------------------------------------------------------
    def add_tool(self, tool: Union[ToolDefinition, Callable[..., Any], Any]) -> None:
        """Register a tool that agents can invoke.

        Accepts three shapes:

        1. :class:`ToolDefinition` — the bridge's native representation.
        2. A plain Python callable — auto-wrapped into a :class:`ToolDefinition`.
        3. A raw SDK ``FunctionTool`` — stored as-is when the SDK is present.

        Parameters
        ----------
        tool :
            Tool to register.
        """
        if isinstance(tool, ToolDefinition):
            definition = tool
        elif callable(tool) and not hasattr(tool, "name"):
            # Plain callable — synthesise a definition
            definition = ToolDefinition(
                name=getattr(tool, "__name__", "unnamed_tool"),
                description=getattr(tool, "__doc__", "") or "No description",
                handler=tool,
                is_async=asyncio.iscoroutinefunction(tool),
            )
        elif hasattr(tool, "name") and hasattr(tool, "description"):
            # Looks like an SDK FunctionTool or compatible object
            definition = ToolDefinition(
                name=tool.name,
                description=tool.description,
            )
            self._raw_tools[tool.name] = tool
        else:
            raise TypeError(
                f"Cannot register tool of type {type(tool).__name__}. "
                "Expected ToolDefinition, callable, or SDK FunctionTool."
            )

        self._tools[definition.name] = definition

        # If SDK is available and we have a handler, attempt to create a
        # proper FunctionTool wrapper so SDK agents can call it.
        if _AGENTS_SDK_AVAILABLE and definition.handler is not None:
            try:
                sdk_tool = self._wrap_to_sdk_tool(definition)
                self._raw_tools[definition.name] = sdk_tool
                _LOGGER.debug("Wrapped '%s' as SDK FunctionTool", definition.name)
            except Exception as exc:
                _LOGGER.debug("Could not wrap '%s' for SDK: %s", definition.name, exc)

        _LOGGER.info("add_tool: %s (%d total)", definition.name, len(self._tools))

    def _wrap_to_sdk_tool(self, definition: ToolDefinition) -> Any:
        """Convert a :class:`ToolDefinition` into an SDK ``FunctionTool``."""
        try:
            from agents.tool import function_tool  # type: ignore[import-untyped]

            if definition.is_async:
                @function_tool(
                    name_=definition.name,
                    description_=definition.description,
                )
                async def _async_wrapper(**kwargs: Any) -> str:
                    return await definition.handler(**kwargs)  # type: ignore[misc]

                return _async_wrapper
            else:
                @function_tool(
                    name_=definition.name,
                    description_=definition.description,
                )
                def _sync_wrapper(**kwargs: Any) -> str:
                    result = definition.handler(**kwargs)  # type: ignore[misc]
                    return str(result)

                return _sync_wrapper
        except ImportError:
            _LOGGER.debug("function_tool decorator not available")
            return None

    # ------------------------------------------------------------------
    # run_agent
    # ------------------------------------------------------------------
    async def run_agent(
        self,
        agent: AgentDescriptor,
        input: Union[str, List[Dict[str, str]]],
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> RunTrace:
        """Execute an agent against an input and return the full trace.

        Parameters
        ----------
        agent :
            Descriptor returned by :meth:`create_agent`.
        input :
            Either a plain text string or a message list (OpenAI chat-format).
        context :
            Optional key/value context injected into the run.

        Returns
        -------
        RunTrace
            Complete execution record including output, tool calls, timing.
        """
        trace_id = _generate_id("trace")
        input_text = input if isinstance(input, str) else json.dumps(input)
        context = context or {}

        trace = RunTrace(
            trace_id=trace_id,
            agent_id=agent.agent_id,
            agent_name=agent.name,
            input_text=input_text,
            status=RunStatus.RUNNING,
            started_at=_now(),
        )
        self._traces[trace_id] = trace
        self._metrics.runs_started += 1

        # Notify listeners
        for cb in self._run_started_callbacks:
            try:
                await cb(trace)
            except Exception as exc:
                _LOGGER.warning("run_started callback error: %s", exc)

        if _AGENTS_SDK_AVAILABLE and agent.raw_agent is not None:
            await self._run_with_sdk(agent, input, context, trace)
        else:
            await self._run_mock(agent, input_text, context, trace)

        trace.finished_at = _now()
        self._metrics.total_run_duration_ms += trace.duration_ms

        if trace.status == RunStatus.FAILED:
            self._metrics.runs_failed += 1
        else:
            self._metrics.runs_completed += 1

        _LOGGER.info(
            "run_agent finished: %s status=%s duration=%.1fms",
            trace.trace_id,
            trace.status.name,
            trace.duration_ms,
        )
        return trace

    async def _run_with_sdk(
        self,
        agent: AgentDescriptor,
        input: Union[str, List[Dict[str, str]]],
        context: Dict[str, Any],
        trace: RunTrace,
    ) -> None:
        """Execute using the real OpenAI Agents SDK."""
        try:
            # Refresh tools on the agent instance in case new ones were
            # registered after the agent was created.
            if self._raw_tools:
                agent.raw_agent.tools = list(self._raw_tools.values())

            result = Runner.run_sync(agent.raw_agent, input)

            # Extract output
            trace.final_output = getattr(result, "final_output", str(result))

            # Extract tool calls from the raw result
            raw_events = getattr(result, "raw_responses", []) or [result]
            for ev in raw_events:
                trace.raw_events.append(self._serialise_event(ev))

            # Look for tool_call items
            for item in getattr(result, "new_items", []):
                if hasattr(item, "type") and item.type == "tool_call":
                    tool_name = getattr(item, "name", "unknown")
                    tool_output = getattr(item, "output", None)
                    tool_error = getattr(item, "error", None)
                    tr = ToolResult(
                        tool_name=tool_name,
                        output=tool_output,
                        error=str(tool_error) if tool_error else None,
                    )
                    trace.tool_calls.append(tr)
                    self._metrics.tool_calls_total += 1
                    if tool_error:
                        self._metrics.tool_calls_failed += 1

            trace.status = RunStatus.COMPLETED

        except Exception as exc:
            trace.status = RunStatus.FAILED
            trace.error = str(exc)
            self._metrics.runs_failed += 1
            _LOGGER.error("SDK run failed: %s", exc)

    async def _run_mock(
        self,
        agent: AgentDescriptor,
        input_text: str,
        context: Dict[str, Any],
        trace: RunTrace,
    ) -> None:
        """Mock execution — logs everything, returns a canned response."""
        _LOGGER.info(
            "[MOCK] run_agent: %s (model=%s) input=%r",
            agent.name,
            agent.model,
            input_text[:200],
        )

        # Simulate latency
        await asyncio.sleep(0.05)

        # If the input references any registered tools, "call" them
        for tool_name, definition in self._tools.items():
            if tool_name.lower() in input_text.lower():
                _LOGGER.info("[MOCK] Detected tool reference: %s", tool_name)
                for cb in self._tool_call_callbacks:
                    try:
                        await cb(tool_name, {})
                    except Exception:
                        pass

                tr = ToolResult(
                    tool_name=tool_name,
                    output=f"[MOCK] Result from {tool_name}",
                    duration_ms=10.0,
                )
                trace.tool_calls.append(tr)
                self._metrics.tool_calls_total += 1

        trace.final_output = (
            f"[MOCK] Agent '{agent.name}' processed: "
            f"{input_text[:120]}{'...' if len(input_text) > 120 else ''}"
        )
        trace.status = RunStatus.COMPLETED

    # ------------------------------------------------------------------
    # handoff
    # ------------------------------------------------------------------
    async def handoff(
        self,
        from_agent: AgentDescriptor,
        to_agent: AgentDescriptor,
        context: str,
        *,
        carry_history: bool = True,
    ) -> RunTrace:
        """Transfer control from one agent to another.

        Parameters
        ----------
        from_agent :
            Currently active agent.
        to_agent :
            Destination agent that takes over.
        context :
            Description of *why* the handoff is happening (shown to the
            destination agent).
        carry_history :
            When ``True`` the conversation history is forwarded to the new
            agent.

        Returns
        -------
        RunTrace
            Execution trace of the *destination* agent's run.
        """
        trace_id = _generate_id("handoff")

        # Update registry
        if from_agent.agent_id in self._agents:
            fa = self._agents[from_agent.agent_id]
            if to_agent.agent_id not in fa.handoff_targets:
                fa.handoff_targets.append(to_agent.agent_id)

        # Notify listeners
        for cb in self._handoff_callbacks:
            try:
                await cb(from_agent.name, to_agent.name, context)
            except Exception as exc:
                _LOGGER.warning("handoff callback error: %s", exc)

        self._metrics.handoffs_performed += 1
        _LOGGER.info(
            "handoff: %s → %s  context=%r",
            from_agent.name,
            to_agent.name,
            context[:100],
        )

        if _AGENTS_SDK_AVAILABLE and to_agent.raw_agent is not None:
            # Build a handoff-aware prompt
            handoff_input = (
                f"[Handoff from {from_agent.name}]\n"
                f"Reason: {context}\n"
                f"Please take over and assist the user."
            )
            trace = await self.run_agent(to_agent, handoff_input)
        else:
            # Mock path
            trace = RunTrace(
                trace_id=trace_id,
                agent_id=to_agent.agent_id,
                agent_name=to_agent.name,
                input_text=context,
                status=RunStatus.RUNNING,
                started_at=_now(),
            )
            self._traces[trace_id] = trace
            await asyncio.sleep(0.03)
            trace.final_output = (
                f"[MOCK] Handoff from '{from_agent.name}' to "
                f"'{to_agent.name}' — context: {context[:100]}"
            )
            trace.handoff_path = [from_agent.agent_id, to_agent.agent_id]
            trace.status = RunStatus.COMPLETED
            trace.finished_at = _now()
            self._metrics.runs_completed += 1

        trace.handoff_path = [from_agent.agent_id, to_agent.agent_id]
        _LOGGER.info("handoff complete: trace=%s", trace.trace_id)
        return trace

    # ------------------------------------------------------------------
    # trace_run
    # ------------------------------------------------------------------
    async def trace_run(
        self,
        agent: AgentDescriptor,
        input: Union[str, List[Dict[str, str]]],
    ) -> RunTrace:
        """Run an agent and return the **complete** trace including raw events.

        This is a convenience wrapper around :meth:`run_agent` that guarantees
        full observability regardless of SDK availability.

        Parameters
        ----------
        agent :
            Descriptor of the agent to run.
        input :
            Text or structured message list.

        Returns
        -------
        RunTrace
            Full trace object.
        """
        return await self.run_agent(agent, input)

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------
    def on_run_started(self, callback: RunStartedCallback) -> RunStartedCallback:
        """Register a callback invoked when any agent run starts."""
        self._run_started_callbacks.append(callback)
        _LOGGER.debug("on_run_started callback registered (%d total)", len(self._run_started_callbacks))
        return callback

    def on_tool_call(self, callback: ToolCallCallback) -> ToolCallCallback:
        """Register a callback invoked before every tool call."""
        self._tool_call_callbacks.append(callback)
        _LOGGER.debug("on_tool_call callback registered (%d total)", len(self._tool_call_callbacks))
        return callback

    def on_handoff(self, callback: HandoffCallback) -> HandoffCallback:
        """Register a callback invoked before every handoff."""
        self._handoff_callbacks.append(callback)
        _LOGGER.debug("on_handoff callback registered (%d total)", len(self._handoff_callbacks))
        return callback

    # ------------------------------------------------------------------
    # Registry introspection
    # ------------------------------------------------------------------
    def list_agents(self) -> List[AgentDescriptor]:
        """Return all registered agent descriptors."""
        return list(self._agents.values())

    def get_agent(self, agent_id: str) -> Optional[AgentDescriptor]:
        """Look up a single agent by its ID."""
        return self._agents.get(agent_id)

    def list_tools(self) -> List[ToolDefinition]:
        """Return all registered tool definitions."""
        return list(self._tools.values())

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Look up a tool by name."""
        return self._tools.get(name)

    def get_trace(self, trace_id: str) -> Optional[RunTrace]:
        """Retrieve a previously recorded trace."""
        return self._traces.get(trace_id)

    def list_traces(
        self, *, agent_id: Optional[str] = None, limit: int = 100
    ) -> List[RunTrace]:
        """List traces with optional filtering.

        Parameters
        ----------
        agent_id :
            When provided, only traces for that agent are returned.
        limit :
            Maximum number of traces to return (most recent first).
        """
        traces = list(self._traces.values())
        if agent_id:
            traces = [t for t in traces if t.agent_id == agent_id]
        traces.sort(key=lambda t: t.started_at, reverse=True)
        return traces[:limit]

    # ------------------------------------------------------------------
    # Utility / serialisation helpers
    # ------------------------------------------------------------------
    def _serialise_event(self, event: Any) -> Dict[str, Any]:
        """Best-effort convert an SDK event object to a plain dict."""
        if hasattr(event, "model_dump"):
            return event.model_dump()  # type: ignore[union-attr]
        if hasattr(event, "__dict__"):
            return {k: str(v) for k, v in event.__dict__.items()}
        return {"repr": repr(event)}

    # ------------------------------------------------------------------
    # Batch helpers
    # ------------------------------------------------------------------
    async def run_parallel(
        self,
        agent: AgentDescriptor,
        inputs: Sequence[Union[str, List[Dict[str, str]]]],
        *,
        max_concurrency: int = 5,
    ) -> List[RunTrace]:
        """Run the same agent against multiple inputs in parallel.

        Parameters
        ----------
        agent :
            Agent descriptor to use for every run.
        inputs :
            Sequence of input texts or message lists.
        max_concurrency :
            Semaphore-bound maximum number of concurrent runs.

        Returns
        -------
        list[RunTrace]
            One trace per input, in the same order as *inputs*.
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _run_one(inp: Union[str, List[Dict[str, str]]]) -> RunTrace:
            async with semaphore:
                return await self.run_agent(agent, inp)

        tasks = [asyncio.create_task(_run_one(inp)) for inp in inputs]
        return await asyncio.gather(*tasks)

    async def run_sequential(
        self,
        agent: AgentDescriptor,
        inputs: Sequence[Union[str, List[Dict[str, str]]]],
    ) -> List[RunTrace]:
        """Run the same agent against multiple inputs sequentially.

        Unlike :meth:`run_parallel`, each run receives the previous run's
        output as conversational context.

        Returns
        -------
        list[RunTrace]
            One trace per input, in order.
        """
        traces: List[RunTrace] = []
        conversation: List[Dict[str, str]] = []

        for inp in inputs:
            if isinstance(inp, str):
                conversation.append({"role": "user", "content": inp})
            else:
                conversation.extend(inp)

            trace = await self.run_agent(agent, conversation)
            traces.append(trace)

            if trace.final_output:
                conversation.append(
                    {"role": "assistant", "content": trace.final_output}
                )

        return traces

    def __repr__(self) -> str:
        return (
            f"AgentsBridge(agents={self.agent_count}, "
            f"tools={self.tool_count}, "
            f"mock={self.is_mock})"
        )


# =============================================================================
#  Factory function
# =============================================================================


def get_agents_bridge(default_model: str = "gpt-4o") -> AgentsBridge:
    """Factory — construct and return an :class:`AgentsBridge`.

    Parameters
    ----------
    default_model :
        Model identifier used as the default for all created agents.

    Returns
    -------
    AgentsBridge
        Fully initialised bridge.
    """
    return AgentsBridge(default_model=default_model)


# =============================================================================
#  Pre-built tool factories (convenience)
# =============================================================================


def create_search_tool(
    search_func: Callable[[str], Union[str, Awaitable[str]]],
) -> ToolDefinition:
    """Wrap an arbitrary search function into a :class:`ToolDefinition`.

    Parameters
    ----------
    search_func :
        Callable taking a query string and returning results.

    Returns
    -------
    ToolDefinition
        Ready to be passed to :meth:`AgentsBridge.add_tool`.
    """
    return ToolDefinition(
        name="search",
        description="Search an external knowledge base or search engine.",
        parameters={
            "query": {
                "type": "string",
                "description": "The search query",
            }
        },
        handler=search_func,
        is_async=asyncio.iscoroutinefunction(search_func),
    )


def create_calculator_tool() -> ToolDefinition:
    """Return a built-in calculator tool definition."""

    def _calc(expression: str) -> str:
        """Evaluate a mathematical expression safely."""
        try:
            # Only permit basic math operations
            allowed_names = {
                "abs": abs,
                "max": max,
                "min": min,
                "round": round,
                "sum": sum,
            }
            result = eval(expression, {"__builtins__": {}}, allowed_names)  # noqa: S307
            return str(result)
        except Exception as exc:
            return f"Error: {exc}"

    return ToolDefinition(
        name="calculator",
        description="Evaluate a mathematical expression.",
        parameters={
            "expression": {
                "type": "string",
                "description": "Mathematical expression to evaluate",
            }
        },
        handler=_calc,
        is_async=False,
    )


# =============================================================================
#  Quick self-test (run as ``python -m jarvis.runtime.agency.agents_bridge``)
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    )

    async def _self_test() -> None:
        bridge = get_agents_bridge(default_model="gpt-4o-mini")
        print(bridge)
        assert bridge.is_mock == (not _AGENTS_SDK_AVAILABLE)

        # ---- Create agents ------------------------------------------------
        greeter = await bridge.create_agent(
            name="Greeter",
            instructions="You are a friendly greeter. Keep responses under 20 words.",
        )
        print(f"Created agent: {greeter.to_dict()}")
        assert greeter.model == "gpt-4o-mini"

        expert = await bridge.create_agent(
            name="Expert",
            instructions="You are a domain expert. Provide detailed answers.",
            model="gpt-4o",
        )
        print(f"Created agent: {expert.to_dict()}")
        assert bridge.agent_count == 2

        # ---- Register tools -----------------------------------------------
        calc_tool = create_calculator_tool()
        bridge.add_tool(calc_tool)

        async def mock_search(query: str) -> str:
            await asyncio.sleep(0.01)
            return f"Search results for: {query}"

        search_tool = create_search_tool(mock_search)
        bridge.add_tool(search_tool)

        # Also test callable registration
        def greet_tool(name: str = "world") -> str:
            return f"Hello, {name}!"

        bridge.add_tool(greet_tool)
        assert bridge.tool_count >= 3
        print(f"Tools registered: {[t.name for t in bridge.list_tools()]}")

        # ---- Run agent ----------------------------------------------------
        trace = await bridge.run_agent(greeter, "Say hello to the JARVIS team")
        print(f"Run trace: {trace.to_dict()}")
        assert trace.status.name == "COMPLETED"
        assert trace.final_output is not None

        # ---- Trace introspection ------------------------------------------
        retrieved = bridge.get_trace(trace.trace_id)
        assert retrieved is not None
        assert retrieved.agent_id == greeter.agent_id

        all_traces = bridge.list_traces()
        assert len(all_traces) >= 1

        # ---- Handoff ------------------------------------------------------
        handoff_trace = await bridge.handoff(
            greeter,
            expert,
            "User asked a deep technical question about neural networks.",
        )
        print(f"Handoff trace: {handoff_trace.to_dict()}")
        assert handoff_trace.status.name == "COMPLETED"
        assert len(handoff_trace.handoff_path) == 2

        # ---- Parallel batch run -------------------------------------------
        batch_inputs = ["Question 1", "Question 2", "Question 3"]
        batch_traces = await bridge.run_parallel(expert, batch_inputs, max_concurrency=2)
        assert len(batch_traces) == 3
        print(f"Batch completed: {len(batch_traces)} traces")

        # ---- Sequential run -----------------------------------------------
        seq_inputs = ["Step 1", "Step 2"]
        seq_traces = await bridge.run_sequential(greeter, seq_inputs)
        assert len(seq_traces) == 2
        print(f"Sequential completed: {len(seq_traces)} traces")

        # ---- Metrics ------------------------------------------------------
        print(f"Metrics: {bridge.metrics}")
        assert bridge.metrics.agents_created == 2
        assert bridge.metrics.runs_completed >= 6
        assert bridge.metrics.handoffs_performed >= 1

        print("Self-test passed ✅")

    asyncio.run(_self_test())
