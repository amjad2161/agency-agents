"""Autonomous iterative loop engine — executes goal-directed cycles until done.

Implements a ReAct-style Thought→Action→Observe loop with:
- Max-iteration guard
- Threading interrupt support (stop_event)
- Pluggable action executors
- Persistent run history via ~/.jarvis/loop_runs.jsonl
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .logging import get_logger

DEFAULT_RUNS_PATH = Path.home() / ".jarvis" / "loop_runs.jsonl"
DEFAULT_MAX_ITERATIONS = 10
LOOP_SLEEP_S = 0.05

log = get_logger()


class LoopStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    INTERRUPTED = "interrupted"
    MAX_ITER = "max_iter"
    ERROR = "error"


@dataclass
class LoopIteration:
    """One cycle of Thought → Action → Observe."""

    iteration: int
    thought: str
    action: str
    observation: str
    done: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LoopRun:
    """Complete record of an autonomous loop execution."""

    run_id: str
    goal: str
    status: str = LoopStatus.PENDING
    iterations: list[LoopIteration] = field(default_factory=list)
    result: str = ""
    error: str = ""
    started_at: float = field(default_factory=time.time)
    ended_at: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["iterations"] = [i.to_dict() for i in self.iterations]
        return d


# Type alias for action executor: receives (action_str, context) → observation_str
ActionExecutor = Callable[[str, dict[str, Any]], str]


class AutonomousLoop:
    """Goal-directed autonomous loop with interrupt support.

    Usage::

        loop = AutonomousLoop(max_iterations=8)

        def my_executor(action: str, ctx: dict) -> str:
            return f"executed: {action}"

        loop.register_executor("default", my_executor)
        run = loop.run("Summarise recent news about LLMs")
        print(run.result)

    Interrupt from another thread::

        stop = threading.Event()
        loop = AutonomousLoop(stop_event=stop)
        threading.Timer(5.0, stop.set).start()
        run = loop.run("long running goal")
    """

    def __init__(
        self,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        stop_event: threading.Event | None = None,
        runs_path: Path | None = None,
    ) -> None:
        self._max_iterations = max_iterations
        self._stop_event = stop_event or threading.Event()
        self._runs_path = runs_path or DEFAULT_RUNS_PATH
        self._runs_path.parent.mkdir(parents=True, exist_ok=True)
        self._executors: dict[str, ActionExecutor] = {}
        self._lock = threading.Lock()
        self._active_runs = 0

    # ── public API ────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """True while at least one ``run()`` call is in flight."""
        return self._active_runs > 0

    @property
    def max_iterations(self) -> int:
        return self._max_iterations

    @property
    def runs_path(self) -> Path:
        return self._runs_path

    def registered_executors(self) -> list[str]:
        """Names of every registered action executor."""
        return list(self._executors.keys())

    def register_executor(self, name: str, fn: ActionExecutor) -> None:
        """Register an action executor callable under *name*."""
        self._executors[name] = fn

    def run(
        self,
        goal: str,
        context: dict[str, Any] | None = None,
        executor_name: str = "default",
    ) -> LoopRun:
        """Execute an autonomous loop for *goal*.

        Returns a LoopRun with full iteration history and final result.
        """
        ctx = dict(context or {})
        run = LoopRun(run_id=str(uuid.uuid4())[:8], goal=goal, status=LoopStatus.RUNNING)
        run.started_at = time.time()

        executor = self._executors.get(executor_name) or self._executors.get("default")

        with self._lock:
            self._active_runs += 1
        try:
            for i in range(self._max_iterations):
                if self._stop_event.is_set():
                    run.status = LoopStatus.INTERRUPTED
                    log.info("autonomous_loop: interrupted at iteration %d", i)
                    break

                thought = self._think(goal, run.iterations, ctx)
                action = self._decide_action(thought, goal, ctx)
                observation = self._execute(action, ctx, executor)

                done = self._is_done(observation, goal, i)
                iteration = LoopIteration(
                    iteration=i + 1,
                    thought=thought,
                    action=action,
                    observation=observation,
                    done=done,
                )
                run.iterations.append(iteration)
                ctx["last_observation"] = observation

                log.debug(
                    "autonomous_loop: iter %d done=%s observation_len=%d",
                    i + 1, done, len(observation),
                )

                if done:
                    run.status = LoopStatus.DONE
                    run.result = self._summarise(goal, run.iterations)
                    break

                time.sleep(LOOP_SLEEP_S)
            else:
                run.status = LoopStatus.MAX_ITER
                run.result = self._summarise(goal, run.iterations)

        except Exception as exc:
            run.status = LoopStatus.ERROR
            run.error = str(exc)
            log.error("autonomous_loop: error — %s", exc)
        finally:
            with self._lock:
                self._active_runs = max(0, self._active_runs - 1)

        run.ended_at = time.time()
        self._persist(run)
        return run

    def run_async(
        self,
        goal: str,
        context: dict[str, Any] | None = None,
        executor_name: str = "default",
        callback: Callable[[LoopRun], None] | None = None,
    ) -> threading.Thread:
        """Start loop in background thread. Returns the thread."""

        def _worker() -> None:
            result = self.run(goal, context, executor_name)
            if callback:
                callback(result)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        """Signal the running loop to stop after the current iteration."""
        self._stop_event.set()

    def reset_stop(self) -> None:
        """Clear the stop signal (allows re-use of the same instance)."""
        self._stop_event.clear()

    def get_run_history(self, n: int = 20) -> list[LoopRun]:
        """Return last *n* persisted runs."""
        runs: list[LoopRun] = []
        if not self._runs_path.exists():
            return runs
        with self._lock:
            lines = self._runs_path.read_text().splitlines()
        for line in lines[-n:]:
            try:
                d = json.loads(line)
                r = LoopRun(
                    run_id=d["run_id"],
                    goal=d["goal"],
                    status=d["status"],
                    result=d.get("result", ""),
                    error=d.get("error", ""),
                    started_at=d.get("started_at", 0.0),
                    ended_at=d.get("ended_at", 0.0),
                )
                runs.append(r)
            except Exception:
                pass
        return runs

    # ── internals ─────────────────────────────────────────────────────────────

    def _think(
        self,
        goal: str,
        history: list[LoopIteration],
        ctx: dict[str, Any],
    ) -> str:
        if not history:
            return f"Starting fresh: my goal is '{goal[:80]}'. I'll begin by understanding scope."
        last = history[-1]
        if last.done:
            return "Goal achieved. Preparing final summary."
        return (
            f"After {len(history)} iterations, last observation was: "
            f"'{last.observation[:60]}'. Continuing toward: '{goal[:60]}'."
        )

    def _decide_action(self, thought: str, goal: str, ctx: dict[str, Any]) -> str:
        goal_lower = goal.lower()
        if "search" in goal_lower or "find" in goal_lower:
            return f"search: {goal[:80]}"
        if "summarise" in goal_lower or "summarize" in goal_lower:
            return f"summarise: {ctx.get('last_observation', goal)[:80]}"
        if "write" in goal_lower or "generate" in goal_lower:
            return f"generate: {goal[:80]}"
        if "analyse" in goal_lower or "analyze" in goal_lower:
            return f"analyse: {ctx.get('last_observation', goal)[:80]}"
        return f"execute: {goal[:80]}"

    def _execute(
        self,
        action: str,
        ctx: dict[str, Any],
        executor: ActionExecutor | None,
    ) -> str:
        if executor:
            try:
                return executor(action, ctx)
            except Exception as exc:
                return f"[executor error] {exc}"
        # Stub
        verb = action.split(":")[0].strip()
        return f"[stub] {verb} completed for: {action[len(verb)+1:].strip()[:60]}"

    def _is_done(self, observation: str, goal: str, iteration: int) -> bool:
        obs_lower = observation.lower()
        if any(w in obs_lower for w in ("complete", "done", "finished", "success")):
            return True
        if iteration >= self._max_iterations - 1:
            return True
        return False

    def _summarise(self, goal: str, iterations: list[LoopIteration]) -> str:
        if not iterations:
            return f"No iterations completed for goal: {goal}"
        last_obs = iterations[-1].observation
        return (
            f"Goal '{goal[:60]}' completed in {len(iterations)} iteration(s). "
            f"Final observation: {last_obs[:120]}"
        )

    def _persist(self, run: LoopRun) -> None:
        with self._lock:
            with self._runs_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(run.to_dict()) + "\n")
