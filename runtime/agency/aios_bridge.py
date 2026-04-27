"""AIOSBridge — minimal AI Operating System interface.

Lets external agents register named handlers and submit tasks to a
shared priority queue. A background worker pool consumes the queue
and stores results keyed by task id. Thread-safe.
"""

from __future__ import annotations

import heapq
import itertools
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from .logging import get_logger

log = get_logger()


@dataclass
class _Agent:
    name: str
    description: str
    fn: Callable


@dataclass
class _Task:
    task_id: str
    body: str
    priority: int
    submitted_at: float
    agent_name: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class AIOSBridge:
    """Queue-backed task dispatcher with named agent handlers."""

    def __init__(self, workers: int = 2) -> None:
        self.agents: dict[str, _Agent] = {}
        self._heap: list[tuple[int, int, _Task]] = []
        self._counter = itertools.count()
        self._results: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._workers: list[threading.Thread] = []
        self._stop = threading.Event()
        self._start_workers(workers)

    def _start_workers(self, n: int) -> None:
        for i in range(n):
            t = threading.Thread(target=self._worker_loop, name=f"aios-w{i}", daemon=True)
            t.start()
            self._workers.append(t)

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            task: _Task | None = None
            with self._cond:
                while not self._heap and not self._stop.is_set():
                    self._cond.wait(timeout=0.5)
                if self._stop.is_set():
                    return
                _, _, task = heapq.heappop(self._heap)
            if task is None:
                continue
            self._results[task.task_id] = {
                "status": "running",
                "started_at": time.time(),
            }
            agent = self._pick_agent(task)
            if agent is None:
                self._results[task.task_id] = {
                    "status": "error",
                    "error": "no agent registered",
                    "finished_at": time.time(),
                }
                continue
            try:
                out = agent.fn(task.body)
                self._results[task.task_id] = {
                    "status": "ok",
                    "result": out,
                    "agent": agent.name,
                    "finished_at": time.time(),
                }
            except Exception as e:
                self._results[task.task_id] = {
                    "status": "error",
                    "error": repr(e),
                    "agent": agent.name,
                    "finished_at": time.time(),
                }

    def _pick_agent(self, task: _Task) -> _Agent | None:
        with self._lock:
            if task.agent_name and task.agent_name in self.agents:
                return self.agents[task.agent_name]
            return next(iter(self.agents.values()), None)

    def register_agent(self, name: str, description: str, fn: Callable) -> None:
        with self._lock:
            self.agents[name] = _Agent(name=name, description=description, fn=fn)

    def submit_task(
        self,
        task: str,
        priority: int = 5,
        agent_name: str | None = None,
        **extra,
    ) -> str:
        task_id = uuid.uuid4().hex
        t = _Task(
            task_id=task_id,
            body=task,
            priority=priority,
            submitted_at=time.time(),
            agent_name=agent_name,
            extra=extra,
        )
        with self._cond:
            heapq.heappush(self._heap, (priority, next(self._counter), t))
            self._results[task_id] = {"status": "queued", "submitted_at": t.submitted_at}
            self._cond.notify()
        return task_id

    def get_result(self, task_id: str, timeout: float | None = None) -> dict[str, Any]:
        deadline = time.time() + timeout if timeout else None
        while True:
            with self._lock:
                res = self._results.get(task_id, {"status": "unknown"})
            if res.get("status") in {"ok", "error", "unknown"}:
                return res
            if deadline is None:
                return res
            if time.time() >= deadline:
                return res
            time.sleep(0.05)

    def list_agents(self) -> list[dict[str, str]]:
        with self._lock:
            return [{"name": a.name, "description": a.description} for a in self.agents.values()]

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "agents": len(self.agents),
                "queued": len(self._heap),
                "completed": sum(1 for r in self._results.values() if r.get("status") in {"ok", "error"}),
                "workers": len(self._workers),
            }

    def shutdown(self, wait: bool = True) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        if wait:
            for t in self._workers:
                t.join(timeout=1.0)


__all__ = ["AIOSBridge"]
