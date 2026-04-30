"""Tier 1 — GOD-MODE :class:`JARVISInterface`.

The single public entry point for every JARVIS One capability. Designed
so that ``ask`` / ``create`` / ``chat`` cover 90% of usage; the remaining
10% (orchestration, planning, world model, hot reload, etc.) is exposed
as explicit methods backed by the :class:`Bridge`.

Hebrew-first by design: language detection routes responses to the
correct locale, and the advisor brain is consulted on every turn so
emotional context is captured.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .collaborative_workflow import Transcript
from .decision_engine import Decision
from .document_generator import Document
from .drawing_engine import Diagram
from .expert_personas import ExpertPersona
from .multi_agent_orchestrator import OrchestrationResult
from .multimodal_output import MultimodalBundle, SUPPORTED_MODALITIES
from .react_loop import ReActTrace
from .task_planner import Plan, PlanTask
from .unified_bridge import Bridge, build_bridge


@dataclass
class AskResponse:
    """Returned by :meth:`JARVISInterface.ask`."""
    request: str
    persona: str
    decision: Decision
    response: str
    emotional: dict[str, Any] = field(default_factory=dict)
    references: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "persona": self.persona,
            "decision": self.decision.to_dict(),
            "response": self.response,
            "emotional": self.emotional,
            "references": self.references,
        }


@dataclass
class ChatTurn:
    user: str
    assistant: str
    persona: str
    sentiment: str
    crisis: bool

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class JARVISInterface:
    """The single public surface of JARVIS One (GOD-MODE).

    Method index — exactly 13 capability methods:

    1. :meth:`ask` — single-shot Q&A through best persona.
    2. :meth:`chat` — append-only conversational turn with memory.
    3. :meth:`create` — multimodal artefact generation.
    4. :meth:`orchestrate` — split, fan out, merge across personas.
    5. :meth:`plan` — schedule a task DAG with critical-path analysis.
    6. :meth:`collaborate` — run a named multi-agent pattern.
    7. :meth:`react` — bounded Observe→Reason→Act→Learn loop.
    8. :meth:`route` — show how a request would be routed.
    9. :meth:`remember` / :meth:`recall` — vector memory.
    10. :meth:`status` — system snapshot for the dashboard.
    11. :meth:`personas` — catalog of senior expert personas.
    12. :meth:`gesture` — process a vision frame into an OS intent.
    13. :meth:`reload` — hot-reload skills + persona registry.
    """

    def __init__(self, bridge: Bridge | None = None,
                 *, repo: Path | None = None) -> None:
        self.bridge = bridge or build_bridge(repo=repo)
        self._chat_log: list[ChatTurn] = []

    # ------------------------------------------------------------------ 1
    def ask(self, message: str, *, persona_slug: str | None = None) -> AskResponse:
        decision = self.bridge.decision.route(message)
        if persona_slug:
            persona = self.bridge.personas.by_slug(persona_slug) \
                or self.bridge.personas.best_for(message)
        else:
            persona = self.bridge.personas.best_for(message)
        emotional = self.bridge.advisor.respond(message)
        if emotional.crisis:
            text = emotional.advisor_response
        else:
            text = self._compose_answer(persona, message, decision)
        # Pull a couple of related skills as references.
        refs = []
        if decision.skill:
            skill = self.bridge.skills.find(decision.skill)
            if skill is not None:
                refs.append({"slug": skill.slug, "name": skill.name,
                             "category": skill.category})
        return AskResponse(
            request=message, persona=persona.slug, decision=decision,
            response=text, emotional=emotional.to_dict(), references=refs,
        )

    # ------------------------------------------------------------------ 2
    def chat(self, message: str) -> ChatTurn:
        ans = self.ask(message)
        turn = ChatTurn(
            user=message,
            assistant=ans.response,
            persona=ans.persona,
            sentiment=ans.emotional.get("sentiment", "neutral"),
            crisis=bool(ans.emotional.get("crisis")),
        )
        self._chat_log.append(turn)
        # Persist a short memory record for future recall.
        self.bridge.memory.add(
            f"USER: {message}\nASSISTANT: {ans.response}",
            persona=ans.persona, sentiment=turn.sentiment,
        )
        return turn

    def chat_log(self) -> list[ChatTurn]:
        return list(self._chat_log)

    # ------------------------------------------------------------------ 3
    def create(self, request: str, *,
               want: Iterable[str] = SUPPORTED_MODALITIES,
               diagram: Diagram | None = None,
               document: Document | None = None,
               text: str | None = None,
               document_format: str = "markdown") -> MultimodalBundle:
        if text is None:
            text = self.ask(request).response
        return self.bridge.multimodal.render(
            request, want=want, diagram=diagram, document=document,
            text=text, document_format=document_format,
        )

    # ------------------------------------------------------------------ 4
    def orchestrate(self, request: str) -> OrchestrationResult:
        return self.bridge.orchestrator.run(request)

    # ------------------------------------------------------------------ 5
    def plan(self, goal: str, *, tasks: list[PlanTask] | None = None) -> Plan:
        if not tasks:
            tasks = self.bridge.planner.decompose(goal)
        return self.bridge.planner.schedule(tasks)

    # ------------------------------------------------------------------ 6
    def collaborate(self, pattern: str, topic: str) -> Transcript:
        return self.bridge.collab.run(pattern, topic)

    # ------------------------------------------------------------------ 7
    def react(self, goal: str, *, max_steps: int = 4) -> ReActTrace:
        return self.bridge.react.run(goal, max_steps=max_steps)

    # ------------------------------------------------------------------ 8
    def route(self, message: str) -> Decision:
        return self.bridge.decision.route(message)

    # ------------------------------------------------------------------ 9
    def remember(self, text: str, **metadata: Any) -> str:
        return self.bridge.memory.add(text, **metadata)

    def recall(self, query: str, *, top_k: int = 5) -> list[dict[str, Any]]:
        return self.bridge.memory.search(query, top_k=top_k)

    # ------------------------------------------------------------------ 10
    def status(self) -> dict[str, Any]:
        return self.bridge.status()

    # ------------------------------------------------------------------ 11
    def personas(self) -> list[dict[str, Any]]:
        return self.bridge.personas.catalog()

    # ------------------------------------------------------------------ 12
    def gesture(self, frame: Any) -> dict[str, Any]:
        evt = self.bridge.vr.handle_frame(frame)
        return {
            "gesture": evt.gesture,
            "intent": evt.intent,
            "payload": evt.payload,
            "action_kind": evt.action.kind if evt.action else None,
            "action_allowed": evt.action.allowed if evt.action else False,
        }

    # ------------------------------------------------------------------ 13
    def reload(self) -> dict[str, Any]:
        snap = self.bridge.skills.reload()
        return {
            "count": snap.count,
            "categories": snap.categories,
            "by_category": snap.by_category,
        }

    # ------------------------------------------------------------------
    def _compose_answer(self, persona: ExpertPersona, message: str,
                        decision: Decision) -> str:
        if decision.needs_clarification:
            return decision.clarification
        opener = (
            f"שלום, אני {persona.display_name}." if persona.language == "he"
            else f"Hello, I'm {persona.display_name}."
        )
        body = (
            f"בקשתך: '{message}'. ניתבתי אותה אל '{decision.skill}' "
            f"בביטחון {decision.confidence:.2f}."
            if persona.language == "he" else
            f"Your request: '{message}'. Routed to '{decision.skill}' "
            f"with confidence {decision.confidence:.2f}."
        )
        sig = persona.signature
        return f"{opener}\n{body}\n{sig}".strip()


def build_default_interface(repo: Path | None = None) -> JARVISInterface:
    """Module-level convenience constructor used by the CLI / server."""
    return JARVISInterface(repo=repo)
