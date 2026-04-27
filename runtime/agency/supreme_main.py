"""Boot the JARVIS supreme stack — the canonical entry point.

``main()`` is the 9-step orchestration boot sequence: load skills, build
the SupremeJarvisBrain, wake the UnifiedBridge, register experts, and
return a ``BootedSystem`` handle the caller can drive directly.

Designed to run cleanly without an Anthropic API key — every dependency
on the LLM is lazy / optional. Boot is idempotent and safe to call
repeatedly; subsequent calls return the same handles.

Used by:
- ``agency.supreme_main:main`` as the programmatic entry point.
- ``python -m agency.supreme_main`` for CLI inspection.
- The autonomous REPL, tests, and any script that wants the full stack.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BootedSystem:
    """Handle returned by :func:`main` — every booted subsystem."""

    bridge: Any
    brain: Any
    registry: Any
    experts: dict[str, Any]
    orchestrator: Any | None = None
    boot_log: list[str] = field(default_factory=list)

    def status(self) -> dict[str, Any]:
        """Aggregated health snapshot of the booted system."""
        from .experts import all_experts as _all_experts

        bridge_status = self.bridge.status() if self.bridge is not None else None
        return {
            "ok": bool(bridge_status and bridge_status.get("ok")),
            "skills_loaded": len(self.registry) if self.registry is not None else 0,
            "categories": len(self.registry.categories()) if self.registry is not None else 0,
            "bridge": bridge_status,
            "experts": {n: e.status() for n, e in (self.experts or {}).items()},
            "boot_log": list(self.boot_log),
        }

    def route(self, request: str) -> dict[str, Any]:
        """Route a free-form request and return a structured result."""
        return self.brain.skill_for(request).to_dict()


_booted: BootedSystem | None = None


def main(reload: bool = False) -> BootedSystem:
    """Boot the supreme stack and return a handle.

    Idempotent: subsequent calls return the same ``BootedSystem``
    instance unless ``reload=True`` is passed.
    """
    global _booted
    if _booted is not None and not reload:
        return _booted

    log: list[str] = []

    # 1. Load skills.
    from .skills import SkillRegistry
    registry = SkillRegistry.load()
    log.append(f"skills loaded: n={len(registry)} categories={len(registry.categories())}")

    # 2. Build the routing brain.
    from .jarvis_brain import SupremeJarvisBrain
    brain = SupremeJarvisBrain(registry)
    log.append("jarvis_brain ready")

    # 3. Wake the unified bridge (capabilities subsystems).
    from .unified_bridge import UnifiedBridge
    bridge = UnifiedBridge()
    log.append("unified_bridge ready: " + ", ".join(bridge.subsystem_names()))

    # 4. Register experts.
    from .experts import all_experts
    experts = all_experts()
    log.append(f"experts ready: {', '.join(sorted(experts))}")

    # 5. Optional orchestrator (LLM-backed; safe to skip if no key).
    orchestrator: Any = None
    try:
        from .amjad_jarvis_meta_orchestrator import AmjadJarvisMetaOrchestrator
        from .llm import LLMConfig

        # Only try to construct the orchestrator if an API key is set;
        # construction otherwise raises and pollutes the boot log.
        cfg = LLMConfig.from_env()
        if cfg.api_key:
            orchestrator = AmjadJarvisMetaOrchestrator(registry=registry)
            log.append("meta_orchestrator ready")
        else:
            log.append("meta_orchestrator skipped (no ANTHROPIC_API_KEY)")
    except Exception as exc:  # pragma: no cover - defensive
        log.append(f"meta_orchestrator skipped: {exc}")

    _booted = BootedSystem(
        bridge=bridge,
        brain=brain,
        registry=registry,
        experts=experts,
        orchestrator=orchestrator,
        boot_log=log,
    )
    return _booted


def reset() -> None:
    """Clear the cached BootedSystem (test-only escape hatch)."""
    global _booted
    _booted = None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agency.supreme_main",
        description="Boot the JARVIS supreme stack and inspect status.",
    )
    parser.add_argument("--status", action="store_true", help="Print full status JSON.")
    parser.add_argument("--route", help="Route a free-form request and print result JSON.")
    parser.add_argument("--reload", action="store_true", help="Reset cached boot before running.")
    args = parser.parse_args(argv)

    if args.reload:
        reset()
    booted = main()
    if args.route:
        print(json.dumps(booted.route(args.route), indent=2, default=str))
    else:
        print(json.dumps(booted.status(), indent=2, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli(sys.argv[1:]))


__all__ = ["BootedSystem", "main", "reset"]
