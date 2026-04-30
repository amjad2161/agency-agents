"""J.A.R.V.I.S One — OMEGA_NEXUS unified subsystem package.

The :class:`JARVISInterface` (GOD-MODE) is the single public entry point.
It composes 30 cooperating subsystems organised in seven tiers:

* Tier 1 — GOD-MODE interface (:mod:`unified_interface`)
* Tier 2 — Multi-agent orchestration (orchestrator, personas, workflow,
  task planner)
* Tier 3 — Output engines (multimodal, document generator, drawing engine)
* Tier 4 — Intelligence & companion (advisor brain)
* Tier 5 — Local processing (brain/voice/vision/memory/os/skills/react/vr)
* Tier 6 — Pass-24 decision & control (decision/gateway/reload/task/ctx/world)
* Tier 7 — Core infrastructure (bridge to existing :mod:`agency` modules)

Every module follows the *mock-first* pattern: heavy optional dependencies
(Ollama, Whisper, MediaPipe, ChromaDB, ReportLab, Watchdog, …) are imported
defensively. When they are missing, a deterministic in-memory fallback keeps
the public API working so tests remain hermetic and Hebrew-first responses
stay available offline. No new third-party dependencies are required.
"""

from __future__ import annotations

from .unified_interface import JARVISInterface, build_default_interface
from .unified_bridge import Bridge, build_bridge

__all__ = [
    "JARVISInterface", "build_default_interface", "Bridge", "build_bridge",
]
