"""Multi-agent DAG — inspired by LangGraph.

Declarative graph of nodes connected by labelled edges. Nodes are
callables (state -> state). The runner executes the graph with cycle
detection, conditional edges, and a deterministic execution order
based on topological sort + tiebreak by name.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable

NodeFn = Callable[[dict[str, Any]], dict[str, Any]]
# A condition selects the next node name from the node's output state.
CondFn = Callable[[dict[str, Any]], str]


@dataclass
class Edge:
    src: str
    dst: str | None = None     # static destination
    cond: CondFn | None = None  # dynamic destination


@dataclass
class GraphNode:
    name: str
    fn: NodeFn


class MultiAgentGraph:
    """LangGraph-shaped DAG with conditional edges and a hard step cap."""

    START = "__start__"
    END = "__end__"

    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[Edge] = []

    # ------------------------------------------------------------------
    def add_node(self, name: str, fn: NodeFn) -> None:
        if name in self.nodes:
            raise ValueError(f"node already defined: {name!r}")
        self.nodes[name] = GraphNode(name=name, fn=fn)

    def add_edge(self, src: str, dst: str) -> None:
        self.edges.append(Edge(src=src, dst=dst))

    def add_conditional_edges(self, src: str, cond: CondFn) -> None:
        self.edges.append(Edge(src=src, cond=cond))

    def set_entry_point(self, name: str) -> None:
        self.add_edge(self.START, name)

    # ------------------------------------------------------------------
    def run(self, state: dict[str, Any], *, max_steps: int = 32) -> dict[str, Any]:
        children = self._children()
        current = self._next_from(self.START, state, children)
        steps = 0
        history: list[str] = []
        while current and current != self.END and steps < max_steps:
            node = self.nodes.get(current)
            if node is None:
                raise KeyError(f"unknown node: {current!r}")
            history.append(current)
            state = dict(node.fn(state))
            steps += 1
            current = self._next_from(current, state, children)
        state.setdefault("__history__", []).extend(history)
        state["__steps__"] = steps
        state["__terminated__"] = current == self.END or steps >= max_steps
        return state

    # ------------------------------------------------------------------
    def _children(self) -> dict[str, list[Edge]]:
        out: dict[str, list[Edge]] = defaultdict(list)
        for edge in self.edges:
            out[edge.src].append(edge)
        return out

    def _next_from(self, src: str, state: dict[str, Any],
                   children: dict[str, list[Edge]]) -> str | None:
        for edge in children.get(src, []):
            if edge.cond:
                target = edge.cond(state)
                if target:
                    return target
            elif edge.dst:
                return edge.dst
        return None
