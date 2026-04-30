"""Pass-24 task executor — priority queue with worker threads.

A small, dependency-free producer/consumer used by the orchestrator to
fan out independent agent tasks. Designed so tests can drive it
synchronously by using ``workers=0`` and calling :meth:`drain`.
"""

from __future__ import annotations

import heapq
import itertools
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


_TASK_COUNTER = itertools.count()


@dataclass(order=True)
class _PriItem:
    priority: int
    seq: int
    task: "Task" = field(compare=False)


@dataclass
class Task:
    id: str
    fn: Callable[..., Any]
    args: tuple = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    priority: int = 5
    status: str = "pending"
    result: Any = None
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None


class TaskExecutor:
    """Priority queue with optional background workers."""

    def __init__(self, *, workers: int = 0) -> None:
        self._heap: list[_PriItem] = []
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._stop = False
        self._tasks: dict[str, Task] = {}
        self._threads: list[threading.Thread] = []
        for _ in range(workers):
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()
            self._threads.append(t)

    # ------------------------------------------------------------------
    def submit(self, fn: Callable[..., Any], *args: Any,
               priority: int = 5, **kwargs: Any) -> Task:
        task = Task(id=uuid.uuid4().hex, fn=fn, args=args, kwargs=kwargs,
                    priority=priority)
        with self._cond:
            self._tasks[task.id] = task
            heapq.heappush(self._heap, _PriItem(priority, next(_TASK_COUNTER), task))
            self._cond.notify()
        return task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def drain(self) -> list[Task]:
        """Run every pending task on the calling thread (sync mode)."""
        done: list[Task] = []
        while True:
            with self._lock:
                if not self._heap:
                    break
                item = heapq.heappop(self._heap)
            self._run(item.task)
            done.append(item.task)
        return done

    def shutdown(self, *, wait: bool = True, timeout: float = 1.0) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify_all()
        if wait:
            for t in self._threads:
                t.join(timeout=timeout)

    def stats(self) -> dict[str, int]:
        states: dict[str, int] = {}
        for task in self._tasks.values():
            states[task.status] = states.get(task.status, 0) + 1
        return states

    # ------------------------------------------------------------------
    def _worker(self) -> None:  # pragma: no cover — exercised via threads
        while True:
            with self._cond:
                while not self._heap and not self._stop:
                    self._cond.wait(timeout=0.5)
                if self._stop and not self._heap:
                    return
                item = heapq.heappop(self._heap) if self._heap else None
            if item is not None:
                self._run(item.task)

    def _run(self, task: Task) -> None:
        task.status = "running"
        task.started_at = time.time()
        try:
            task.result = task.fn(*task.args, **task.kwargs)
            task.status = "done"
        except Exception as exc:  # noqa: BLE001 — surface to caller
            task.status = "error"
            task.error = f"{type(exc).__name__}: {exc}"
        finally:
            task.finished_at = time.time()
