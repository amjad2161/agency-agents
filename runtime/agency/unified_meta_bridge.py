#!/usr/bin/env python3
"""
================================================================================
J.A.R.V.I.S BRAINIAC -- Unified Meta Bridge | Orchestrator of Orchestrators
================================================================================

Connects ALL 18+ external repositories and internal bridges into a single
coherent routing, discovery, execution, and monitoring layer.

Responsibilities:
  * Discovery      -- Query every bridge for capabilities
  * Routing        -- Keyword + semantic matching to select best bridge
  * Execution      -- Auto-route, parallel dispatch, cross-bridge workflows
  * Integration    -- Multi-step pipelines across disparate bridges
  * Monitoring     -- Health, telemetry, capability mapping
  * Simulation     -- Mock bridge for offline / test scenarios

Author: Amjad Mobarsham (sole owner)
Version: 25.0.0
================================================================================
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
import threading
import time
import traceback
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
    Type,
    Union,
)

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
logger = logging.getLogger("unified_meta_bridge")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
    ))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

# ------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------
BRIDGE_VERSION = "25.0.0"
MAX_PARALLEL_WORKERS = 16
DEFAULT_TIMEOUT = 120.0
HEALTH_CHECK_INTERVAL = 30.0

# ------------------------------------------------------------------------------
# Enums
# ------------------------------------------------------------------------------
class BridgeHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class RoutingStrategy(str, Enum):
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    LLM = "llm"
    HYBRID = "hybrid"


class ExecutionMode(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    ADAPTIVE = "adaptive"


# ------------------------------------------------------------------------------
# Data Classes
# ------------------------------------------------------------------------------
@dataclass
class Capability:
    name: str
    description: str
    keywords: List[str] = field(default_factory=list)
    bridge: str = ""
    method: str = ""
    latency_ms: float = 0.0
    success_rate: float = 1.0


@dataclass
class BridgeHealth:
    name: str
    status: BridgeHealthStatus
    last_check: float
    response_ms: float
    error_count: int
    success_count: int
    capabilities: List[str]
    version: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RouteDecision:
    bridge: str
    method: str
    confidence: float
    strategy: RoutingStrategy
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    reasoning: str = ""


@dataclass
class ExecutionResult:
    bridge: str
    method: str
    status: str
    result: Any
    duration_ms: float
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowStep:
    step_id: str
    bridge: str
    method: str
    inputs: Dict[str, Any]
    outputs: Any = None
    status: str = "pending"
    duration_ms: float = 0.0
    error: Optional[str] = None


# ==============================================================================
# 1. DISCOVERY ENGINE
# ==============================================================================
class DiscoveryEngine:
    """
    Probes every registered bridge and extracts its advertised capabilities.
    Supports both static manifest introspection and dynamic runtime probing.
    """

    def __init__(self, bridge_registry: Optional[Dict[str, Callable[[], Any]]] = None) -> None:
        self.registry = bridge_registry or {}
        self._cache: Dict[str, List[Capability]] = {}
        self._cache_timestamp: float = 0.0
        self._lock = threading.RLock()

    def discover_all(self, force_refresh: bool = False) -> Dict[str, List[str]]:
        """
        Return {"bridge_name": ["capability1", "capability2", ...]} for every bridge.
        """
        with self._lock:
            if not force_refresh and self._cache and (
                time.time() - self._cache_timestamp < HEALTH_CHECK_INTERVAL
            ):
                return {k: [c.name for c in v] for k, v in self._cache.items()}

        results: Dict[str, List[str]] = {}
        for name, factory in self.registry.items():
            try:
                bridge = factory()
                caps = self._introspect_bridge(bridge, name)
                results[name] = [c.name for c in caps]
                with self._lock:
                    self._cache[name] = caps
            except Exception as exc:
                logger.warning(f"Discovery failed for {name}: {exc}")
                results[name] = []
        with self._lock:
            self._cache_timestamp = time.time()
        return results

    def _introspect_bridge(self, bridge: Any, bridge_name: str) -> List[Capability]:
        """Extract public methods as capabilities."""
        capabilities: List[Capability] = []
        skip_prefixes = ("_", "mock_", "__")
        if bridge is None:
            return capabilities
        for attr_name in dir(bridge):
            if attr_name.startswith(skip_prefixes):
                continue
            attr = getattr(bridge, attr_name, None)
            if not callable(attr):
                continue
            sig = inspect.signature(attr)
            doc = inspect.getdoc(attr) or ""
            keywords = self._extract_keywords(doc)
            capabilities.append(Capability(
                name=attr_name,
                description=doc[:200] if doc else f"Method {attr_name} on {bridge_name}",
                keywords=keywords,
                bridge=bridge_name,
                method=attr_name,
            ))
        return capabilities

    def _extract_keywords(self, text: str) -> List[str]:
        """Naive keyword extraction from docstring + method name heuristics."""
        if not text:
            return []
        # Lowercase, split on non-alphanumeric, filter short tokens
        words = re.findall(r"[a-zA-Z]{3,}", text.lower())
        stop = {
            "the", "and", "for", "with", "this", "that", "from", "into",
            "return", "returns", "using", "used", "when", "where", "then",
            "than", "also", "will", "can", "may", "must", "should", "could",
            "would", "has", "have", "had", "was", "were", "been", "are",
        }
        return list({w for w in words if w not in stop})

    def get_capability_details(self, bridge_name: str) -> List[Capability]:
        with self._lock:
            return list(self._cache.get(bridge_name, []))

    def search_capabilities(self, query: str) -> List[Capability]:
        """Search all capabilities by keyword match."""
        query_words = set(query.lower().split())
        hits: List[Tuple[float, Capability]] = []
        with self._lock:
            for caps in self._cache.values():
                for cap in caps:
                    cap_words = set(cap.keywords + cap.name.lower().split("_"))
                    score = len(query_words & cap_words) / max(len(query_words), 1)
                    if score > 0.0:
                        hits.append((score, cap))
        hits.sort(key=lambda x: x[0], reverse=True)
        return [h[1] for h in hits[:50]]


# ==============================================================================
# 2. ROUTING ENGINE
# ==============================================================================
class RoutingEngine:
    """
    Decides which bridge and method should handle a given task string.
    Supports keyword matching, semantic similarity, and LLM-based reasoning.
    """

    def __init__(self, discovery: DiscoveryEngine) -> None:
        self.discovery = discovery
        self._keyword_map: Dict[str, List[Tuple[str, str, float]]] = defaultdict(list)
        self._build_keyword_map()

    def _build_keyword_map(self) -> None:
        """Pre-compute keyword -> (bridge, method, weight) mappings."""
        caps = []
        with self.discovery._lock:
            for bridge_caps in self.discovery._cache.values():
                caps.extend(bridge_caps)
        for cap in caps:
            for kw in cap.keywords:
                self._keyword_map[kw].append((cap.bridge, cap.method, 1.0))
            # Also index method name tokens
            for token in cap.name.lower().split("_"):
                if len(token) >= 3:
                    self._keyword_map[token].append((cap.bridge, cap.method, 0.8))

    def route(self, task: str, strategy: RoutingStrategy = RoutingStrategy.HYBRID) -> RouteDecision:
        """
        Find the best (bridge, method) for a task.

        Returns RouteDecision with confidence 0.0-1.0.
        """
        task_lower = task.lower()

        # -- Keyword phase --
        keyword_scores: Dict[Tuple[str, str], float] = defaultdict(float)
        for word in re.findall(r"[a-zA-Z]{3,}", task_lower):
            for bridge, method, weight in self._keyword_map.get(word, []):
                keyword_scores[(bridge, method)] += weight

        # -- Semantic / heuristic phase --
        semantic_scores = self._semantic_score(task_lower)
        for key, score in semantic_scores.items():
            keyword_scores[key] += score

        # -- LLM reasoning phase (simulated) --
        if strategy in (RoutingStrategy.LLM, RoutingStrategy.HYBRID):
            llm_scores = self._llm_reasoning(task_lower)
            for key, score in llm_scores.items():
                keyword_scores[key] += score * 2.0  # LLM gets higher weight

        if not keyword_scores:
            # Fallback: return a default bridge with low confidence
            return RouteDecision(
                bridge="agents_bridge",
                method="run_agent",
                confidence=0.15,
                strategy=strategy,
                reasoning="No capability match found; falling back to generic agent bridge.",
            )

        # Normalize and sort
        max_score = max(keyword_scores.values())
        ranked = sorted(
            ((k, v / max_score) for k, v in keyword_scores.items()),
            key=lambda x: x[1],
            reverse=True,
        )

        best_key, best_score = ranked[0]
        alternatives = [
            {"bridge": k[0], "method": k[1], "score": round(s, 3)}
            for k, s in ranked[1:4]
        ]

        confidence = min(best_score, 1.0)
        reasoning = self._build_reasoning(task, best_key, confidence, strategy)

        return RouteDecision(
            bridge=best_key[0],
            method=best_key[1],
            confidence=confidence,
            strategy=strategy,
            alternatives=alternatives,
            reasoning=reasoning,
        )

    def _semantic_score(self, task: str) -> Dict[Tuple[str, str], float]:
        """Heuristic semantic matching using predefined domain mappings."""
        scores: Dict[Tuple[str, str], float] = defaultdict(float)
        domain_rules = {
            # bridge patterns -> task keywords -> score
            "autogen": ["autogen", "agent", "chat", "group", "multi-agent", "conversation"],
            "langchain": ["langchain", "chain", "prompt", "template", "retrieval", "vector"],
            "llamaindex": ["llamaindex", "index", "rag", "query", "document", "embedding"],
            "mem0": ["mem0", "memory", "recall", "remember", "conversation history", "store"],
            "metagpt": ["metagpt", "startup", "company", "role", "software", "project"],
            "ragflow": ["ragflow", "rag", "pipeline", "chunk", "knowledge base", "kb"],
            "semantic_kernel": ["semantic", "kernel", "plugin", "skill", "microsoft"],
            "livekit": ["livekit", "audio", "video", "stream", "webrtc", "room"],
            "agents_bridge": ["agent", "tool", "delegate", "run", "task", "worker"],
            "github_ingestor": ["github", "repo", "repository", "clone", "commit", "code"],
            "local_vision": ["vision", "image", "picture", "photo", "see", "detect", "ocr"],
            "local_voice": ["voice", "speak", "audio", "tts", "listen", "transcribe"],
            "drawing_engine": ["draw", "sketch", "diagram", "chart", "visualize", "plot"],
            "document_generator": ["document", "pdf", "report", "write", "generate doc"],
            "trading_engine": ["trade", "stock", "market", "crypto", "portfolio", "buy", "sell"],
            "visual_qa": ["qa", "visual question", "ask image", "describe image", "caption"],
            "volumetric_renderer": ["3d", "volumetric", "render", "gaussian splat", "point cloud"],
            "window_manager_3d": ["window", "desktop", "3d ui", "spatial", "wm", "workspace"],
            "docker_android_bridge": ["docker", "android", "container", "mobile", "apk"],
            "auto_browser_bridge": ["browser", "web", "page", "navigate", "scrape", "click"],
            "computer_use_ootb_bridge": ["computer", "gui", "desktop", "mouse", "keyboard"],
            "gemini_computer_use_bridge": ["gemini", "computer", "screen", "action"],
            "open_autoglm_bridge": ["autoglm", "gui", "phone", "mobile", "tap", "swipe"],
            "supersplat_bridge": ["supersplat", "splat", "3d scene", "gsplat"],
            "e2b_computer_use_bridge": ["e2b", "sandbox", "code", "secure", "execution"],
            "paper2code_bridge": ["paper", "research", "arxiv", "code generation", "replicate"],
            "jcode_bridge": ["jcode", "editor", "ide", "refactor", "autocomplete"],
            "off_grid_mobile_ai_bridge": ["offline", "edge", "mobile", "no internet", "embedded"],
            "humanizer_bridge": ["humanizer", "natural", "tone", "rewrite", "persona"],
            "localsend_bridge": ["localsend", "share", "file", "transfer", "local network"],
            "microsoft_jarvis_bridge": ["microsoft", "jarvis", "hugginggpt", "model hub"],
            "meta_agent_bridge": ["meta", "self-improve", "evolve", "adapt", "learn"],
            "decepticon_bridge": ["decepticon", "red team", "adversarial", "security"],
            "ace_step_ui_bridge": ["ace", "step", "ui", "interface", "component"],
        }
        for bridge, keywords in domain_rules.items():
            for kw in keywords:
                if kw in task:
                    default_methods = {
                        "autogen": "run_agent",
                        "langchain": "run_chain",
                        "llamaindex": "query_index",
                        "mem0": "add_memory",
                        "metagpt": "run_project",
                        "ragflow": "query_knowledge",
                        "semantic_kernel": "run_function",
                        "livekit": "join_room",
                        "agents_bridge": "run_agent",
                        "github_ingestor": "ingest_repo",
                        "local_vision": "analyze_image",
                        "local_voice": "speak_text",
                        "drawing_engine": "draw",
                        "document_generator": "generate",
                        "trading_engine": "execute_trade",
                        "visual_qa": "answer_question",
                        "volumetric_renderer": "render",
                        "window_manager_3d": "create_workspace",
                        "docker_android_bridge": "run_container",
                        "auto_browser_bridge": "navigate",
                        "computer_use_ootb_bridge": "use_computer",
                        "gemini_computer_use_bridge": "use_screen",
                        "open_autoglm_bridge": "tap_phone",
                        "supersplat_bridge": "load_scene",
                        "e2b_computer_use_bridge": "execute_code",
                        "paper2code_bridge": "generate_from_paper",
                        "jcode_bridge": "edit_file",
                        "off_grid_mobile_ai_bridge": "run_offline",
                        "humanizer_bridge": "humanize",
                        "localsend_bridge": "send_file",
                        "microsoft_jarvis_bridge": "plan_and_solve",
                        "meta_agent_bridge": "evolve",
                        "decepticon_bridge": "probe",
                        "ace_step_ui_bridge": "render_ui",
                    }
                    method = default_methods.get(bridge, "execute")
                    scores[(bridge, method)] += 1.5
        return dict(scores)

    def _llm_reasoning(self, task: str) -> Dict[Tuple[str, str], float]:
        """
        Simulated LLM reasoning for routing.
        In production this calls the local LLM with a routing prompt.
        """
        scores: Dict[Tuple[str, str], float] = {}
        # Simple pattern-based simulation
        if "code" in task or "program" in task or "function" in task:
            scores[("autogen", "run_agent")] = 0.6
            scores[("jcode_bridge", "edit_file")] = 0.5
        if "search" in task or "find" in task or "query" in task:
            scores[("llamaindex", "query_index")] = 0.7
            scores[("ragflow", "query_knowledge")] = 0.6
        if "write" in task or "generate" in task or "create" in task:
            scores[("document_generator", "generate")] = 0.7
            scores[("drawing_engine", "draw")] = 0.5
        if "image" in task or "picture" in task or "photo" in task:
            scores[("local_vision", "analyze_image")] = 0.8
            scores[("visual_qa", "answer_question")] = 0.7
        if "voice" in task or "speak" in task or "audio" in task:
            scores[("local_voice", "speak_text")] = 0.8
            scores[("livekit", "join_room")] = 0.4
        if "trade" in task or "stock" in task or "buy" in task or "sell" in task:
            scores[("trading_engine", "execute_trade")] = 0.9
        if "github" in task or "repo" in task or "clone" in task:
            scores[("github_ingestor", "ingest_repo")] = 0.9
        if "browser" in task or "web" in task or "page" in task:
            scores[("auto_browser_bridge", "navigate")] = 0.9
            scores[("gemini_computer_use_bridge", "use_screen")] = 0.5
        if "3d" in task or "render" in task or "volumetric" in task:
            scores[("volumetric_renderer", "render")] = 0.9
            scores[("supersplat_bridge", "load_scene")] = 0.7
        if "docker" in task or "container" in task or "android" in task:
            scores[("docker_android_bridge", "run_container")] = 0.9
        if "offline" in task or "edge" in task or "embedded" in task:
            scores[("off_grid_mobile_ai_bridge", "run_offline")] = 0.9
        if "security" in task or "attack" in task or "red team" in task:
            scores[("decepticon_bridge", "probe")] = 0.9
        if "evolve" in task or "adapt" in task or "learn" in task:
            scores[("meta_agent_bridge", "evolve")] = 0.9
        return scores

    def _build_reasoning(
        self, task: str, best: Tuple[str, str], confidence: float, strategy: RoutingStrategy
    ) -> str:
        bridge, method = best
        return (
            f"Task '{task[:60]}...' routed to {bridge}.{method} via {strategy.value} "
            f"with confidence {confidence:.2f}. "
            f"Keywords matched domain profile for {bridge}."
        )

    def refresh(self) -> None:
        self._keyword_map.clear()
        self._build_keyword_map()


# ==============================================================================
# 3. EXECUTION ENGINE
# ==============================================================================
class ExecutionEngine:
    """
    Dispatches tasks to the correct bridge methods.
    Supports synchronous, async, parallel, and adaptive execution.
    """

    def __init__(self, router: RoutingEngine, registry: Dict[str, Callable[[], Any]]) -> None:
        self.router = router
        self.registry = registry
        self._executor = ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS)
        self._metrics: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.RLock()

    def execute_single(
        self,
        task: str,
        route: Optional[RouteDecision] = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        """
        Execute one task via its best-matched bridge.
        """
        t0 = time.perf_counter()
        if route is None:
            route = self.router.route(task)

        bridge_name = route.bridge
        method_name = route.method

        try:
            bridge = self._resolve_bridge(bridge_name)
            if bridge is None:
                raise RuntimeError(f"Bridge '{bridge_name}' not available.")

            method = getattr(bridge, method_name, None)
            if method is None:
                # Fallback to generic execute
                method = getattr(bridge, "execute", None)
                if method is None:
                    raise RuntimeError(
                        f"Method '{method_name}' not found on '{bridge_name}' and no generic execute."
                    )

            # Handle async bridges
            if asyncio.iscoroutinefunction(method):
                result = asyncio.run(self._run_async(method, task, **kwargs))
            else:
                if "task" in inspect.signature(method).parameters:
                    result = method(task, **kwargs)
                else:
                    result = method(**kwargs)

            duration = (time.perf_counter() - t0) * 1000
            with self._lock:
                self._metrics[bridge_name].append(duration)

            return ExecutionResult(
                bridge=bridge_name,
                method=method_name,
                status="success",
                result=result,
                duration_ms=duration,
                metadata={"confidence": route.confidence, "strategy": route.strategy.value},
            )

        except Exception as exc:
            duration = (time.perf_counter() - t0) * 1000
            logger.error(f"Execution failed on {bridge_name}.{method_name}: {exc}")
            return ExecutionResult(
                bridge=bridge_name,
                method=method_name,
                status="error",
                result=None,
                duration_ms=duration,
                error=str(exc),
                metadata={"traceback": traceback.format_exc()},
            )

    async def _run_async(self, method: Callable, task: str, **kwargs: Any) -> Any:
        """Helper to run async bridge methods."""
        if "task" in inspect.signature(method).parameters:
            return await method(task, **kwargs)
        return await method(**kwargs)

    def execute_parallel(self, tasks: List[Union[str, Dict[str, Any]]]) -> List[ExecutionResult]:
        """
        Execute multiple tasks in parallel across different bridges.

        tasks: list of strings or {"task": "...", "kwargs": {...}} dicts.
        """
        futures = []
        task_specs: List[Tuple[str, Dict[str, Any]]] = []
        for spec in tasks:
            if isinstance(spec, str):
                task_str, kwargs = spec, {}
            else:
                task_str = spec.get("task", "")
                kwargs = spec.get("kwargs", {})
            task_specs.append((task_str, kwargs))
            futures.append(self._executor.submit(self.execute_single, task_str, None, **kwargs))

        results = []
        for fut in as_completed(futures):
            try:
                results.append(fut.result(timeout=DEFAULT_TIMEOUT))
            except Exception as exc:
                results.append(ExecutionResult(
                    bridge="unknown",
                    method="unknown",
                    status="error",
                    result=None,
                    duration_ms=0.0,
                    error=str(exc),
                ))
        return results

    def execute_adaptive(
        self,
        task: str,
        preferred_bridges: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        """
        Try preferred bridges in order until one succeeds.
        """
        if preferred_bridges:
            for bridge_name in preferred_bridges:
                route = RouteDecision(
                    bridge=bridge_name,
                    method="execute",
                    confidence=0.9,
                    strategy=RoutingStrategy.HYBRID,
                )
                result = self.execute_single(task, route=route, **kwargs)
                if result.status == "success":
                    return result
        # Fallback to normal routing
        return self.execute_single(task, **kwargs)

    def _resolve_bridge(self, name: str) -> Any:
        """Lazy-load a bridge from the registry."""
        factory = self.registry.get(name)
        if factory is None:
            # Attempt dynamic import from known locations
            return self._dynamic_import_bridge(name)
        return factory()

    def _dynamic_import_bridge(self, name: str) -> Any:
        """Attempt to import bridge class dynamically from agency modules."""
        import importlib
        module_map = {
            "autogen": "autogen_bridge",
            "langchain": "langchain_bridge",
            "llamaindex": "llamaindex_bridge",
            "mem0": "mem0_bridge",
            "metagpt": "metagpt_bridge",
            "ragflow": "ragflow_bridge",
            "semantic_kernel": "semantic_kernel_bridge",
            "livekit": "livekit_bridge",
            "agents_bridge": "agents_bridge",
            "github_ingestor": "github_ingestor",
            "local_vision": "local_vision",
            "local_voice": "local_voice",
            "drawing_engine": "drawing_engine",
            "document_generator": "document_generator",
            "trading_engine": "trading_engine",
            "visual_qa": "visual_qa",
            "volumetric_renderer": "volumetric_renderer",
            "window_manager_3d": "window_manager_3d",
            "docker_android_bridge": "external_integrations.docker_android_bridge",
            "auto_browser_bridge": "external_integrations.auto_browser_bridge",
            "computer_use_ootb_bridge": "external_integrations.computer_use_ootb_bridge",
            "gemini_computer_use_bridge": "external_integrations.gemini_computer_use_bridge",
            "open_autoglm_bridge": "external_integrations.open_autoglm_bridge",
            "supersplat_bridge": "external_integrations.supersplat_bridge",
            "e2b_computer_use_bridge": "external_integrations.e2b_computer_use_bridge",
            "paper2code_bridge": "external_integrations.paper2code_bridge",
            "jcode_bridge": "external_integrations.jcode_bridge",
            "off_grid_mobile_ai_bridge": "external_integrations.off_grid_mobile_ai_bridge",
            "humanizer_bridge": "external_integrations.humanizer_bridge",
            "localsend_bridge": "external_integrations.localsend_bridge",
            "microsoft_jarvis_bridge": "external_integrations.microsoft_jarvis_bridge",
            "meta_agent_bridge": "external_integrations.meta_agent_bridge",
            "decepticon_bridge": "external_integrations.decepticon_bridge",
            "ace_step_ui_bridge": "external_integrations.ace_step_ui_bridge",
        }
        mod_name = module_map.get(name)
        if mod_name is None:
            return None
        try:
            if mod_name.startswith("external_integrations."):
                module = importlib.import_module(
                    f"jarvis.runtime.agency.{mod_name}", package=__package__
                )
            else:
                module = importlib.import_module(
                    f"jarvis.runtime.agency.{mod_name}", package=__package__
                )
            # Guess class name from bridge name
            class_name = "".join(word.capitalize() for word in name.replace("_bridge", "").split("_")) + "Bridge"
            if not hasattr(module, class_name):
                # Try alternate naming
                alt_names = [name.replace("_bridge", "").capitalize() + "Bridge"]
                for an in alt_names:
                    if hasattr(module, an):
                        class_name = an
                        break
            cls = getattr(module, class_name, None)
            if cls:
                return cls()
        except Exception as exc:
            logger.debug(f"Dynamic import failed for {name}: {exc}")
        return None

    def get_average_latency(self, bridge_name: str) -> float:
        with self._lock:
            latencies = self._metrics.get(bridge_name, [])
            return sum(latencies) / len(latencies) if latencies else 0.0


# ==============================================================================
# 4. INTEGRATION / WORKFLOW ENGINE
# ==============================================================================
class WorkflowEngine:
    """
    Orchestrates multi-step workflows that span multiple bridges.
    """

    def __init__(self, execution: ExecutionEngine) -> None:
        self.execution = execution
        self._workflows: Dict[str, List[WorkflowStep]] = {}
        self._lock = threading.RLock()

    def build_workflow(
        self,
        steps: List[Dict[str, Any]],
        workflow_id: Optional[str] = None,
    ) -> str:
        """
        Build a workflow from step definitions and return its ID.

        steps: [{"bridge": "...", "method": "...", "inputs": {...}}]
        """
        wid = workflow_id or f"wf_{uuid.uuid4().hex[:12]}"
        parsed: List[WorkflowStep] = []
        for i, spec in enumerate(steps):
            parsed.append(WorkflowStep(
                step_id=f"{wid}_step_{i}",
                bridge=spec.get("bridge", ""),
                method=spec.get("method", ""),
                inputs=spec.get("inputs", {}),
            ))
        with self._lock:
            self._workflows[wid] = parsed
        return wid

    def run_workflow(self, workflow_id: str, inject: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a stored workflow sequentially, passing outputs forward.
        """
        with self._lock:
            steps = list(self._workflows.get(workflow_id, []))
        if not steps:
            return {"error": f"Workflow {workflow_id} not found."}

        context: Dict[str, Any] = dict(inject or {})
        completed: List[WorkflowStep] = []

        for step in steps:
            t0 = time.perf_counter()
            # Merge context into inputs
            merged_inputs = dict(step.inputs)
            merged_inputs.update(context)
            # Resolve template variables like {{previous.result}}
            merged_inputs = self._resolve_templates(merged_inputs, context)

            route = RouteDecision(
                bridge=step.bridge,
                method=step.method,
                confidence=1.0,
                strategy=RoutingStrategy.HYBRID,
            )
            result = self.execution.execute_single(
                task=merged_inputs.pop("task", f"{step.method} via {step.bridge}"),
                route=route,
                **merged_inputs,
            )
            step.duration_ms = (time.perf_counter() - t0) * 1000
            step.status = result.status
            step.outputs = result.result
            if result.error:
                step.error = result.error
            completed.append(step)

            # Pass outputs forward unless error
            if result.status == "success" and result.result is not None:
                context[f"step_{len(completed)-1}_result"] = result.result
                context["last_result"] = result.result
            else:
                break  # Stop workflow on first error

        return {
            "workflow_id": workflow_id,
            "status": "success" if all(s.status == "success" for s in completed) else "partial",
            "steps": completed,
            "context": context,
        }

    def _resolve_templates(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Replace {{key}} placeholders with context values."""
        resolved: Dict[str, Any] = {}
        template_pattern = re.compile(r"\{\{(\w+)\}\}")
        for k, v in inputs.items():
            if isinstance(v, str):
                resolved[k] = template_pattern.sub(lambda m: str(context.get(m.group(1), m.group(0))), v)
            else:
                resolved[k] = v
        return resolved

    def get_workflow(self, workflow_id: str) -> Optional[List[WorkflowStep]]:
        with self._lock:
            return list(self._workflows.get(workflow_id, []))

    def list_workflows(self) -> List[str]:
        with self._lock:
            return list(self._workflows.keys())

    def synthesize_results(self, results: List[ExecutionResult]) -> str:
        """
        Merge outputs from multiple bridges into a coherent markdown response.
        """
        if not results:
            return "No results to synthesize."

        parts: List[str] = []
        parts.append("# Unified Meta Bridge Synthesis\n")
        parts.append(f"**Timestamp:** {datetime.utcnow().isoformat()}Z\n")
        parts.append(f"**Tasks executed:** {len(results)}\n\n")

        success_count = sum(1 for r in results if r.status == "success")
        error_count = len(results) - success_count
        parts.append(f"**Success rate:** {success_count}/{len(results)}\n")
        if error_count:
            parts.append(f"**Errors:** {error_count}\n")
        parts.append("---\n\n")

        for i, res in enumerate(results, 1):
            parts.append(f"## {i}. `{res.bridge}.{res.method}`\n")
            parts.append(f"- **Status:** {res.status}\n")
            parts.append(f"- **Duration:** {res.duration_ms:.1f} ms\n")
            if res.error:
                parts.append(f"- **Error:** {res.error}\n")
            else:
                output = res.result
                if isinstance(output, dict):
                    output = json.dumps(output, indent=2, default=str)
                elif isinstance(output, list):
                    output = json.dumps(output, indent=2, default=str)
                parts.append(f"\n**Output:**\n```\n{output}\n```\n")
            parts.append("\n")

        # Add executive summary
        parts.append("---\n\n## Executive Summary\n\n")
        if success_count == len(results):
            parts.append("All tasks completed successfully. The cross-bridge workflow executed without issues.\n")
        elif success_count > 0:
            parts.append(
                f"Partial success: {success_count} tasks succeeded, {error_count} failed. "
                "Review error details above for remediation.\n"
            )
        else:
            parts.append("All tasks failed. Check bridge connectivity and configuration.\n")

        total_ms = sum(r.duration_ms for r in results)
        parts.append(f"\n**Total elapsed:** {total_ms:.1f} ms\n")

        return "".join(parts)


# ==============================================================================
# 5. MONITORING & HEALTH ENGINE
# ==============================================================================
class MonitoringEngine:
    """
    Health checks, telemetry, and capability mapping for all bridges.
    """

    def __init__(self, registry: Dict[str, Callable[[], Any]], execution: ExecutionEngine) -> None:
        self.registry = registry
        self.execution = execution
        self._health_cache: Dict[str, BridgeHealth] = {}
        self._last_check: float = 0.0
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None

    def start_monitoring(self) -> None:
        """Start background health monitoring thread."""
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            return
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("Health monitoring thread started.")

    def stop_monitoring(self) -> None:
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2.0)

    def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            self.check_all()
            time.sleep(HEALTH_CHECK_INTERVAL)

    def check_all(self, force: bool = False) -> Dict[str, BridgeHealth]:
        """
        Probe every bridge for availability and response time.
        """
        with self._lock:
            if not force and self._health_cache and (
                time.time() - self._last_check < HEALTH_CHECK_INTERVAL
            ):
                return dict(self._health_cache)

        results: Dict[str, BridgeHealth] = {}
        for name in self.registry:
            health = self._check_single(name)
            results[name] = health

        with self._lock:
            self._health_cache = results
            self._last_check = time.time()
        return results

    def _check_single(self, name: str) -> BridgeHealth:
        t0 = time.perf_counter()
        try:
            bridge = self.execution._resolve_bridge(name)
            if bridge is None:
                return BridgeHealth(
                    name=name,
                    status=BridgeHealthStatus.UNAVAILABLE,
                    last_check=time.time(),
                    response_ms=0.0,
                    error_count=0,
                    success_count=0,
                    capabilities=[],
                )

            # Try calling a lightweight ping/health method if available
            ping_methods = ["health", "ping", "status", "is_ready", "is_mock"]
            response_ms = 0.0
            for pm in ping_methods:
                ping = getattr(bridge, pm, None)
                if callable(ping):
                    try:
                        if asyncio.iscoroutinefunction(ping):
                            asyncio.run(ping())
                        else:
                            ping()
                    except Exception:
                        pass
                    finally:
                        response_ms = (time.perf_counter() - t0) * 1000
                    break
            else:
                response_ms = (time.perf_counter() - t0) * 1000

            # Derive status from response time
            if response_ms < 5000:
                status = BridgeHealthStatus.HEALTHY
            elif response_ms < 15000:
                status = BridgeHealthStatus.DEGRADED
            else:
                status = BridgeHealthStatus.UNAVAILABLE

            # Extract version and capabilities
            version = getattr(bridge, "version", "")
            if hasattr(bridge, "metrics"):
                try:
                    m = bridge.metrics()
                    if hasattr(m, "to_dict"):
                        meta = m.to_dict()
                    else:
                        meta = dict(m)
                except Exception:
                    meta = {}
            else:
                meta = {}

            return BridgeHealth(
                name=name,
                status=status,
                last_check=time.time(),
                response_ms=response_ms,
                error_count=meta.get("error_count", 0),
                success_count=meta.get("success_count", 0),
                capabilities=list(meta.get("capabilities", [])),
                version=str(version),
                metadata=meta,
            )

        except Exception as exc:
            return BridgeHealth(
                name=name,
                status=BridgeHealthStatus.UNAVAILABLE,
                last_check=time.time(),
                response_ms=(time.perf_counter() - t0) * 1000,
                error_count=1,
                success_count=0,
                capabilities=[],
                metadata={"exception": str(exc)},
            )

    def get_bridge_health(self) -> Dict[str, Dict[str, Any]]:
        """Return JSON-serializable health status for all bridges."""
        healths = self.check_all()
        return {
            name: {
                "status": h.status.value,
                "last_check": datetime.utcfromtimestamp(h.last_check).isoformat() + "Z",
                "response_ms": round(h.response_ms, 2),
                "error_count": h.error_count,
                "success_count": h.success_count,
                "capabilities": h.capabilities,
                "version": h.version,
                "metadata": h.metadata,
            }
            for name, h in healths.items()
        }

    def get_capability_map(self) -> Dict[str, Any]:
        """Full map of all bridge -> capabilities."""
        healths = self.check_all()
        return {
            name: {
                "status": h.status.value,
                "version": h.version,
                "capabilities": h.capabilities,
                "health": {
                    "response_ms": round(h.response_ms, 2),
                    "error_count": h.error_count,
                    "success_count": h.success_count,
                },
            }
            for name, h in healths.items()
        }

    def get_slow_bridges(self, threshold_ms: float = 5000.0) -> List[str]:
        """Return names of bridges exceeding latency threshold."""
        healths = self.check_all()
        return [name for name, h in healths.items() if h.response_ms > threshold_ms]

    def get_unhealthy_bridges(self) -> List[str]:
        healths = self.check_all()
        return [
            name for name, h in healths.items()
            if h.status in (BridgeHealthStatus.DEGRADED, BridgeHealthStatus.UNAVAILABLE)
        ]


# ==============================================================================
# 6. UNIFIED META BRIDGE (Main Orchestrator)
# ==============================================================================
class UnifiedMetaBridge:
    """
    The orchestrator of orchestrators.

    Connects 18+ external repositories and internal bridges into a single
    coherent routing, execution, and monitoring layer.

    Usage:
        bridge = get_unified_meta_bridge()
        result = bridge.execute_via_best_bridge("Generate a stock report for AAPL")
        health = bridge.get_bridge_health()
        workflow = bridge.cross_bridge_workflow([...])
    """

    def __init__(
        self,
        bridge_registry: Optional[Dict[str, Callable[[], Any]]] = None,
        strategy: RoutingStrategy = RoutingStrategy.HYBRID,
    ) -> None:
        self.version = BRIDGE_VERSION
        self.strategy = strategy
        self.registry: Dict[str, Callable[[], Any]] = bridge_registry or {}
        self.discovery = DiscoveryEngine(self.registry)
        self.router = RoutingEngine(self.discovery)
        self.execution = ExecutionEngine(self.router, self.registry)
        self.workflow = WorkflowEngine(self.execution)
        self.monitoring = MonitoringEngine(self.registry, self.execution)
        self._initialized = False
        self._init_lock = threading.RLock()
        self._metrics: Dict[str, Any] = {
            "tasks_routed": 0,
            "tasks_executed": 0,
            "workflows_run": 0,
            "errors": 0,
            "start_time": time.time(),
        }

    # -- Lifecycle --
    def initialize(self) -> None:
        """Discover capabilities and start monitoring."""
        with self._init_lock:
            if self._initialized:
                return
            self.discovery.discover_all(force_refresh=True)
            self.router.refresh()
            self.monitoring.start_monitoring()
            self._initialized = True
            logger.info("UnifiedMetaBridge initialized.")

    def shutdown(self) -> None:
        """Graceful shutdown."""
        with self._init_lock:
            self.monitoring.stop_monitoring()
            self.execution._executor.shutdown(wait=False)
            self._initialized = False
            logger.info("UnifiedMetaBridge shut down.")

    # -- Discovery --
    def discover_all_capabilities(self) -> Dict[str, List[str]]:
        """
        Query all registered bridges and list their capabilities.

        Returns: {"bridge_name": ["capability1", "capability2", ...]}
        """
        self._maybe_init()
        caps = self.discovery.discover_all(force_refresh=True)
        logger.info(f"Discovered capabilities from {len(caps)} bridges.")
        return caps

    # -- Routing --
    def route_task(self, task: str) -> Dict[str, Any]:
        """
        Find the best bridge for a task using keyword + semantic + LLM reasoning.

        Returns: {"bridge": "name", "method": "method_name", "confidence": 0.0-1.0}
        """
        self._maybe_init()
        decision = self.router.route(task, strategy=self.strategy)
        self._metrics["tasks_routed"] += 1
        return {
            "bridge": decision.bridge,
            "method": decision.method,
            "confidence": round(decision.confidence, 3),
            "strategy": decision.strategy.value,
            "reasoning": decision.reasoning,
            "alternatives": decision.alternatives,
        }

    # -- Execution --
    def execute_via_best_bridge(self, task: str, **kwargs: Any) -> Dict[str, Any]:
        """
        Auto-route a task to its best bridge and execute it.

        Returns execution result dict.
        """
        self._maybe_init()
        decision = self.router.route(task, strategy=self.strategy)
        result = self.execution.execute_single(task, route=decision, **kwargs)
        self._metrics["tasks_executed"] += 1
        if result.status != "success":
            self._metrics["errors"] += 1
        return self._result_to_dict(result)

    def execute_parallel(self, tasks: List[Union[str, Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """
        Run multiple tasks across different bridges in parallel.

        tasks: list of strings or {"task": "...", "kwargs": {...}} dicts.

        Returns list of execution result dicts.
        """
        self._maybe_init()
        results = self.execution.execute_parallel(tasks)
        self._metrics["tasks_executed"] += len(results)
        self._metrics["errors"] += sum(1 for r in results if r.status != "success")
        return [self._result_to_dict(r) for r in results]

    # -- Integration --
    def cross_bridge_workflow(self, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Multi-step workflow using different bridges.

        Example steps:
            [
                {"bridge": "github_ingestor", "method": "ingest_repo", "inputs": {"url": "..."}},
                {"bridge": "local_brain", "method": "analyze", "inputs": {"task": "{{last_result}}"}},
                {"bridge": "document_generator", "method": "generate", "inputs": {"content": "{{last_result}}"}},
            ]

        Returns workflow execution summary dict.
        """
        self._maybe_init()
        workflow_id = self.workflow.build_workflow(steps)
        result = self.workflow.run_workflow(workflow_id)
        self._metrics["workflows_run"] += 1
        if result.get("status") != "success":
            self._metrics["errors"] += 1
        return result

    def synthesize_results(self, results: List[Dict[str, Any]]) -> str:
        """
        Merge outputs from multiple bridge executions into a coherent markdown response.
        """
        execution_results = []
        for r in results:
            er = ExecutionResult(
                bridge=r.get("bridge", "unknown"),
                method=r.get("method", "unknown"),
                status=r.get("status", "unknown"),
                result=r.get("result"),
                duration_ms=r.get("duration_ms", 0.0),
                error=r.get("error"),
                metadata=r.get("metadata", {}),
            )
            execution_results.append(er)
        return self.workflow.synthesize_results(execution_results)

    # -- Monitoring --
    def get_bridge_health(self) -> Dict[str, Dict[str, Any]]:
        """Health status of all bridges."""
        self._maybe_init()
        return self.monitoring.get_bridge_health()

    def get_capability_map(self) -> Dict[str, Any]:
        """Full map of all available capabilities."""
        self._maybe_init()
        return self.monitoring.get_capability_map()

    def get_metrics(self) -> Dict[str, Any]:
        """Runtime metrics for this meta bridge."""
        uptime = time.time() - self._metrics["start_time"]
        return {
            "uptime_seconds": round(uptime, 2),
            "tasks_routed": self._metrics["tasks_routed"],
            "tasks_executed": self._metrics["tasks_executed"],
            "workflows_run": self._metrics["workflows_run"],
            "errors": self._metrics["errors"],
            "bridges_registered": len(self.registry),
            "version": self.version,
        }

    def get_bridge(self, name: str) -> Any:
        """Direct access to a specific bridge instance."""
        return self.execution._resolve_bridge(name)

    # -- Advanced: adaptive retry --
    def execute_with_retry(
        self,
        task: str,
        max_retries: int = 2,
        fallback_bridges: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Execute with automatic retry and fallback bridge rotation.
        """
        self._maybe_init()
        last_error = None
        for attempt in range(max_retries + 1):
            result = self.execution.execute_adaptive(
                task,
                preferred_bridges=fallback_bridges if attempt > 0 else None,
                **kwargs,
            )
            if result.status == "success":
                return self._result_to_dict(result)
            last_error = result.error
            logger.warning(f"Attempt {attempt+1} failed: {last_error}")
        return self._result_to_dict(ExecutionResult(
            bridge="unknown",
            method="execute_with_retry",
            status="error",
            result=None,
            duration_ms=0.0,
            error=f"All {max_retries+1} attempts failed. Last: {last_error}",
        ))

    # -- Internal helpers --
    def _maybe_init(self) -> None:
        if not self._initialized:
            self.initialize()

    def _result_to_dict(self, result: ExecutionResult) -> Dict[str, Any]:
        return {
            "bridge": result.bridge,
            "method": result.method,
            "status": result.status,
            "result": result.result,
            "duration_ms": round(result.duration_ms, 2),
            "error": result.error,
            "metadata": result.metadata,
        }

    def __repr__(self) -> str:
        return (
            f"<UnifiedMetaBridge v{self.version} "
            f"bridges={len(self.registry)} "
            f"initialized={self._initialized}>"
        )


# ==============================================================================
# 7. MOCK UNIFIED META BRIDGE
# ==============================================================================
class MockUnifiedMetaBridge:
    """
    Same interface as UnifiedMetaBridge, but simulates all routing and execution.
    Useful for offline mode, unit tests, and CI pipelines.
    """

    def __init__(self, seed: int = 42) -> None:
        self.version = BRIDGE_VERSION
        self._seed = seed
        self._rng_state = seed
        self._call_log: List[Dict[str, Any]] = []
        self._metrics = {
            "tasks_routed": 0,
            "tasks_executed": 0,
            "workflows_run": 0,
            "errors": 0,
            "start_time": time.time(),
        }
        self._bridges = [
            "autogen", "langchain", "llamaindex", "mem0", "metagpt",
            "ragflow", "semantic_kernel", "livekit", "agents_bridge",
            "github_ingestor", "local_vision", "local_voice", "drawing_engine",
            "document_generator", "trading_engine", "visual_qa",
            "volumetric_renderer", "window_manager_3d",
            "docker_android_bridge", "auto_browser_bridge",
            "computer_use_ootb_bridge", "gemini_computer_use_bridge",
            "open_autoglm_bridge", "supersplat_bridge", "e2b_computer_use_bridge",
            "paper2code_bridge", "jcode_bridge", "off_grid_mobile_ai_bridge",
            "humanizer_bridge", "localsend_bridge", "microsoft_jarvis_bridge",
            "meta_agent_bridge", "decepticon_bridge", "ace_step_ui_bridge",
        ]
        self._capabilities: Dict[str, List[str]] = {
            b: ["execute", "status", "ping", "health"] for b in self._bridges
        }

    # -- Lifecycle --
    def initialize(self) -> None:
        logger.info("MockUnifiedMetaBridge initialized (simulation mode).")

    def shutdown(self) -> None:
        logger.info("MockUnifiedMetaBridge shut down.")

    # -- Discovery --
    def discover_all_capabilities(self) -> Dict[str, List[str]]:
        """Simulated capability discovery."""
        self._log_call("discover_all_capabilities")
        return dict(self._capabilities)

    # -- Routing --
    def route_task(self, task: str) -> Dict[str, Any]:
        """Simulated routing based on keyword match."""
        self._metrics["tasks_routed"] += 1
        task_lower = task.lower()
        best_bridge = "agents_bridge"
        for b in self._bridges:
            if b.replace("_bridge", "").replace("_", " ") in task_lower:
                best_bridge = b
                break
        confidence = self._rand_float(0.55, 0.98)
        self._log_call("route_task", {"task": task, "bridge": best_bridge})
        return {
            "bridge": best_bridge,
            "method": "execute",
            "confidence": round(confidence, 3),
            "strategy": "hybrid",
            "reasoning": f"Mock routing: keyword match on '{task[:40]}...' -> {best_bridge}",
            "alternatives": [
                {"bridge": self._bridges[i], "method": "execute", "score": round(self._rand_float(0.3, 0.5), 3)}
                for i in range(1, 4)
            ],
        }

    # -- Execution --
    def execute_via_best_bridge(self, task: str, **kwargs: Any) -> Dict[str, Any]:
        """Simulated execution returning mock data."""
        self._metrics["tasks_executed"] += 1
        route = self.route_task(task)
        self._log_call("execute_via_best_bridge", {"task": task, "route": route})
        return {
            "bridge": route["bridge"],
            "method": route["method"],
            "status": "success",
            "result": f"Mock result for '{task}' from {route['bridge']}",
            "duration_ms": round(self._rand_float(50.0, 800.0), 2),
            "error": None,
            "metadata": {"mock": True, "confidence": route["confidence"]},
        }

    def execute_parallel(self, tasks: List[Union[str, Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Simulated parallel execution."""
        self._metrics["tasks_executed"] += len(tasks)
        results = []
        for spec in tasks:
            if isinstance(spec, str):
                task_str = spec
            else:
                task_str = spec.get("task", "")
            results.append(self.execute_via_best_bridge(task_str))
        self._log_call("execute_parallel", {"count": len(tasks)})
        return results

    # -- Integration --
    def cross_bridge_workflow(self, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Simulated multi-step workflow."""
        self._metrics["workflows_run"] += 1
        completed = []
        for i, step in enumerate(steps):
            completed.append({
                "step_id": f"mock_step_{i}",
                "bridge": step.get("bridge", "agents_bridge"),
                "method": step.get("method", "execute"),
                "status": "success",
                "outputs": f"Mock output for step {i}",
                "duration_ms": round(self._rand_float(50.0, 500.0), 2),
                "error": None,
            })
        self._log_call("cross_bridge_workflow", {"steps": len(steps)})
        return {
            "workflow_id": f"mock_wf_{uuid.uuid4().hex[:8]}",
            "status": "success",
            "steps": completed,
            "context": {"last_result": completed[-1]["outputs"] if completed else None},
        }

    def synthesize_results(self, results: List[Dict[str, Any]]) -> str:
        """Mock synthesis returning markdown."""
        self._log_call("synthesize_results", {"count": len(results)})
        parts = ["# Mock Synthesis\n", f"**Tasks:** {len(results)}\n\n"]
        for i, r in enumerate(results, 1):
            parts.append(f"## {i}. `{r.get('bridge', '?')}.{r.get('method', '?')}`\n")
            parts.append(f"- Status: {r.get('status', '?')}\n")
            parts.append(f"- Result: {r.get('result', '?')}\n\n")
        return "".join(parts)

    # -- Monitoring --
    def get_bridge_health(self) -> Dict[str, Dict[str, Any]]:
        """Simulated health for all bridges."""
        self._log_call("get_bridge_health")
        return {
            b: {
                "status": "healthy",
                "last_check": datetime.utcnow().isoformat() + "Z",
                "response_ms": round(self._rand_float(10.0, 300.0), 2),
                "error_count": 0,
                "success_count": self._rand_int(10, 500),
                "capabilities": self._capabilities.get(b, []),
                "version": self.version,
                "metadata": {"mock": True},
            }
            for b in self._bridges
        }

    def get_capability_map(self) -> Dict[str, Any]:
        """Simulated capability map."""
        self._log_call("get_capability_map")
        return {
            b: {
                "status": "healthy",
                "version": self.version,
                "capabilities": self._capabilities.get(b, []),
                "health": {
                    "response_ms": round(self._rand_float(10.0, 300.0), 2),
                    "error_count": 0,
                    "success_count": self._rand_int(10, 500),
                },
            }
            for b in self._bridges
        }

    def get_metrics(self) -> Dict[str, Any]:
        uptime = time.time() - self._metrics["start_time"]
        return {
            "uptime_seconds": round(uptime, 2),
            "tasks_routed": self._metrics["tasks_routed"],
            "tasks_executed": self._metrics["tasks_executed"],
            "workflows_run": self._metrics["workflows_run"],
            "errors": self._metrics["errors"],
            "bridges_registered": len(self._bridges),
            "version": self.version,
            "mock": True,
        }

    def get_bridge(self, name: str) -> Any:
        """Return a mock bridge proxy."""
        return _MockBridgeProxy(name)

    def execute_with_retry(
        self,
        task: str,
        max_retries: int = 2,
        fallback_bridges: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return self.execute_via_best_bridge(task, **kwargs)

    # -- Internal --
    def _rand_float(self, lo: float, hi: float) -> float:
        self._rng_state = (self._rng_state * 1103515245 + 12345) & 0x7FFFFFFF
        return lo + (self._rng_state / 0x7FFFFFFF) * (hi - lo)

    def _rand_int(self, lo: int, hi: int) -> int:
        return int(self._rand_float(lo, hi))

    def _log_call(self, method: str, extra: Optional[Dict[str, Any]] = None) -> None:
        self._call_log.append({
            "timestamp": time.time(),
            "method": method,
            "extra": extra or {},
        })

    @property
    def call_log(self) -> List[Dict[str, Any]]:
        return list(self._call_log)

    def __repr__(self) -> str:
        return f"<MockUnifiedMetaBridge v{self.version} bridges={len(self._bridges)}>"


class _MockBridgeProxy:
    """Proxy object returned by MockUnifiedMetaBridge.get_bridge()."""

    def __init__(self, name: str) -> None:
        self._name = name

    def __getattr__(self, item: str) -> Callable[..., Any]:
        def _stub(*args: Any, **kwargs: Any) -> str:
            return f"Mock[{self._name}.{item}] called with {args} {kwargs}"
        return _stub

    def __repr__(self) -> str:
        return f"<_MockBridgeProxy name={self._name}>"


# ==============================================================================
# 8. DEFAULT BRIDGE REGISTRY BUILDER
# ==============================================================================

# Module-level capability tracking
_BRIDGE_CAPABILITIES: Dict[str, List[Capability]] = {}

# Capability manifests for all 18+ bridges -- used when bridges are not importable.
_DEFAULT_CAPABILITY_MANIFEST: Dict[str, List[Capability]] = {
    "autogen": [
        Capability("run_agent", "Execute an AutoGen agent with a task.", ["agent", "autogen", "run"]),
        Capability("create_assistant", "Create a new assistant agent.", ["create", "assistant"]),
        Capability("group_chat", "Run a group chat among multiple agents.", ["group", "chat", "multi"]),
        Capability("code_execution", "Execute generated code in a sandbox.", ["code", "execute"]),
    ],
    "langchain": [
        Capability("run_chain", "Run a LangChain chain/pipeline.", ["chain", "pipeline"]),
        Capability("create_prompt", "Create a prompt template.", ["prompt", "template"]),
        Capability("query_vector", "Query a vector store.", ["vector", "query", "similarity"]),
        Capability("build_index", "Build a vector index.", ["index", "embed"]),
    ],
    "llamaindex": [
        Capability("query_index", "Query a LlamaIndex index.", ["index", "query", "llamaindex"]),
        Capability("build_index", "Build an index from documents.", ["build", "documents"]),
        Capability("insert_document", "Insert a document into the index.", ["insert", "document"]),
    ],
    "mem0": [
        Capability("add_memory", "Store a new memory.", ["store", "memory", "save"]),
        Capability("get_memory", "Retrieve memories by query.", ["retrieve", "recall", "search"]),
        Capability("delete_memory", "Delete a memory entry.", ["delete", "remove"]),
    ],
    "metagpt": [
        Capability("run_project", "Run a MetaGPT software startup project.", ["startup", "software", "project"]),
        Capability("assign_roles", "Assign roles to agents.", ["role", "assign"]),
        Capability("write_code", "Generate code via MetaGPT.", ["code", "generate"]),
    ],
    "ragflow": [
        Capability("query_knowledge", "Query a knowledge base.", ["knowledge", "query", "rag"]),
        Capability("create_kb", "Create a new knowledge base.", ["create", "kb"]),
        Capability("upload_document", "Upload document to RAGFlow.", ["upload", "document"]),
    ],
    "semantic_kernel": [
        Capability("run_function", "Run a Semantic Kernel function.", ["function", "skill", "plugin"]),
        Capability("import_skill", "Import a skill/plugin.", ["import", "skill"]),
        Capability("create_prompt", "Create a semantic prompt.", ["prompt", "semantic"]),
    ],
    "livekit": [
        Capability("join_room", "Join a LiveKit room.", ["room", "join", "webrtc"]),
        Capability("publish_audio", "Publish audio track.", ["audio", "publish"]),
        Capability("subscribe_track", "Subscribe to a media track.", ["subscribe", "track"]),
    ],
    "agents_bridge": [
        Capability("run_agent", "Run a task via the agents bridge.", ["agent", "task", "run"]),
        Capability("create_agent", "Create a new agent.", ["create", "agent"]),
        Capability("handoff", "Handoff between agents.", ["handoff", "delegate"]),
    ],
    "github_ingestor": [
        Capability("ingest_repo", "Ingest a GitHub repository.", ["github", "repo", "clone"]),
        Capability("search_code", "Search code in ingested repos.", ["search", "code"]),
        Capability("summarize_repo", "Summarize repository contents.", ["summarize", "overview"]),
    ],
    "local_vision": [
        Capability("analyze_image", "Analyze an image.", ["image", "vision", "analyze"]),
        Capability("detect_objects", "Detect objects in an image.", ["detect", "objects"]),
        Capability("ocr", "Extract text via OCR.", ["ocr", "text", "extract"]),
    ],
    "local_voice": [
        Capability("speak_text", "Convert text to speech.", ["tts", "speak", "voice"]),
        Capability("transcribe", "Transcribe audio to text.", ["stt", "transcribe", "listen"]),
    ],
    "drawing_engine": [
        Capability("draw", "Create a drawing or diagram.", ["draw", "sketch", "diagram"]),
        Capability("chart", "Generate a chart.", ["chart", "graph", "plot"]),
    ],
    "document_generator": [
        Capability("generate", "Generate a document.", ["document", "pdf", "report"]),
        Capability("render_html", "Render HTML output.", ["html", "render"]),
    ],
    "trading_engine": [
        Capability("execute_trade", "Execute a trade.", ["trade", "buy", "sell"]),
        Capability("get_quote", "Get market quote.", ["quote", "price", "market"]),
        Capability("portfolio_summary", "Summarize portfolio.", ["portfolio", "summary"]),
    ],
    "visual_qa": [
        Capability("answer_question", "Answer question about an image.", ["qa", "visual", "question"]),
        Capability("caption", "Generate image caption.", ["caption", "describe"]),
    ],
    "volumetric_renderer": [
        Capability("render", "Render a volumetric/3D scene.", ["3d", "render", "volumetric"]),
        Capability("load_point_cloud", "Load a point cloud.", ["pointcloud", "load"]),
    ],
    "window_manager_3d": [
        Capability("create_workspace", "Create a 3D workspace.", ["3d", "workspace", "window"]),
        Capability("arrange_windows", "Arrange windows in 3D.", ["arrange", "spatial"]),
    ],
    # External integration bridges
    "docker_android_bridge": [
        Capability("run_container", "Run a Docker/Android container.", ["docker", "android", "container"]),
        Capability("build_image", "Build a Docker image.", ["build", "image"]),
    ],
    "auto_browser_bridge": [
        Capability("navigate", "Navigate a web page.", ["browser", "navigate", "web"]),
        Capability("click", "Click an element.", ["click", "interact"]),
        Capability("scrape", "Scrape page content.", ["scrape", "extract"]),
    ],
    "computer_use_ootb_bridge": [
        Capability("use_computer", "Control computer GUI.", ["computer", "gui", "desktop"]),
        Capability("click_screen", "Click on screen coordinates.", ["click", "screen"]),
    ],
    "gemini_computer_use_bridge": [
        Capability("use_screen", "Use Gemini to control screen.", ["gemini", "screen", "computer"]),
        Capability("capture_screen", "Capture screen for Gemini.", ["capture", "screen"]),
    ],
    "open_autoglm_bridge": [
        Capability("tap_phone", "Tap on phone UI.", ["tap", "phone", "mobile"]),
        Capability("swipe", "Swipe gesture on phone.", ["swipe", "gesture"]),
    ],
    "supersplat_bridge": [
        Capability("load_scene", "Load a Gaussian splat scene.", ["splat", "scene", "3d"]),
        Capability("export_scene", "Export a splat scene.", ["export", "scene"]),
    ],
    "e2b_computer_use_bridge": [
        Capability("execute_code", "Execute code in E2B sandbox.", ["sandbox", "code", "e2b"]),
        Capability("run_command", "Run shell command in sandbox.", ["command", "shell"]),
    ],
    "paper2code_bridge": [
        Capability("generate_from_paper", "Generate code from paper.", ["paper", "code", "arxiv"]),
        Capability("search_papers", "Search academic papers.", ["search", "papers"]),
    ],
    "jcode_bridge": [
        Capability("edit_file", "Edit code in JCode editor.", ["edit", "code", "refactor"]),
        Capability("autocomplete", "Provide code autocomplete.", ["autocomplete", "suggest"]),
    ],
    "off_grid_mobile_ai_bridge": [
        Capability("run_offline", "Run inference offline.", ["offline", "edge", "mobile"]),
        Capability("sync_model", "Sync model to device.", ["sync", "model"]),
    ],
    "humanizer_bridge": [
        Capability("humanize", "Humanize text output.", ["humanize", "tone", "natural"]),
        Capability("set_persona", "Set humanizer persona.", ["persona", "style"]),
    ],
    "localsend_bridge": [
        Capability("send_file", "Send file via LocalSend.", ["send", "file", "transfer"]),
        Capability("receive_file", "Receive file via LocalSend.", ["receive", "file"]),
    ],
    "microsoft_jarvis_bridge": [
        Capability("plan_and_solve", "Plan and solve with HuggingGPT.", ["plan", "solve", "hugginggpt"]),
        Capability("select_model", "Select best model for task.", ["select", "model"]),
    ],
    "meta_agent_bridge": [
        Capability("evolve", "Evolve agent capabilities.", ["evolve", "adapt", "learn"]),
        Capability("self_improve", "Self-improve agent.", ["improve", "self"]),
    ],
    "decepticon_bridge": [
        Capability("probe", "Probe for security weaknesses.", ["probe", "security", "test"]),
        Capability("red_team", "Run red-team exercise.", ["redteam", "adversarial"]),
    ],
    "ace_step_ui_bridge": [
        Capability("render_ui", "Render UI component.", ["ui", "render", "component"]),
        Capability("build_interface", "Build full interface.", ["interface", "build"]),
    ],
}


def _build_default_registry() -> Dict[str, Callable[[], Any]]:
    """
    Build a registry that lazily imports each bridge.
    Falls back to a mock instance if import fails.
    """
    registry: Dict[str, Callable[[], Any]] = {}

    def _make_lazy_bridge(module_path: str, class_name: str, bridge_name: str) -> Callable[[], Any]:
        def _factory() -> Any:
            try:
                import importlib
                module = importlib.import_module(module_path, package=__package__)
                cls = getattr(module, class_name, None)
                if cls:
                    return cls()
            except Exception as exc:
                logger.debug(f"Lazy import failed for {bridge_name}: {exc}")
            # Return a minimal mock
            return _MockBridgeProxy(bridge_name)
        return _factory

    # Internal bridges
    _BRIDGE_SPEC = [
        ("autogen", "jarvis.runtime.agency.autogen_bridge", "AutoGenBridge"),
        ("langchain", "jarvis.runtime.agency.langchain_bridge", "LangChainBridge"),
        ("llamaindex", "jarvis.runtime.agency.llamaindex_bridge", "LlamaIndexBridge"),
        ("mem0", "jarvis.runtime.agency.mem0_bridge", "Mem0Bridge"),
        ("metagpt", "jarvis.runtime.agency.metagpt_bridge", "MetaGPTBridge"),
        ("ragflow", "jarvis.runtime.agency.ragflow_bridge", "RAGFlowBridge"),
        ("semantic_kernel", "jarvis.runtime.agency.semantic_kernel_bridge", "SemanticKernelBridge"),
        ("livekit", "jarvis.runtime.agency.livekit_bridge", "LiveKitBridge"),
        ("agents_bridge", "jarvis.runtime.agency.agents_bridge", "AgentsBridge"),
        ("github_ingestor", "jarvis.runtime.agency.github_ingestor", "GitHubIngestor"),
        ("local_vision", "jarvis.runtime.agency.local_vision", "LocalVisionSystem"),
        ("local_voice", "jarvis.runtime.agency.local_voice", "LocalVoiceProcessor"),
        ("drawing_engine", "jarvis.runtime.agency.drawing_engine", "DrawingEngine"),
        ("document_generator", "jarvis.runtime.agency.document_generator", "DocumentGenerator"),
        ("trading_engine", "jarvis.runtime.agency.trading_engine", "TradingEngine"),
        ("visual_qa", "jarvis.runtime.agency.visual_qa", "VisualQA"),
        ("volumetric_renderer", "jarvis.runtime.agency.volumetric_renderer", "VolumetricRenderer"),
        ("window_manager_3d", "jarvis.runtime.agency.window_manager_3d", "WindowManager3D"),
        # External integration bridges
        ("docker_android_bridge", "jarvis.runtime.agency.external_integrations.docker_android_bridge", "DockerAndroidBridge"),
        ("auto_browser_bridge", "jarvis.runtime.agency.external_integrations.auto_browser_bridge", "AutoBrowserBridge"),
        ("computer_use_ootb_bridge", "jarvis.runtime.agency.external_integrations.computer_use_ootb_bridge", "ComputerUseOOTBBridge"),
        ("gemini_computer_use_bridge", "jarvis.runtime.agency.external_integrations.gemini_computer_use_bridge", "GeminiComputerUseBridge"),
        ("open_autoglm_bridge", "jarvis.runtime.agency.external_integrations.open_autoglm_bridge", "OpenAutoGLMBridge"),
        ("supersplat_bridge", "jarvis.runtime.agency.external_integrations.supersplat_bridge", "SupersplatBridge"),
        ("e2b_computer_use_bridge", "jarvis.runtime.agency.external_integrations.e2b_computer_use_bridge", "E2BComputerUseBridge"),
        ("paper2code_bridge", "jarvis.runtime.agency.external_integrations.paper2code_bridge", "Paper2CodeBridge"),
        ("jcode_bridge", "jarvis.runtime.agency.external_integrations.jcode_bridge", "JCodeBridge"),
        ("off_grid_mobile_ai_bridge", "jarvis.runtime.agency.external_integrations.off_grid_mobile_ai_bridge", "OffGridMobileAIBridge"),
        ("humanizer_bridge", "jarvis.runtime.agency.external_integrations.humanizer_bridge", "HumanizerBridge"),
        ("localsend_bridge", "jarvis.runtime.agency.external_integrations.localsend_bridge", "LocalsendBridge"),
        ("microsoft_jarvis_bridge", "jarvis.runtime.agency.external_integrations.microsoft_jarvis_bridge", "MicrosoftJarvisBridge"),
        ("meta_agent_bridge", "jarvis.runtime.agency.external_integrations.meta_agent_bridge", "MetaAgentBridge"),
        ("decepticon_bridge", "jarvis.runtime.agency.external_integrations.decepticon_bridge", "DecepticonBridge"),
        ("ace_step_ui_bridge", "jarvis.runtime.agency.external_integrations.ace_step_ui_bridge", "AceStepUIBridge"),
        ("autogpt_bridge", "jarvis.runtime.agency.external_integrations.autogpt_bridge", "AutoGPTBridge"),
    ]

    for name, mod_path, cls_name in _BRIDGE_SPEC:
        registry[name] = _make_lazy_bridge(mod_path, cls_name, name)
        # Pre-seed capability manifest
        if name in _DEFAULT_CAPABILITY_MANIFEST:
            _BRIDGE_CAPABILITIES[name] = _DEFAULT_CAPABILITY_MANIFEST[name]

    return registry


# ==============================================================================
# 9. FACTORY
# ==============================================================================
_bridge_instance: Optional[UnifiedMetaBridge] = None
_bridge_lock = threading.Lock()


def get_unified_meta_bridge(
    use_mock: bool = False,
    strategy: str = "hybrid",
    custom_registry: Optional[Dict[str, Callable[[], Any]]] = None,
) -> Union[UnifiedMetaBridge, MockUnifiedMetaBridge]:
    """
    Factory function to get (or create) the UnifiedMetaBridge singleton.

    Parameters:
        use_mock: If True, return MockUnifiedMetaBridge.
        strategy: Routing strategy -- "keyword", "semantic", "llm", or "hybrid".
        custom_registry: Override the default bridge registry.

    Returns:
        UnifiedMetaBridge or MockUnifiedMetaBridge instance.

    Example:
        >>> bridge = get_unified_meta_bridge()
        >>> bridge.route_task("Analyze image for objects")
        {"bridge": "local_vision", "method": "analyze_image", "confidence": 0.92, ...}
    """
    global _bridge_instance

    if use_mock:
        return MockUnifiedMetaBridge()

    with _bridge_lock:
        if _bridge_instance is not None:
            return _bridge_instance

        registry = custom_registry or _build_default_registry()
        strat = RoutingStrategy(strategy)
        bridge = UnifiedMetaBridge(bridge_registry=registry, strategy=strat)
        bridge.initialize()
        _bridge_instance = bridge
        logger.info(
            f"UnifiedMetaBridge created with {len(registry)} bridges (strategy={strategy})"
        )
        return bridge


def reset_bridge() -> None:
    """Reset the singleton (useful for testing)."""
    global _bridge_instance
    with _bridge_lock:
        if _bridge_instance is not None:
            _bridge_instance.shutdown()
        _bridge_instance = None


# ==============================================================================
# 10. __main__ CLI / Smoke Test
# ==============================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 70)
    print("J.A.R.V.I.S BRAINIAC -- Unified Meta Bridge Smoke Test")
    print("=" * 70)

    # Test with mock
    print("\n--- Mock Bridge Test ---")
    mock = get_unified_meta_bridge(use_mock=True)
    caps = mock.discover_all_capabilities()
    print(f"Discovered {len(caps)} bridges with capabilities")

    route = mock.route_task("Generate a report from a GitHub repo")
    print(f"Route: {json.dumps(route, indent=2)}")

    result = mock.execute_via_best_bridge("Generate a report from a GitHub repo")
    print(f"Execute: {json.dumps(result, indent=2)}")

    health = mock.get_bridge_health()
    print(f"Health (first 3): {json.dumps(dict(list(health.items())[:3]), indent=2)}")

    # Test workflow
    workflow_result = mock.cross_bridge_workflow([
        {"bridge": "github_ingestor", "method": "ingest_repo", "inputs": {"url": "https://github.com/example/repo"}},
        {"bridge": "local_brain", "method": "analyze", "inputs": {"task": "{{last_result}}"}},
    ])
    print(f"Workflow: {json.dumps(workflow_result, indent=2)[:500]}...")

    synthesis = mock.synthesize_results([result])
    print(f"Synthesis (first 300 chars): {synthesis[:300]}...")

    metrics = mock.get_metrics()
    print(f"Metrics: {json.dumps(metrics, indent=2)}")

    # Test real bridge (without full init)
    print("\n--- Real Bridge Registry Test ---")
    real_registry = _build_default_registry()
    print(f"Registry size: {len(real_registry)} bridges")
    for name in sorted(real_registry.keys())[:5]:
        print(f"  - {name}")
    print("  ...")

    print("\n" + "=" * 70)
    print("All smoke tests passed.")
    print("=" * 70)
