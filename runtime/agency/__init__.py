"""Agency runtime: orchestrate the persona library as runnable skills.

The package is intentionally light at import time — heavy modules
(httpx, anthropic, sqlite vector store) are loaded lazily through
the getters below so a `from agency import ...` for one piece doesn't
drag in the whole runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__version__ = "0.1.0"


if TYPE_CHECKING:
    # Type-only imports so callers get autocomplete without paying the
    # import cost at runtime. The actual instances come from the
    # getters below.
    from .aios_bridge import AIOSBridge
    from .autonomous_loop import AutonomousLoop
    from .capability_evolver import CapabilityEvolver
    from .context_manager import ContextManager
    from .evals import EvalSuite
    from .knowledge_expansion import KnowledgeExpansion
    from .llm_router import LLMRouter
    from .meta_reasoner import MetaReasoningEngine
    from .multi_agent import AgentPool
    from .multimodal import MultimodalProcessor
    from .prompt_optimizer import PromptCache
    from .sandbox import SubprocessSandbox
    from .self_learner_engine import SelfLearnerEngine
    from .semantic_router import SemanticRouter
    from .streaming import SSEEmitter
    from .tool_registry import ToolRegistry
    from .tracing import Tracer
    from .tui import JarvisConsole
    from .unified_bridge import UnifiedBridge
    from .vector_store import AgentMemory
    from .experts.expert_chemistry import ChemistryExpert
    from .experts.expert_clinician import ClinicianExpert
    from .experts.expert_contracts_law import ContractsLawExpert
    from .experts.expert_economics import EconomicsExpert
    from .experts.expert_mathematics import MathematicsExpert
    from .experts.expert_neuroscience import NeuroscienceExpert
    from .experts.expert_physics import PhysicsExpert
    from .experts.expert_psychology_cbt import PsychologyCBTExpert


# ---- Singletons -----------------------------------------------------------
# These are process-wide. Each holds either persistent state on disk
# (lessons, capabilities, knowledge) or process-local state (context,
# loop, reasoner, multimodal). Constructing them is cheap, but a
# singleton spares callers from re-loading the JSONL/JSON every time.

_self_learner: "SelfLearnerEngine | None" = None
_meta_reasoner: "MetaReasoningEngine | None" = None
_capability_evolver: "CapabilityEvolver | None" = None
_context_manager: "ContextManager | None" = None
_autonomous_loop: "AutonomousLoop | None" = None
_knowledge_expansion: "KnowledgeExpansion | None" = None
_multimodal_processor: "MultimodalProcessor | None" = None
_unified_bridge: "UnifiedBridge | None" = None
_llm_router: "LLMRouter | None" = None
_tracer: "Tracer | None" = None
_vector_memory: "AgentMemory | None" = None
_tool_registry: "ToolRegistry | None" = None
_eval_suite: "EvalSuite | None" = None
_semantic_router: "SemanticRouter | None" = None
_prompt_cache: "PromptCache | None" = None
_sandbox: "SubprocessSandbox | None" = None
_console: "JarvisConsole | None" = None
_agent_pool: "AgentPool | None" = None
_aios_bridge: "AIOSBridge | None" = None


def get_self_learner() -> "SelfLearnerEngine":
    global _self_learner
    if _self_learner is None:
        from .self_learner_engine import SelfLearnerEngine
        _self_learner = SelfLearnerEngine()
    return _self_learner


def get_meta_reasoner() -> "MetaReasoningEngine":
    global _meta_reasoner
    if _meta_reasoner is None:
        from .meta_reasoner import MetaReasoningEngine
        _meta_reasoner = MetaReasoningEngine()
    return _meta_reasoner


def get_capability_evolver() -> "CapabilityEvolver":
    global _capability_evolver
    if _capability_evolver is None:
        from .capability_evolver import CapabilityEvolver
        _capability_evolver = CapabilityEvolver()
    return _capability_evolver


def get_context_manager() -> "ContextManager":
    global _context_manager
    if _context_manager is None:
        from .context_manager import ContextManager
        _context_manager = ContextManager()
    return _context_manager


def get_autonomous_loop() -> "AutonomousLoop":
    global _autonomous_loop
    if _autonomous_loop is None:
        from .autonomous_loop import AutonomousLoop
        _autonomous_loop = AutonomousLoop()
    return _autonomous_loop


def get_knowledge_expansion() -> "KnowledgeExpansion":
    global _knowledge_expansion
    if _knowledge_expansion is None:
        from .knowledge_expansion import KnowledgeExpansion
        _knowledge_expansion = KnowledgeExpansion()
    return _knowledge_expansion


def get_multimodal_processor() -> "MultimodalProcessor":
    """Return the shared multimodal processor instance.

    `MultimodalProcessor` is instance-based and may carry pluggable OCR /
    transcription backends; the singleton lets callers configure those
    backends once and reuse the processor everywhere.
    """
    global _multimodal_processor
    if _multimodal_processor is None:
        from .multimodal import MultimodalProcessor
        _multimodal_processor = MultimodalProcessor()
    return _multimodal_processor


def get_llm_router() -> "LLMRouter":
    global _llm_router
    if _llm_router is None:
        from .llm_router import default_router
        _llm_router = default_router()
    return _llm_router


def get_tracer_singleton() -> "Tracer":
    global _tracer
    if _tracer is None:
        from .tracing import get_tracer as _gt
        _tracer = _gt()
    return _tracer


def get_vector_store() -> "AgentMemory":
    global _vector_memory
    if _vector_memory is None:
        from .vector_store import get_vector_store as _gv
        _vector_memory = _gv("tfidf")
    return _vector_memory


def get_tool_registry() -> "ToolRegistry":
    global _tool_registry
    if _tool_registry is None:
        from .tool_registry import get_registry as _gr
        _tool_registry = _gr()
    return _tool_registry


def get_streaming() -> "SSEEmitter":
    """``SSEEmitter`` is a stateless namespace — return the class itself."""
    from .streaming import SSEEmitter
    return SSEEmitter  # type: ignore[return-value]


def get_evals() -> "EvalSuite":
    global _eval_suite
    if _eval_suite is None:
        from .evals import EvalSuite
        _eval_suite = EvalSuite()
    return _eval_suite


def get_semantic_router() -> "SemanticRouter":
    global _semantic_router
    if _semantic_router is None:
        from .semantic_router import default_router as _ds
        _semantic_router = _ds()
    return _semantic_router


def get_prompt_optimizer() -> "PromptCache":
    global _prompt_cache
    if _prompt_cache is None:
        from .prompt_optimizer import PromptCache
        _prompt_cache = PromptCache()
    return _prompt_cache


def get_sandbox() -> "SubprocessSandbox":
    global _sandbox
    if _sandbox is None:
        from .sandbox import SubprocessSandbox
        _sandbox = SubprocessSandbox()
    return _sandbox


def get_console() -> "JarvisConsole":
    global _console
    if _console is None:
        from .tui import get_console as _gc
        _console = _gc()
    return _console


def get_multi_agent() -> "AgentPool":
    """Return a placeholder agent pool seeded with one no-op agent."""
    global _agent_pool
    if _agent_pool is None:
        from .multi_agent import AgentPool
        pool = AgentPool()
        pool.add_agent("default", lambda x: x)
        _agent_pool = pool
    return _agent_pool


def get_aios_bridge() -> "AIOSBridge":
    global _aios_bridge
    if _aios_bridge is None:
        from .aios_bridge import AIOSBridge
        _aios_bridge = AIOSBridge()
    return _aios_bridge


# ---- Domain expert getters (each module owns its own singleton) ----

def get_clinician() -> "ClinicianExpert":
    from .experts.expert_clinician import get_expert
    return get_expert()


def get_contracts_law() -> "ContractsLawExpert":
    from .experts.expert_contracts_law import get_expert
    return get_expert()


def get_mathematics() -> "MathematicsExpert":
    from .experts.expert_mathematics import get_expert
    return get_expert()


def get_physics() -> "PhysicsExpert":
    from .experts.expert_physics import get_expert
    return get_expert()


def get_psychology_cbt() -> "PsychologyCBTExpert":
    from .experts.expert_psychology_cbt import get_expert
    return get_expert()


def get_economics() -> "EconomicsExpert":
    from .experts.expert_economics import get_expert
    return get_expert()


def get_chemistry() -> "ChemistryExpert":
    from .experts.expert_chemistry import get_expert
    return get_expert()


def get_neuroscience() -> "NeuroscienceExpert":
    from .experts.expert_neuroscience import get_expert
    return get_expert()


def get_experts_dict() -> dict[str, Any]:
    """Convenience: all 8 domain experts in a dict keyed by DOMAIN."""
    return {
        "clinician": get_clinician(),
        "contracts_law": get_contracts_law(),
        "mathematics": get_mathematics(),
        "physics": get_physics(),
        "psychology_cbt": get_psychology_cbt(),
        "economics": get_economics(),
        "chemistry": get_chemistry(),
        "neuroscience": get_neuroscience(),
    }


def get_unified_bridge() -> "UnifiedBridge":
    """Fully wired bridge spanning every JARVIS subsystem."""
    global _unified_bridge
    if _unified_bridge is not None:
        return _unified_bridge
    from .unified_bridge import UnifiedBridge
    _unified_bridge = UnifiedBridge(
        llm_router=get_llm_router(),
        semantic_router=get_semantic_router(),
        memory=get_vector_store(),
        tool_registry=get_tool_registry(),
        tracer=get_tracer_singleton(),
        eval_suite=get_evals(),
        console=get_console(),
        self_learner=get_self_learner(),
        meta_reasoner=get_meta_reasoner(),
        context_manager=get_context_manager(),
        knowledge_expansion=get_knowledge_expansion(),
        multimodal=get_multimodal_processor(),
        aios_bridge=get_aios_bridge(),
        experts=get_experts_dict(),
    )
    return _unified_bridge


__all__ = [
    "__version__",
    "get_self_learner",
    "get_meta_reasoner",
    "get_capability_evolver",
    "get_context_manager",
    "get_autonomous_loop",
    "get_knowledge_expansion",
    "get_multimodal_processor",
    "get_unified_bridge",
    "get_llm_router",
    "get_tracer_singleton",
    "get_vector_store",
    "get_tool_registry",
    "get_streaming",
    "get_evals",
    "get_semantic_router",
    "get_prompt_optimizer",
    "get_sandbox",
    "get_console",
    "get_multi_agent",
    "get_aios_bridge",
    "get_clinician",
    "get_contracts_law",
    "get_mathematics",
    "get_physics",
    "get_psychology_cbt",
    "get_economics",
    "get_chemistry",
    "get_neuroscience",
    "get_experts_dict",
]
