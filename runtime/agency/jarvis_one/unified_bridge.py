"""Unified bridge (Tier 7) — central hub aggregating every JARVIS subsystem.

Holds one instance of each subsystem so callers can fetch them by name
without rebuilding the entire stack on every request. The bridge also
exposes a :meth:`status` snapshot that the ``/singularity`` HTTP endpoint
and the ``agency map`` CLI command consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import __version__
from .advisor_brain import AdvisorBrain
from .api_gateway import APIGateway
from .collaborative_workflow import CollaborativeWorkflow
from .context_manager import snapshot as ctx_snapshot
from .decision_engine import DecisionEngine, DecisionRule
from .document_generator import DocumentGenerator
from .drawing_engine import DrawingEngine
from .expert_personas import ALL_PERSONAS, ExpertPersonaIndex
from .hot_reload import HotReloadConfig, HotReloadWatcher
from .local_brain import LocalBrain
from .local_memory import LocalMemory
from .local_os import LocalOS
from .local_skill_engine import LocalSkillEngine
from .local_voice import LocalVoice
from .local_vision import LocalVision
from .multi_agent_orchestrator import MultiAgentOrchestrator
from .multimodal_output import MultimodalOutput
from .react_loop import ReActLoop
from .task_executor import TaskExecutor
from .task_planner import TaskPlanner
from .vr_interface import VRInterface
from .world_model import WorldModel


@dataclass
class Bridge:
    """Container for the 21 JARVIS subsystems."""

    repo: Path
    skills: LocalSkillEngine
    brain: LocalBrain
    voice: LocalVoice
    vision: LocalVision
    memory: LocalMemory
    os_bridge: LocalOS
    react: ReActLoop
    vr: VRInterface
    decision: DecisionEngine
    gateway: APIGateway
    hot_reload: HotReloadWatcher
    task_executor: TaskExecutor
    world: WorldModel
    advisor: AdvisorBrain
    drawing: DrawingEngine
    docgen: DocumentGenerator
    multimodal: MultimodalOutput
    orchestrator: MultiAgentOrchestrator
    collab: CollaborativeWorkflow
    planner: TaskPlanner
    personas: ExpertPersonaIndex
    extra: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        snap = self.skills.snapshot()
        return {
            "version": __version__,
            "repo": str(self.repo),
            "skills": {
                "count": snap.count,
                "categories": snap.categories,
                "by_category": snap.by_category,
            },
            "personas": {
                "count": len(self.personas.personas),
                "catalog": self.personas.catalog(),
            },
            "subsystems": self._subsystem_health(),
            "context": ctx_snapshot(),
            "world": self.world.to_dict(),
        }

    def _subsystem_health(self) -> dict[str, Any]:
        return {
            "brain": self.brain.health(),
            "voice": self.voice.health(),
            "vision": self.vision.health(),
            "memory": self.memory.health(),
            "os": self.os_bridge.health(),
            "vr": self.vr.health(),
            "task_executor": self.task_executor.stats(),
            "decision_threshold": self.decision.threshold,
        }


def build_bridge(repo: Path | None = None) -> Bridge:
    """Construct the Bridge with sensible defaults wired in.

    Pure-Python construction — no network calls, no heavy dep imports
    triggered on the happy path. Each subsystem will lazily try its
    optional dependency only when actually used.
    """
    skills = LocalSkillEngine(repo=repo)
    brain = LocalBrain()
    voice = LocalVoice()
    vision = LocalVision()
    memory = LocalMemory()
    os_bridge = LocalOS()
    react = ReActLoop(brain=brain)
    vr = VRInterface(vision=vision, os_bridge=os_bridge)
    decision = DecisionEngine(skills.registry, rules=[
        DecisionRule(keywords=("draw", "diagram", "flowchart"),
                     skill_slug="design/visual-design"),
        DecisionRule(keywords=("contract", "legal", "lawsuit"),
                     skill_slug="strategy/strategic-advisor"),
    ])
    task_executor = TaskExecutor(workers=0)
    world = WorldModel()
    advisor = AdvisorBrain()
    drawing = DrawingEngine()
    docgen = DocumentGenerator()
    multimodal = MultimodalOutput(voice=voice, docgen=docgen, draw=drawing)
    orchestrator = MultiAgentOrchestrator(executor=task_executor)
    collab = CollaborativeWorkflow(personas=ALL_PERSONAS)
    planner = TaskPlanner()
    personas = ExpertPersonaIndex(ALL_PERSONAS)
    gateway = APIGateway(voice=voice, decision=decision, skills=skills)

    # Hot reload watches the repo's persona dirs.
    hot = HotReloadWatcher(
        config=HotReloadConfig(paths=[skills.repo]),
        on_change=lambda _path: skills.reload(),
    )

    return Bridge(
        repo=skills.repo,
        skills=skills, brain=brain, voice=voice, vision=vision,
        memory=memory, os_bridge=os_bridge, react=react, vr=vr,
        decision=decision, gateway=gateway, hot_reload=hot,
        task_executor=task_executor, world=world, advisor=advisor,
        drawing=drawing, docgen=docgen, multimodal=multimodal,
        orchestrator=orchestrator, collab=collab, planner=planner,
        personas=personas,
    )
