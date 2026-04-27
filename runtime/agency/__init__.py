"""Agency runtime: orchestrate the persona library as runnable skills.

The package is intentionally light at import time — heavy modules
(httpx, anthropic, sqlite vector store) are loaded lazily through
the getters below so a `from agency import ...` for one piece doesn't
drag in the whole runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__version__ = "0.1.0"


if TYPE_CHECKING:
    # Type-only imports so callers get autocomplete without paying the
    # import cost at runtime. The actual instances come from the
    # getters below.
    from .autonomous_loop import AutonomousLoop
    from .capability_evolver import CapabilityEvolver
    from .context_manager import ContextManager
    from .knowledge_expansion import KnowledgeExpansion
    from .meta_reasoner import MetaReasoningEngine
    from .multimodal import MultimodalProcessor
    from .self_learner_engine import SelfLearnerEngine


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
_unified_bridge: "object | None" = None


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


def get_unified_bridge() -> object:
    """Composite bridge that exposes every capability through one
    handle — useful for callers that want a single `bridge.something`
    surface without juggling seven imports.

    The bridge is built lazily so importing the package is still cheap.
    """
    global _unified_bridge
    if _unified_bridge is not None:
        return _unified_bridge

    class _UnifiedBridge:
        def __init__(self) -> None:
            self.self_learner = get_self_learner()
            self.meta_reasoner = get_meta_reasoner()
            self.capability_evolver = get_capability_evolver()
            self.context_manager = get_context_manager()
            self.autonomous_loop = get_autonomous_loop()
            self.knowledge_expansion = get_knowledge_expansion()
            self.multimodal = get_multimodal_processor()

        def __repr__(self) -> str:
            return (
                "<UnifiedBridge "
                "self_learner+meta_reasoner+capability_evolver"
                "+context_manager+autonomous_loop+knowledge_expansion"
                "+multimodal>"
            )

    _unified_bridge = _UnifiedBridge()
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
]
