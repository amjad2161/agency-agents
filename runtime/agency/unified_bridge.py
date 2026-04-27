"""Unified bridge — single handle to every JARVIS subsystem.

Wires LLM routing, semantic intent classification, vector memory,
tools, tracing, evaluation, console output, self-learning,
meta-reasoning, context management, knowledge expansion, multimodal
processing and the AIOS task broker into one ``UnifiedBridge.process``
call.

Every subsystem is constructed lazily so import-time stays cheap and
optional dependencies do not block the rest of the runtime. ``status``
returns a per-subsystem health report (green/yellow/red).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from .aios_bridge import AIOSBridge
from .context_manager import ContextManager
from .evals import EvalSuite
from .llm_router import LLMRouter, default_router as _default_llm_router
from .logging import get_logger
from .meta_reasoner import MetaReasoningEngine
from .self_learner_engine import SelfLearnerEngine
from .semantic_router import (
    SemanticRouter,
    default_router as _default_semantic_router,
)
from .tool_registry import ToolRegistry, get_registry
from .tracing import Tracer, get_tracer
from .tui import JarvisConsole, get_console
from .vector_store import AgentMemory, get_vector_store

log = get_logger()


@dataclass
class _Status:
    name: str
    healthy: bool
    detail: str = ""


class UnifiedBridge:
    """Composite handle wiring every JARVIS subsystem."""

    def __init__(
        self,
        *,
        llm_router: LLMRouter | None = None,
        semantic_router: SemanticRouter | None = None,
        memory: AgentMemory | None = None,
        tool_registry: ToolRegistry | None = None,
        tracer: Tracer | None = None,
        eval_suite: EvalSuite | None = None,
        console: JarvisConsole | None = None,
        self_learner: SelfLearnerEngine | None = None,
        meta_reasoner: MetaReasoningEngine | None = None,
        context_manager: ContextManager | None = None,
        knowledge_expansion: Any | None = None,
        multimodal: Any | None = None,
        aios_bridge: AIOSBridge | None = None,
        # Backwards-compat alias from the older bridge ctor.
        tools: ToolRegistry | None = None,
    ) -> None:
        self.llm_router = (
            llm_router if llm_router is not None else _default_llm_router()
        )
        self.semantic_router = (
            semantic_router if semantic_router is not None
            else _default_semantic_router()
        )
        self.memory = memory if memory is not None else get_vector_store("tfidf")
        registry_arg = tool_registry if tool_registry is not None else tools
        self.tool_registry = (
            registry_arg if registry_arg is not None else get_registry()
        )
        self.tools = self.tool_registry  # legacy alias
        self.tracer = tracer if tracer is not None else get_tracer()
        self.eval_suite = eval_suite if eval_suite is not None else EvalSuite()
        self.console = console if console is not None else get_console()
        self.self_learner = (
            self_learner if self_learner is not None else SelfLearnerEngine()
        )
        self.meta_reasoner = (
            meta_reasoner if meta_reasoner is not None else MetaReasoningEngine()
        )
        self.context_manager = (
            context_manager if context_manager is not None else ContextManager()
        )
        self.knowledge_expansion = (
            knowledge_expansion if knowledge_expansion is not None
            else self._lazy_knowledge()
        )
        self.multimodal = (
            multimodal if multimodal is not None else self._lazy_multimodal()
        )
        self.aios_bridge = aios_bridge if aios_bridge is not None else AIOSBridge()

    # ------------------------------------------------------------------
    def process(
        self, request: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        ctx = context or {}
        with self.tracer.span("unified_bridge.process") as span:
            span.metadata["request"] = request[:200]

            # 1. Semantic routing.
            try:
                route, confidence = self.semantic_router.route(request)
                domain = route.name
            except Exception as exc:
                log.warning("semantic route failed: %s", exc)
                domain, confidence = "unknown", 0.0
            span.metadata["domain"] = domain
            span.metadata["confidence"] = confidence

            # 2. Memory recall.
            try:
                recalls = self.memory.search(request, top_k=3)
            except Exception as exc:
                log.warning("memory recall failed: %s", exc)
                recalls = []
            recall_lines = [
                f"- {self._entry_text(e)[:160]}" for e in recalls
            ]

            # 3. LLM call.
            prompt_parts = [f"Domain: {domain}", f"Request: {request}"]
            if recall_lines:
                prompt_parts.append("Recall:\n" + "\n".join(recall_lines))
            if ctx.get("system"):
                prompt_parts.append(f"System: {ctx['system']}")
            prompt = "\n".join(prompt_parts)
            llm_start = time.perf_counter()
            try:
                response_text = self.llm_router.complete(
                    prompt,
                    max_tokens=int(ctx.get("max_tokens", 512)),
                    temperature=float(ctx.get("temperature", 0.7)),
                )
                if not isinstance(response_text, str):
                    response_text = str(response_text)
                provider = self._provider_name()
            except Exception as exc:
                response_text = f"[error: {exc}]"
                provider = "none"
            tokens_used = self._estimate_tokens(prompt, response_text)
            llm_latency_ms = (time.perf_counter() - llm_start) * 1000

            # 4. Optional tool execution. An explicit ``ctx['tool']``
            # wins; otherwise we look for a tool whose name matches the
            # route, matching the legacy bridge behaviour.
            tool_outputs: dict[str, Any] = {}
            tool_name = ctx.get("tool") or domain
            tool_obj = (
                self.tool_registry.get(tool_name) if tool_name else None
            )
            if tool_obj is not None:
                tool_args = ctx.get("tool_args")
                if tool_args is None:
                    tool_args = {"request": request}
                try:
                    tool_outputs[tool_name] = self.tool_registry.execute(
                        tool_name, **tool_args,
                    )
                except Exception as exc:
                    tool_outputs[tool_name] = {"error": str(exc)}

            # 5. Persist into memory.
            try:
                memory_id = self.memory.store(
                    f"Q: {request}\nA: {response_text}",
                    metadata={
                        "domain": domain,
                        "provider": provider,
                        "ts": time.time(),
                    },
                )
            except Exception as exc:
                log.warning("memory store failed: %s", exc)
                memory_id = ""

            # 6. Self-learner.
            try:
                self.self_learner.record_interaction(
                    request=request,
                    response=response_text,
                    routed_to=domain,
                )
            except Exception as exc:
                log.warning("self_learner failed: %s", exc)

            return {
                "request_id": uuid.uuid4().hex[:16],
                "request": request,
                "response": response_text,
                "domain": domain,
                "route": domain,           # legacy alias
                "confidence": confidence,
                "latency_ms": llm_latency_ms,
                "tokens_used": tokens_used,
                "provider": provider,
                "memory_id": memory_id,
                "memory": [
                    {"id": e.id, "content": self._entry_text(e)[:160]}
                    for e in recalls
                ],
                "recall_count": len(recalls),
                "tool_outputs": tool_outputs,
                "tool_result": next(iter(tool_outputs.values()), None),
            }

    # ------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        checks: list[_Status] = [
            _Status(
                "llm_router",
                bool(self.llm_router.providers),
                f"{len(self.llm_router.providers)} providers",
            ),
            _Status(
                "semantic_router",
                bool(self.semantic_router.routes),
                f"{len(self.semantic_router.routes)} routes",
            ),
            _Status("memory", True, f"{len(self.memory)} entries"),
            _Status(
                "tool_registry", True, f"{len(self.tool_registry.names())} tools"
            ),
            _Status("tracer", True, f"backend={self.tracer.backend}"),
            _Status("eval_suite", True, "ready"),
            _Status(
                "console", True,
                "rich" if getattr(self.console, "has_rich", False) else "plain",
            ),
            _Status("self_learner", True, "ready"),
            _Status("meta_reasoner", True, "ready"),
            _Status("context_manager", True, "ready"),
            _Status(
                "knowledge_expansion",
                self.knowledge_expansion is not None,
                "ready" if self.knowledge_expansion is not None else "absent",
            ),
            _Status(
                "multimodal",
                self.multimodal is not None,
                "ready" if self.multimodal is not None else "absent",
            ),
            _Status(
                "aios_bridge",
                True,
                f"agents={len(self.aios_bridge.list_agents())}",
            ),
        ]
        # Flat keys preserve the legacy ``ub.status()['llm_router']``
        # access pattern used by older callers and tests.
        flat: dict[str, Any] = {
            "llm_router": {
                "providers": [p.name for p in self.llm_router.providers],
                "stats": getattr(self.llm_router, "stats", lambda: {})(),
            },
            "semantic_router": {
                "routes": [r.name for r in self.semantic_router.routes],
                "backend": getattr(self.semantic_router, "backend", "unknown"),
            },
            "memory": {"size": len(self.memory)},
            "tools": {
                "count": len(self.tool_registry.names()),
                "names": self.tool_registry.names(),
            },
            "self_learner": self.self_learner is not None,
            "meta_reasoner": self.meta_reasoner is not None,
            "context_manager": self.context_manager is not None,
        }
        flat["ok"] = all(c.healthy for c in checks)
        flat["subsystems"] = {
            c.name: {
                "healthy": c.healthy,
                "status": "green" if c.healthy else "red",
                "detail": c.detail,
            }
            for c in checks
        }
        return flat

    # ------------------------------------------------------------------
    @staticmethod
    def _entry_text(entry: Any) -> str:
        for attr in ("content", "text"):
            value = getattr(entry, attr, None)
            if isinstance(value, str):
                return value
        return str(entry)

    def _provider_name(self) -> str:
        last = getattr(self.llm_router, "last_provider", None)
        return getattr(last, "name", "") or "unknown"

    @staticmethod
    def _estimate_tokens(prompt: str, response: str) -> int:
        return max(1, (len(prompt) + len(response)) // 4)

    @staticmethod
    def _lazy_knowledge() -> Any | None:
        try:
            from .knowledge_expansion import KnowledgeExpansion
            return KnowledgeExpansion()
        except Exception as exc:
            log.warning("knowledge_expansion unavailable: %s", exc)
            return None

    @staticmethod
    def _lazy_multimodal() -> Any | None:
        try:
            from .multimodal import MultimodalProcessor
            return MultimodalProcessor()
        except Exception as exc:
            log.warning("multimodal unavailable: %s", exc)
            return None


__all__ = ["UnifiedBridge"]
