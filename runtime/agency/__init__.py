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
    from .amjad_memory import AmjadMemory
    from .autonomous_loop import AutonomousLoop
    from .capability_evolver import CapabilityEvolver
    from .character_state import CharacterState
    from .context_manager import ContextManager
    from .knowledge_expansion import KnowledgeExpansion
    from .meta_reasoner import MetaReasoningEngine
    from .multimodal import MultimodalProcessor
    from .persona_engine import PersonaEngine
    from .self_learner_engine import SelfLearnerEngine


# ---- Singletons -----------------------------------------------------------

_persona_engine: "PersonaEngine | None" = None
_character_state: "CharacterState | None" = None
_amjad_memory: "AmjadMemory | None" = None
_self_learner: "SelfLearnerEngine | None" = None
_meta_reasoner: "MetaReasoningEngine | None" = None
_capability_evolver: "CapabilityEvolver | None" = None
_context_manager: "ContextManager | None" = None
_autonomous_loop: "AutonomousLoop | None" = None
_knowledge_expansion: "KnowledgeExpansion | None" = None
_multimodal_processor: "MultimodalProcessor | None" = None
_unified_bridge: "object | None" = None


def get_persona_engine() -> "PersonaEngine":
    global _persona_engine
    if _persona_engine is None:
        from .persona_engine import PersonaEngine
        _persona_engine = PersonaEngine()
    return _persona_engine


def get_character_state() -> "CharacterState":
    global _character_state
    if _character_state is None:
        from .character_state import CharacterState
        _character_state = CharacterState.get_instance()
    return _character_state


def get_amjad_memory() -> "AmjadMemory":
    global _amjad_memory
    if _amjad_memory is None:
        from .amjad_memory import AmjadMemory
        _amjad_memory = AmjadMemory()
    return _amjad_memory


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
    """Return the shared multimodal processor instance."""
    global _multimodal_processor
    if _multimodal_processor is None:
        from .multimodal import MultimodalProcessor
        _multimodal_processor = MultimodalProcessor()
    return _multimodal_processor


def get_unified_bridge() -> object:
    """Composite bridge exposing every capability through one handle.
    Includes JARVIS persona, character state, and Amjad memory.
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
            # JARVIS character system
            self.persona = get_persona_engine()
            self.character = get_character_state()
            self.memory = get_amjad_memory()

        def process(self, request: str, context: dict | None = None) -> dict:
            """Route request through JARVIS persona; inject persona_mode."""
            ctx = dict(context or {})
            mode = ctx.get("mode") or self.persona.detect_mode(request)
            raw_response = ctx.get("response", "")
            formatted = (
                self.persona.format_response(raw_response, mode)
                if raw_response
                else ""
            )
            self.character.record_interaction(
                domain=ctx.get("domain", "general")
            )
            ctx.update(
                {
                    "request": request,
                    "response": formatted or raw_response,
                    "persona_mode": mode,
                }
            )
            return ctx

        def __repr__(self) -> str:
            return (
                "<UnifiedBridge "
                "self_learner+meta_reasoner+capability_evolver"
                "+context_manager+autonomous_loop+knowledge_expansion"
                "+multimodal+persona+character+memory>"
            )

    _unified_bridge = _UnifiedBridge()
    return _unified_bridge


__all__ = [
    "__version__",
    "get_persona_engine",
    "get_character_state",
    "get_amjad_memory",
    "get_meta_reasoner",
    "get_capability_evolver",
    "get_context_manager",
    "get_autonomous_loop",
    "get_knowledge_expansion",
    "get_multimodal_processor",
    "get_unified_bridge",
]
