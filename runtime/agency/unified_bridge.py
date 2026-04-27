"""Unified Bridge — single handle exposing every JARVIS capability.

Wraps the lazy singletons in :mod:`agency` so callers can grab one
``UnifiedBridge`` object and reach the self-learner, meta reasoner,
capability evolver, context manager, autonomous loop, knowledge
expansion engine, and multimodal processor through one surface.

Also reports a unified ``status()`` snapshot of every subsystem — useful
for health checks, dashboards, and CLI inspection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SubsystemStatus:
    name: str
    ok: bool
    detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


class UnifiedBridge:
    """Composite handle to every JARVIS capability subsystem.

    Constructed lazily — only the singletons that are actually accessed
    are instantiated.  Calling ``status()`` is the cheapest way to
    confirm every subsystem can be brought up without raising.
    """

    def __init__(self) -> None:
        from . import (
            get_self_learner,
            get_meta_reasoner,
            get_capability_evolver,
            get_context_manager,
            get_autonomous_loop,
            get_knowledge_expansion,
            get_multimodal_processor,
        )

        self.self_learner = get_self_learner()
        self.meta_reasoner = get_meta_reasoner()
        self.capability_evolver = get_capability_evolver()
        self.context_manager = get_context_manager()
        self.autonomous_loop = get_autonomous_loop()
        self.knowledge_expansion = get_knowledge_expansion()
        self.multimodal = get_multimodal_processor()

    # ------------------------------------------------------------------
    # Status / introspection
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Return a structured health snapshot of every subsystem.

        Each subsystem reports ``ok`` + a small ``detail`` dict.  The
        bridge composes them under one envelope with a top-level
        ``ok`` (true if every subsystem is OK).
        """
        subsystems = [
            self._status_self_learner(),
            self._status_meta_reasoner(),
            self._status_capability_evolver(),
            self._status_context_manager(),
            self._status_autonomous_loop(),
            self._status_knowledge_expansion(),
            self._status_multimodal(),
        ]
        all_ok = all(s.ok for s in subsystems)
        return {
            "ok": all_ok,
            "subsystems": [s.to_dict() for s in subsystems],
            "count": len(subsystems),
        }

    def subsystem_names(self) -> list[str]:
        return [
            "self_learner",
            "meta_reasoner",
            "capability_evolver",
            "context_manager",
            "autonomous_loop",
            "knowledge_expansion",
            "multimodal",
        ]

    # ------------------------------------------------------------------
    # Per-subsystem health probes
    # ------------------------------------------------------------------

    def _status_self_learner(self) -> SubsystemStatus:
        try:
            n = len(self.self_learner.lessons)
            return SubsystemStatus(
                "self_learner", True, {"lessons": n, "path": str(self.self_learner.lessons_path)}
            )
        except Exception as exc:  # pragma: no cover - defensive
            return SubsystemStatus("self_learner", False, {"error": str(exc)})

    def _status_meta_reasoner(self) -> SubsystemStatus:
        try:
            steps = len(getattr(self.meta_reasoner, "_steps", []))
            return SubsystemStatus("meta_reasoner", True, {"steps_recorded": steps})
        except Exception as exc:  # pragma: no cover
            return SubsystemStatus("meta_reasoner", False, {"error": str(exc)})

    def _status_capability_evolver(self) -> SubsystemStatus:
        try:
            profiles = self.capability_evolver.all_profiles()
            return SubsystemStatus(
                "capability_evolver",
                True,
                {"profiles": len(profiles)},
            )
        except Exception as exc:  # pragma: no cover
            return SubsystemStatus("capability_evolver", False, {"error": str(exc)})

    def _status_context_manager(self) -> SubsystemStatus:
        try:
            domains = self.context_manager.all_domains()
            return SubsystemStatus(
                "context_manager",
                True,
                {"domains": len(domains)},
            )
        except Exception as exc:  # pragma: no cover
            return SubsystemStatus("context_manager", False, {"error": str(exc)})

    def _status_autonomous_loop(self) -> SubsystemStatus:
        try:
            running = bool(getattr(self.autonomous_loop, "is_running", False))
            return SubsystemStatus("autonomous_loop", True, {"running": running})
        except Exception as exc:  # pragma: no cover
            return SubsystemStatus("autonomous_loop", False, {"error": str(exc)})

    def _status_knowledge_expansion(self) -> SubsystemStatus:
        try:
            entries = self.knowledge_expansion.entry_count()
            return SubsystemStatus(
                "knowledge_expansion",
                True,
                {"entries": entries},
            )
        except Exception as exc:  # pragma: no cover
            return SubsystemStatus("knowledge_expansion", False, {"error": str(exc)})

    def _status_multimodal(self) -> SubsystemStatus:
        try:
            backends = self.multimodal.available_backends()
            return SubsystemStatus(
                "multimodal",
                True,
                {"backends": list(backends)},
            )
        except Exception as exc:  # pragma: no cover
            return SubsystemStatus("multimodal", False, {"error": str(exc)})

    def __repr__(self) -> str:
        return (
            "<UnifiedBridge "
            "self_learner+meta_reasoner+capability_evolver"
            "+context_manager+autonomous_loop+knowledge_expansion"
            "+multimodal>"
        )


__all__ = ["UnifiedBridge", "SubsystemStatus"]
