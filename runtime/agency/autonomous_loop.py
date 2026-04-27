"""Autonomous loop runner.

Executes a registered task callable repeatedly, with bounded
iterations, cancellation, and threading-safe stop signal. Used by
long-running self-driven workflows (e.g. an evolver that wants to
keep optimizing tools until told to stop).

The loop is *not* a thread pool. Exactly one task runs at a time.
Async wrapping is provided via `run_async` for callers who want to
fire-and-forget without blocking their main thread.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class LoopStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    INTERRUPTED = "interrupted"
    MAX_ITER = "max_iter"
    ERROR = "error"


@dataclass
class LoopResult:
    status: LoopStatus
    iterations: int
    last_output: Any = None
    error: str | None = None
    elapsed_seconds: float = 0.0


# Executor signature: (task_payload, iteration_index) -> (output, done)
#   - output: anything the caller wants to keep
#   - done:   True ⇒ loop terminates with status DONE
ExecutorFn = Callable[[Any, int], tuple[Any, bool]]


class AutonomousLoop:
    """Single-task runner with cooperative cancel + bounded iterations."""

    def __init__(self) -> None:
        self._executors: dict[str, ExecutorFn] = {}
        self._stop_event = threading.Event()
        self._status: LoopStatus = LoopStatus.PENDING
        self._thread: threading.Thread | None = None
        self._last_result: LoopResult | None = None

    # ----- registration -----

    def register_executor(self, name: str, fn: ExecutorFn) -> None:
        if not callable(fn):
            raise TypeError("executor must be callable")
        self._executors[name] = fn

    def unregister_executor(self, name: str) -> bool:
        return self._executors.pop(name, None) is not None

    def executors(self) -> list[str]:
        return sorted(self._executors.keys())

    # ----- run -----

    def run(
        self,
        task: dict[str, Any],
        *,
        max_iterations: int = 10,
        sleep_between: float = 0.0,
    ) -> LoopResult:
        """Run the task synchronously. `task` must contain a "executor"
        key naming a registered executor and may contain "payload"."""
        if max_iterations <= 0:
            raise ValueError("max_iterations must be positive")
        executor_name = task.get("executor")
        if not executor_name:
            raise ValueError("task must include an 'executor' name")
        fn = self._executors.get(executor_name)
        if fn is None:
            raise KeyError(f"no executor registered for {executor_name!r}")

        payload = task.get("payload")
        # Note: we do NOT clear the stop event here — pre-setting stop()
        # before run() should produce an immediate INTERRUPTED. Callers
        # who want to reuse a loop instance call reset() between runs.
        self._status = LoopStatus.RUNNING
        started = time.monotonic()
        last_output: Any = None
        i = 0
        try:
            for i in range(1, max_iterations + 1):
                if self._stop_event.is_set():
                    self._status = LoopStatus.INTERRUPTED
                    break
                last_output, done = fn(payload, i)
                if done:
                    self._status = LoopStatus.DONE
                    break
                if sleep_between > 0:
                    # Wait but stay responsive to stop().
                    if self._stop_event.wait(sleep_between):
                        self._status = LoopStatus.INTERRUPTED
                        break
            else:
                # Loop fell through without break.
                self._status = LoopStatus.MAX_ITER
            result = LoopResult(
                status=self._status,
                iterations=i,
                last_output=last_output,
                elapsed_seconds=round(time.monotonic() - started, 4),
            )
        except Exception as e:  # noqa: BLE001 — surface any executor failure
            self._status = LoopStatus.ERROR
            result = LoopResult(
                status=LoopStatus.ERROR,
                iterations=i,
                last_output=last_output,
                error=f"{type(e).__name__}: {e}",
                elapsed_seconds=round(time.monotonic() - started, 4),
            )
        self._last_result = result
        return result

    def run_async(
        self,
        task: dict[str, Any],
        *,
        max_iterations: int = 10,
        sleep_between: float = 0.0,
    ) -> threading.Thread:
        """Fire-and-forget. Returns the worker thread; caller can
        `join()` if they want to wait. Only one async run at a time."""
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("an autonomous loop is already running")

        def _runner() -> None:
            self.run(task, max_iterations=max_iterations, sleep_between=sleep_between)

        t = threading.Thread(target=_runner, daemon=True)
        self._thread = t
        t.start()
        return t

    def stop(self) -> None:
        """Signal the running loop to exit at the next checkpoint."""
        self._stop_event.set()

    def reset(self) -> None:
        """Clear the stop signal so the loop can be reused."""
        self._stop_event.clear()
        self._status = LoopStatus.PENDING

    # ----- introspection -----

    @property
    def status(self) -> LoopStatus:
        return self._status

    def last_result(self) -> LoopResult | None:
        return self._last_result

    def is_running(self) -> bool:
        return self._status is LoopStatus.RUNNING and (
            self._thread is None or self._thread.is_alive()
        )
