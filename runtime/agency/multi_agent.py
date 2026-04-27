"""Multi-agent orchestration — Pipeline (sequential), Graph (DAG), Pool (round-robin).

Inspired by LangGraph. Steps are plain callables; the orchestrator
threads outputs between them. The Graph runs independent nodes in
parallel via ThreadPoolExecutor and topologically orders dependent ones.
"""

from __future__ import annotations

import itertools
import threading
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any, Callable

from .logging import get_logger

log = get_logger()


@dataclass
class AgentNode:
    """One step in a graph or pipeline."""

    name: str
    fn: Callable
    dependencies: list[str] = field(default_factory=list)


class Pipeline:
    """Sequential execution. Each step receives the previous output."""

    def __init__(self) -> None:
        self.steps: list[AgentNode] = []

    def add_step(self, name: str, fn: Callable) -> "Pipeline":
        self.steps.append(AgentNode(name=name, fn=fn))
        return self

    def run(self, input: Any) -> dict[str, Any]:
        results: dict[str, Any] = {"input": input}
        cur = input
        for step in self.steps:
            try:
                out = step.fn(cur)
            except Exception as e:
                log.error("pipeline step %s failed: %s", step.name, e)
                results[step.name] = {"error": repr(e)}
                results["_failed_at"] = step.name
                return results
            results[step.name] = out
            cur = out
        results["output"] = cur
        return results


class Graph:
    """DAG executor. Nodes with met dependencies run in parallel."""

    def __init__(self, max_workers: int = 4) -> None:
        self.nodes: dict[str, AgentNode] = {}
        self.max_workers = max_workers

    def add_node(
        self,
        name: str,
        fn: Callable,
        dependencies: list[str] | None = None,
    ) -> "Graph":
        self.nodes[name] = AgentNode(name=name, fn=fn, dependencies=list(dependencies or []))
        return self

    def _validate(self) -> list[str]:
        # Kahn's algorithm — also detects cycles
        indeg = {n: 0 for n in self.nodes}
        for node in self.nodes.values():
            for dep in node.dependencies:
                if dep not in self.nodes:
                    raise KeyError(f"node {node.name!r} depends on unknown {dep!r}")
                indeg[node.name] += 1
        ready = [n for n, d in indeg.items() if d == 0]
        order: list[str] = []
        while ready:
            n = ready.pop(0)
            order.append(n)
            for m_name, m in self.nodes.items():
                if n in m.dependencies:
                    indeg[m_name] -= 1
                    if indeg[m_name] == 0:
                        ready.append(m_name)
        if len(order) != len(self.nodes):
            raise ValueError("cycle detected in graph")
        return order

    def run(self, input: Any) -> dict[str, Any]:
        self._validate()
        results: dict[str, Any] = {"input": input}
        failed: set[str] = set()
        completed: set[str] = set()
        lock = threading.Lock()

        def runnable() -> list[str]:
            out = []
            for name, node in self.nodes.items():
                if name in completed or name in failed:
                    continue
                if any(d in failed for d in node.dependencies):
                    failed.add(name)
                    results[name] = {"skipped": "upstream_failed"}
                    continue
                if all(d in completed for d in node.dependencies):
                    out.append(name)
            return out

        def run_node(name: str) -> tuple[str, Any, Exception | None]:
            node = self.nodes[name]
            inputs = {d: results[d] for d in node.dependencies}
            payload = inputs if inputs else input
            try:
                out = node.fn(payload)
                return name, out, None
            except Exception as e:
                return name, None, e

        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            while True:
                ready = runnable()
                if not ready:
                    if len(completed) + len(failed) >= len(self.nodes):
                        break
                    # Stalled — should not happen after _validate, but bail
                    break
                futures = [ex.submit(run_node, n) for n in ready]
                for fut in futures:
                    name, out, err = fut.result()
                    with lock:
                        if err is not None:
                            log.error("graph node %s failed: %s", name, err)
                            results[name] = {"error": repr(err)}
                            failed.add(name)
                        else:
                            results[name] = out
                            completed.add(name)
        results["_completed"] = sorted(completed)
        results["_failed"] = sorted(failed)
        return results


class AgentPool:
    """Round-robin pool of named worker callables."""

    def __init__(self, max_workers: int = 4) -> None:
        self.agents: list[AgentNode] = []
        self._cycle = None
        self._lock = threading.Lock()
        self.max_workers = max_workers

    def add_agent(self, name: str, fn: Callable) -> "AgentPool":
        self.agents.append(AgentNode(name=name, fn=fn))
        self._cycle = itertools.cycle(self.agents) if self.agents else None
        return self

    def _next(self) -> AgentNode:
        with self._lock:
            if not self.agents or self._cycle is None:
                raise RuntimeError("no agents registered")
            return next(self._cycle)

    def dispatch(self, task: Any) -> Any:
        agent = self._next()
        return agent.fn(task)

    def dispatch_all(self, tasks: list[Any]) -> list[Any]:
        if not self.agents:
            raise RuntimeError("no agents registered")
        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(tasks)))) as ex:
            futures: list[Future] = []
            for t in tasks:
                agent = self._next()
                futures.append(ex.submit(agent.fn, t))
            wait(futures)
            out: list[Any] = []
            for f in futures:
                try:
                    out.append(f.result())
                except Exception as e:
                    out.append({"error": repr(e)})
            return out

    def __len__(self) -> int:
        return len(self.agents)


__all__ = ["AgentNode", "Pipeline", "Graph", "AgentPool"]
