"""
E2B Open Computer Use Bridge — JARVIS Runtime Integration Adapter
=================================================================
Wraps the e2b-dev/open-computer-use agent (SandboxAgent + E2B Desktop Sandbox)
as an async-capable, headless task executor for the JARVIS agency runtime.

Repo      : https://github.com/e2b-dev/open-computer-use
License   : Apache-2.0
Python    : >=3.10
Depends   : e2b, e2b-desktop, openai, anthropic, gradio-client, pillow, python-dotenv

Usage (async):
    bridge = E2BComputerUseBridge()
    task = await bridge.start_session("Check the weather in SF via Chrome")
    async for event in bridge.stream_events(task.task_id):
        ...
    result = await bridge.stop_session(task.task_id)

Author    : JARVIS Runtime Auto-Generated Adapter
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Ensure the original repo's package is importable.  In production, install
#   pip install git+https://github.com/e2b-dev/open-computer-use.git
# or vendor the os_computer_use/ folder into the JARVIS Python path.
# ---------------------------------------------------------------------------
import sys

logger = logging.getLogger("jarvis.e2b_computer_use_bridge")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class BridgeConfig:
    """Centralised configuration loaded from environment + sensible defaults."""

    E2B_API_KEY: str = os.getenv("E2B_API_KEY", "")
    # LLM provider keys (only the ones selected in config.py are required)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    FIREWORKS_API_KEY: str = os.getenv("FIREWORKS_API_KEY", "")
    MISTRAL_API_KEY: str = os.getenv("MISTRAL_API_KEY", "")
    MOONSHOT_API_KEY: str = os.getenv("MOONSHOT_API_KEY", "")
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    LLAMA_API_KEY: str = os.getenv("LLAMA_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    HF_TOKEN: str = os.getenv("HF_TOKEN", "")

    # Runtime tuning
    SANDBOX_TIMEOUT_SEC: int = int(os.getenv("E2B_SANDBOX_TIMEOUT", "300"))
    OUTPUT_ROOT: Path = Path(os.getenv("E2B_OUTPUT_ROOT", "./output/e2b_bridge"))
    MAX_CONCURRENT_SESSIONS: int = int(os.getenv("E2B_MAX_SESSIONS", "5"))
    SCREENSHOT_INTERVAL_MS: int = int(os.getenv("E2B_SCREENSHOT_INTERVAL_MS", "500"))

    @classmethod
    def validate(cls) -> List[str]:
        """Return list of missing critical env vars."""
        missing = []
        if not cls.E2B_API_KEY:
            missing.append("E2B_API_KEY")
        return missing


# ---------------------------------------------------------------------------
# Domain models / event schema
# ---------------------------------------------------------------------------


class EventType(str, Enum):
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"
    SCREENSHOT = "screenshot"
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    ERROR = "error"
    STATUS = "status"
    HEARTBEAT = "heartbeat"


@dataclass
class BridgeEvent:
    """Standardised event emitted by the bridge for consumption by JARVIS."""

    timestamp: str
    type: EventType
    task_id: str
    session_id: str
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def now(cls, event_type: EventType, task_id: str, session_id: str, **kwargs) -> "BridgeEvent":
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            type=event_type,
            task_id=task_id,
            session_id=session_id,
            data=kwargs,
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)


@dataclass
class SessionResult:
    """Final aggregated result of a sandbox session."""

    task_id: str
    session_id: str
    status: str  # "completed" | "error" | "cancelled"
    instruction: str
    start_time: str
    end_time: str
    duration_sec: float
    actions_taken: int
    screenshots: List[str] = field(default_factory=list)
    log_html_path: Optional[str] = None
    final_observation: Optional[str] = None
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal: event queue + agent hook injection
# ---------------------------------------------------------------------------


class _EventBus:
    """Simple async pub/sub for BridgeEvents inside a single session."""

    def __init__(self) -> None:
        self._queues: List[asyncio.Queue[BridgeEvent]] = []

    def subscribe(self) -> asyncio.Queue[BridgeEvent]:
        q: asyncio.Queue[BridgeEvent] = asyncio.Queue()
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[BridgeEvent]) -> None:
        if q in self._queues:
            self._queues.remove(q)

    def publish(self, event: BridgeEvent) -> None:
        for q in self._queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass


# ---------------------------------------------------------------------------
# Bridge implementation
# ---------------------------------------------------------------------------


class E2BComputerUseBridge:
    """
    Async integration bridge for e2b-dev/open-computer-use.

    Each JARVIS task maps to one sandbox session (1:1).  The bridge manages
    sandbox lifecycle, translates tool interactions into BridgeEvents, and
    exposes a streaming API for real-time observation.
    """

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        missing = BridgeConfig.validate()
        if missing:
            raise RuntimeError(f"Missing required env vars: {missing}")

        self._output_dir = output_dir or BridgeConfig.OUTPUT_ROOT
        self._output_dir.mkdir(parents=True, exist_ok=True)

        # In-memory session bookkeeping
        self._sessions: Dict[str, _SessionContext] = {}
        self._sem = asyncio.Semaphore(BridgeConfig.MAX_CONCURRENT_SESSIONS)

        # Ensure E2B API key is present in the environment for the underlying lib
        os.environ.setdefault("E2B_API_KEY", BridgeConfig.E2B_API_KEY)

    # -- Public API ---------------------------------------------------------

    async def start_session(self, instruction: str, task_id: Optional[str] = None) -> BridgeEvent:
        """
        Launch a new sandbox session and begin executing *instruction*.

        Returns a SESSION_STARTED event immediately; subsequent events are
        streamed via :meth:`stream_events`.
        """
        async with self._sem:
            session_id = str(uuid.uuid4())[:8]
            task_id = task_id or str(uuid.uuid4())[:8]
            run_dir = self._output_dir / f"run_{task_id}_{session_id}"
            run_dir.mkdir(parents=True, exist_ok=True)

            ctx = _SessionContext(
                task_id=task_id,
                session_id=session_id,
                instruction=instruction,
                run_dir=run_dir,
                event_bus=_EventBus(),
            )
            self._sessions[session_id] = ctx

            # Kick off the blocking agent loop in a thread / process pool
            ctx._task = asyncio.create_task(self._agent_loop(ctx))

            event = BridgeEvent.now(
                EventType.SESSION_STARTED, task_id, session_id,
                instruction=instruction, output_dir=str(run_dir),
            )
            ctx.event_bus.publish(event)
            logger.info("Session %s started for task %s", session_id, task_id)
            return event

    async def stream_events(self, session_id: str) -> AsyncIterator[BridgeEvent]:
        """Async generator yielding all BridgeEvents for a session."""
        ctx = self._sessions.get(session_id)
        if not ctx:
            yield BridgeEvent.now(
                EventType.ERROR, "unknown", session_id,
                message=f"Session {session_id} not found",
            )
            return

        q = ctx.event_bus.subscribe()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=1.0)
                    yield event
                    if event.type in (EventType.SESSION_ENDED, EventType.ERROR):
                        break
                except asyncio.TimeoutError:
                    # Emit heartbeat so consumers know the connection is alive
                    yield BridgeEvent.now(
                        EventType.HEARTBEAT, ctx.task_id, session_id,
                        elapsed_sec=time.time() - ctx._start_ts,
                    )
                    if ctx._task and ctx._task.done():
                        break
        finally:
            ctx.event_bus.unsubscribe(q)

    async def stop_session(self, session_id: str) -> SessionResult:
        """
        Signal cancellation to the agent loop, wait for cleanup, and return
        the aggregated session result.
        """
        ctx = self._sessions.get(session_id)
        if not ctx:
            raise KeyError(f"Session {session_id} not found")

        ctx._cancelled = True
        if ctx._task and not ctx._task.done():
            ctx._task.cancel()
            try:
                await ctx._task
            except asyncio.CancelledError:
                pass

        result = self._build_result(ctx, status="cancelled")
        logger.info("Session %s stopped (cancelled)", session_id)
        return result

    async def get_session(self, session_id: str) -> Dict[str, Any]:
        """Snapshot of current session state (lightweight, non-blocking)."""
        ctx = self._sessions.get(session_id)
        if not ctx:
            return {"error": "Session not found"}
        return {
            "task_id": ctx.task_id,
            "session_id": ctx.session_id,
            "instruction": ctx.instruction,
            "status": "running" if ctx._task and not ctx._task.done() else "finished",
            "actions_taken": ctx.actions_taken,
            "screenshots": ctx.screenshots,
            "output_dir": str(ctx.run_dir),
            "elapsed_sec": time.time() - ctx._start_ts,
        }

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all tracked sessions with lightweight metadata."""
        return [
            {
                "task_id": s.task_id,
                "session_id": s.session_id,
                "instruction": s.instruction[:80],
                "status": "running" if s._task and not s._task.done() else "finished",
                "actions_taken": s.actions_taken,
            }
            for s in self._sessions.values()
        ]

    # -- Internal agent loop ------------------------------------------------

    async def _agent_loop(self, ctx: "_SessionContext") -> None:
        """
        Runs the original SandboxAgent in an executor so the async event loop
        stays unblocked.  All agent side-effects are captured and published as
        BridgeEvents.
        """
        ctx._start_ts = time.time()
        loop = asyncio.get_running_loop()

        try:
            # Lazy-import here so the bridge module can be imported even when
            # the open-computer-use dependencies are not yet installed.
            from os_computer_use.streaming import Sandbox
            from os_computer_use.sandbox_agent import SandboxAgent
            from os_computer_use.logging import Logger

            # We override the global logger so we can intercept agent output
            agent_logger = Logger()
            agent_logger.log_file = str(ctx.run_dir / "log.html")

            def _init() -> Tuple[Sandbox, SandboxAgent]:
                sandbox = Sandbox()
                agent = SandboxAgent(sandbox, output_dir=str(ctx.run_dir), save_logs=True)
                return sandbox, agent

            sandbox, agent = await loop.run_in_executor(None, _init)
            ctx._sandbox = sandbox
            ctx._agent = agent

            # Monkey-patch the agent's methods so we can emit events
            self._instrument_agent(agent, ctx)

            # Run the blocking agent.run() in a thread
            def _run() -> None:
                try:
                    agent.run(ctx.instruction)
                except KeyboardInterrupt:
                    pass  # Expected on cancellation

            await loop.run_in_executor(None, _run)

            status = "completed" if not ctx._cancelled else "cancelled"
        except Exception as exc:
            logger.exception("Agent loop failed for session %s", ctx.session_id)
            ctx.event_bus.publish(
                BridgeEvent.now(
                    EventType.ERROR, ctx.task_id, ctx.session_id,
                    message=str(exc), exc_type=type(exc).__name__,
                )
            )
            status = "error"
            ctx._error_message = str(exc)
        finally:
            # Sandbox cleanup
            if hasattr(ctx, "_sandbox") and ctx._sandbox:
                try:
                    await loop.run_in_executor(None, ctx._sandbox.kill)
                except Exception:
                    logger.debug("Sandbox kill raised (ignored)")

            ctx._end_ts = time.time()
            result = self._build_result(ctx, status=status)
            ctx.event_bus.publish(
                BridgeEvent.now(
                    EventType.SESSION_ENDED, ctx.task_id, ctx.session_id,
                    result=asdict(result),
                )
            )
            logger.info("Session %s ended (%s)", ctx.session_id, status)

    # -- Instrumentation ----------------------------------------------------

    def _instrument_agent(self, agent: Any, ctx: "_SessionContext") -> None:
        """
        Wrap SandboxAgent methods so every screenshot, action, and observation
        becomes a BridgeEvent on the event bus.
        """
        orig_screenshot = agent.screenshot
        orig_call_function = agent.call_function

        def _screenshot() -> bytes:
            data = orig_screenshot()
            filepath = agent.latest_screenshot
            if filepath:
                ctx.screenshots.append(filepath)
                ctx.event_bus.publish(
                    BridgeEvent.now(
                        EventType.SCREENSHOT, ctx.task_id, ctx.session_id,
                        screenshot_path=filepath,
                    )
                )
            return data

        agent.screenshot = _screenshot

        def _call_function(name: str, arguments: Dict[str, Any]) -> str:
            ctx.actions_taken += 1
            ctx.event_bus.publish(
                BridgeEvent.now(
                    EventType.ACTION, ctx.task_id, ctx.session_id,
                    action=name, parameters=arguments,
                )
            )
            result = orig_call_function(name, arguments)
            ctx.event_bus.publish(
                BridgeEvent.now(
                    EventType.OBSERVATION, ctx.task_id, ctx.session_id,
                    action=name, result=result,
                )
            )
            return result

        agent.call_function = _call_function

        # We also patch the logger so THOUGHT lines become events
        import os_computer_use.logging as _log_mod
        orig_log = _log_mod.logger.log

        def _patched_log(text: str, color: str = "black", print_: bool = True) -> str:
            ret = orig_log(text, color, print_)
            if text.startswith("THOUGHT:"):
                ctx.event_bus.publish(
                    BridgeEvent.now(
                        EventType.THOUGHT, ctx.task_id, ctx.session_id,
                        thought=text.replace("THOUGHT: ", ""),
                    )
                )
            return ret

        _log_mod.logger.log = _patched_log

    # -- Helpers ------------------------------------------------------------

    def _build_result(self, ctx: "_SessionContext", status: str) -> SessionResult:
        return SessionResult(
            task_id=ctx.task_id,
            session_id=ctx.session_id,
            status=status,
            instruction=ctx.instruction,
            start_time=datetime.fromtimestamp(ctx._start_ts, tz=timezone.utc).isoformat(),
            end_time=datetime.fromtimestamp(ctx._end_ts, tz=timezone.utc).isoformat(),
            duration_sec=round(ctx._end_ts - ctx._start_ts, 2),
            actions_taken=ctx.actions_taken,
            screenshots=ctx.screenshots,
            log_html_path=str(ctx.run_dir / "log.html") if (ctx.run_dir / "log.html").exists() else None,
            final_observation=ctx._final_observation,
            error_message=getattr(ctx, "_error_message", None),
        )


# ---------------------------------------------------------------------------
# Internal session bookkeeping
# ---------------------------------------------------------------------------


@dataclass
class _SessionContext:
    task_id: str
    session_id: str
    instruction: str
    run_dir: Path
    event_bus: _EventBus

    actions_taken: int = 0
    screenshots: List[str] = field(default_factory=list)
    _cancelled: bool = False
    _start_ts: float = 0.0
    _end_ts: float = 0.0
    _task: Optional[asyncio.Task] = None
    _sandbox: Any = None
    _agent: Any = None
    _final_observation: Optional[str] = None
    _error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Optional: FastAPI router factory (for JARVIS runtime HTTP exposure)
# ---------------------------------------------------------------------------

try:
    from fastapi import APIRouter, HTTPException
    from fastapi.responses import StreamingResponse

    def create_bridge_router(bridge: E2BComputerUseBridge) -> APIRouter:
        """
        Factory that returns a FastAPI router exposing the bridge over HTTP.
        Mount with: app.include_router(create_bridge_router(bridge), prefix="/e2b")
        """
        router = APIRouter(tags=["e2b-computer-use"])

        @router.post("/sessions")
        async def create_session(payload: Dict[str, str]):
            instruction = payload.get("instruction", "")
            if not instruction:
                raise HTTPException(status_code=400, detail="'instruction' required")
            event = await bridge.start_session(instruction, task_id=payload.get("task_id"))
            return {"event": asdict(event)}

        @router.get("/sessions")
        async def list_sessions():
            return {"sessions": bridge.list_sessions()}

        @router.get("/sessions/{session_id}")
        async def get_session(session_id: str):
            return await bridge.get_session(session_id)

        @router.delete("/sessions/{session_id}")
        async def delete_session(session_id: str):
            result = await bridge.stop_session(session_id)
            return asdict(result)

        @router.get("/sessions/{session_id}/events")
        async def events(session_id: str):
            async def _gen():
                async for ev in bridge.stream_events(session_id):
                    yield f"data: {ev.to_json()}\n\n"
            return StreamingResponse(_gen(), media_type="text/event-stream")

        return router

except ImportError:
    create_bridge_router = None  # type: ignore[assignment]
    logger.debug("fastapi not installed; router factory unavailable")


# ---------------------------------------------------------------------------
# CLI smoke-test (optional)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    async def _smoke() -> None:
        bridge = E2BComputerUseBridge()
        instruction = os.getenv("E2B_SMOKE_INSTRUCTION", "Open the calculator and compute 2+2")
        started = await bridge.start_session(instruction)
        print("Started:", started.to_json())

        async for ev in bridge.stream_events(started.session_id):
            print(ev.to_json())
            if ev.type == EventType.SESSION_ENDED:
                break

    asyncio.run(_smoke())
