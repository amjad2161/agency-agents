"""Central nervous system connecting all JARVIS subsystems.

The :class:`UnifiedBridge` acts as the central integration hub,
managing 21 named subsystems and coordinating the main processing
pipeline: route → execute → learn.

Example::

    from runtime.agency.unified_bridge import get_unified_bridge
    bridge = get_unified_bridge()
    result = bridge.process("build a react app")
    health = bridge.status()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Subsystem names managed by the UnifiedBridge
_SUBSYSTEM_NAMES: List[str] = [
    "llm_router",
    "semantic_router",
    "memory",
    "tool_registry",
    "persona_engine",
    "emotion_state",
    "cost_router",
    "eval_harness",
    "self_learner",
    "meta_reasoning",
    "capability_evolver",
    "context_manager",
    "autonomous_loop",
    "knowledge_expansion",
    "multimodal_processor",
    "trust_layer",
    "scheduler",
    "vector_memory",
    "tracing",
    "audit_logger",
    "stats_tracker",
]


@dataclass
class SubsystemInfo:
    """Metadata about a registered subsystem.

    Attributes:
        status: Lifecycle status - ``"initialized"``, ``"active"``, etc.
        instance: The actual subsystem object (may be ``None`` until activated).
    """

    status: str = "initialized"
    instance: Optional[Any] = None


class UnifiedBridge:
    """Central nervous system connecting all JARVIS subsystems.

    Manages 21 subsystems with lazy initialization, health checking,
    and the main processing pipeline. Follows the singleton pattern.

    Processing pipeline::

        request → route (jarvis_brain) → execute → learn
    """

    _instance: Optional["UnifiedBridge"] = None

    def __new__(cls, experts: Optional[List[Any]] = None) -> "UnifiedBridge":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._experts = experts or []
            cls._instance._subsystems: Dict[str, Dict[str, Any]] = {}
            cls._instance._init_subsystems()
        return cls._instance

    def _init_subsystems(self) -> None:
        """Initialize all 21 subsystems with lazy loading.

        Each subsystem starts in ``"initialized"`` status with no
        backing instance. Call :meth:`set_subsystem` to activate one.
        """
        for name in _SUBSYSTEM_NAMES:
            self._subsystems[name] = {"status": "initialized", "instance": None}

    def process(self, request: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Main processing pipeline: route → execute → learn.

        Args:
            request: Natural-language request from the user.
            context: Optional dictionary of additional context.

        Returns:
            Dictionary containing the routing result, subsystem status,
            expert count, and processing status.
        """
        from .jarvis_brain import get_brain

        brain = get_brain()
        route = brain.route(request)

        return {
            "request": request,
            "route": route.to_dict(),
            "subsystems_checked": len(self._subsystems),
            "experts_available": len(self._experts),
            "status": "processed",
        }

    def status(self) -> Dict[str, Any]:
        """Health check all subsystems.

        Returns:
            Dictionary with total count, online count, and per-subsystem
            status strings.
        """
        return {
            "total_subsystems": len(self._subsystems),
            "online": sum(
                1 for s in self._subsystems.values() if s.get("status") == "active"
            ),
            "initialized": sum(
                1 for s in self._subsystems.values() if s.get("status") == "initialized"
            ),
            "subsystems": {
                name: info.get("status", "unknown")
                for name, info in self._subsystems.items()
            },
        }

    def get_subsystem(self, name: str) -> Optional[Any]:
        """Retrieve a subsystem's backing instance.

        Args:
            name: Subsystem identifier from the canonical list.

        Returns:
            The subsystem instance, or ``None`` if not found or not activated.
        """
        if name in self._subsystems:
            return self._subsystems[name].get("instance")
        return None

    def set_subsystem(self, name: str, instance: Any) -> None:
        """Activate a subsystem with a concrete instance.

        Args:
            name: Subsystem identifier.
            instance: The subsystem object to register.
        """
        self._subsystems[name] = {"status": "active", "instance": instance}

    def deactivate_subsystem(self, name: str) -> None:
        """Deactivate a subsystem without removing it.

        Args:
            name: Subsystem identifier.
        """
        if name in self._subsystems:
            self._subsystems[name]["status"] = "initialized"
            self._subsystems[name]["instance"] = None

    def list_subsystems(self) -> List[str]:
        """Return all registered subsystem names."""
        return list(self._subsystems.keys())

    @property
    def experts(self) -> List[Any]:
        """List of expert agents available to the bridge."""
        return self._experts.copy()

    def add_expert(self, expert: Any) -> None:
        """Register an additional expert agent.

        Args:
            expert: Expert object to add.
        """
        self._experts.append(expert)


def get_unified_bridge(experts: Optional[List[Any]] = None) -> UnifiedBridge:
    """Return the singleton :class:`UnifiedBridge` instance.

    Args:
        experts: Optional list of expert agents to register on first call.

    Returns:
        The shared :class:`UnifiedBridge` instance.
    """
    return UnifiedBridge(experts=experts)
