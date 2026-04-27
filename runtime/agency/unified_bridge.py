"""UnifiedBridge — single handle that wires together all JARVIS subsystems.

Pipeline order on `process(request)`:
    1. Semantic route the request → route name + confidence
    2. Recall related entries from agent memory (vector store)
    3. Invoke a tool when one matches the route
    4. Record the outcome into the self-learner

Each subsystem is optional — missing pieces are skipped, not errored.
"""

from __future__ import annotations

import time
from typing import Any

from .logging import get_logger
from .llm_router import LLMRouter, default_router as _default_llm_router
from .semantic_router import SemanticRouter, default_router as _default_semantic_router
from .vector_store import AgentMemory, get_vector_store
from .tool_registry import ToolRegistry, get_registry as _tool_registry

log = get_logger()


class UnifiedBridge:
    """Composes the runtime subsystems into one entrypoint."""

    def __init__(
        self,
        llm_router: LLMRouter | None = None,
        semantic_router: SemanticRouter | None = None,
        memory: AgentMemory | None = None,
        tools: ToolRegistry | None = None,
        self_learner: Any = None,
        meta_reasoner: Any = None,
        context_manager: Any = None,
    ) -> None:
        self.llm_router = llm_router or _default_llm_router()
        self.semantic_router = semantic_router or _default_semantic_router()
        self.memory = memory or get_vector_store("tfidf")
        self.tools = tools or _tool_registry()
        self.self_learner = self_learner
        self.meta_reasoner = meta_reasoner
        self.context_manager = context_manager

    def process(self, request: str) -> dict[str, Any]:
        t0 = time.time()
        out: dict[str, Any] = {"request": request, "started_at": t0}

        # 1. Semantic routing
        try:
            route, confidence = self.semantic_router.route(request)
            out["route"] = route.name
            out["confidence"] = confidence
        except Exception as e:
            log.warning("semantic route failed: %s", e)
            out["route"] = "unknown"
            out["confidence"] = 0.0

        # 2. Memory recall
        try:
            recalled = self.memory.search(request, top_k=3)
            out["memory"] = [{"id": e.id, "content": e.content[:160]} for e in recalled]
        except Exception as e:
            log.warning("memory recall failed: %s", e)
            out["memory"] = []

        # 3. Tool execution if a tool matches the route name
        tool = self.tools.get(out["route"])
        if tool is not None and tool.fn is not None:
            try:
                out["tool_result"] = self.tools.execute(out["route"], request=request)
            except Exception as e:
                out["tool_result"] = {"error": repr(e)}
        else:
            out["tool_result"] = None

        # 4. Persist the request into memory for next time
        try:
            mem_id = self.memory.store(
                request,
                metadata={"route": out["route"], "confidence": out["confidence"]},
            )
            out["memory_id"] = mem_id
        except Exception as e:
            log.warning("memory store failed: %s", e)

        # 5. Record into self-learner (best-effort)
        if self.self_learner is not None:
            try:
                self.self_learner.record_interaction(
                    request=request,
                    response=str(out.get("tool_result") or ""),
                    domain_slug=out["route"],
                    feedback=None,
                )
            except Exception as e:
                log.warning("self_learner record failed: %s", e)

        out["latency_ms"] = (time.time() - t0) * 1000.0
        return out

    def status(self) -> dict[str, Any]:
        return {
            "llm_router": {
                "providers": [p.name for p in self.llm_router.providers],
                "stats": self.llm_router.stats(),
            },
            "semantic_router": {
                "routes": [r.name for r in self.semantic_router.routes],
                "backend": self.semantic_router.backend,
            },
            "memory": {"size": len(self.memory)},
            "tools": {"count": len(self.tools.list_tools()), "names": self.tools.names()},
            "self_learner": self.self_learner is not None,
            "meta_reasoner": self.meta_reasoner is not None,
            "context_manager": self.context_manager is not None,
        }


__all__ = ["UnifiedBridge"]
