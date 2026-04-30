"""Pass-24 API gateway — VAD → NLU → Decision → Skill → TTS pipeline.

Sequences the local subsystems so a raw user utterance flows through
voice activity detection, language understanding, the decision engine,
the chosen skill, and finally text-to-speech synthesis. Each stage is
optional and can be swapped via the constructor.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from . import context_manager as ctx
from .decision_engine import Decision, DecisionEngine
from .local_skill_engine import LocalSkillEngine
from .local_voice import LocalVoice, detect_language


@dataclass
class GatewayResult:
    transcript: str
    language: str
    decision: Decision
    response: str
    audio_bytes: int
    elapsed: float
    trace: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transcript": self.transcript,
            "language": self.language,
            "decision": self.decision.to_dict(),
            "response": self.response,
            "audio_bytes": self.audio_bytes,
            "elapsed": round(self.elapsed, 4),
            "trace": list(self.trace),
        }


class APIGateway:
    """End-to-end pipeline orchestrator."""

    def __init__(self, *, voice: LocalVoice, decision: DecisionEngine,
                 skills: LocalSkillEngine,
                 responder: Any | None = None) -> None:
        self.voice = voice
        self.decision = decision
        self.skills = skills
        self.responder = responder  # optional callable(skill, message) -> str

    def handle(self, audio_or_text: bytes | str) -> GatewayResult:
        start = time.time()
        trace: list[str] = []

        # 1) STT (or pass-through for text).
        if isinstance(audio_or_text, (bytes, bytearray)):
            stt = self.voice.transcribe(bytes(audio_or_text))
            transcript = stt["text"]
            trace.append(f"stt:{stt['engine']}")
        else:
            transcript = audio_or_text
            trace.append("stt:passthrough")
        language = detect_language(transcript)

        with ctx.scope(stage="gateway", transcript=transcript, language=language):
            # 2) Decision routing.
            decision = self.decision.route(transcript)
            trace.append(f"decision:{decision.skill or 'none'}@{decision.confidence:.2f}")
            ctx.set_value("skill", decision.skill)
            ctx.set_value("confidence", decision.confidence)

            # 3) Responder — defaults to deterministic mock so tests stay hermetic.
            if decision.needs_clarification:
                response_text = decision.clarification
                trace.append("respond:clarify")
            else:
                response_text = self._respond(decision.skill or "", transcript)
                trace.append("respond:skill")

            # 4) TTS.
            audio = self.voice.synthesize(response_text, language=language)
            trace.append(f"tts:{len(audio)}b")

        return GatewayResult(
            transcript=transcript, language=language,
            decision=decision, response=response_text,
            audio_bytes=len(audio), elapsed=time.time() - start,
            trace=trace,
        )

    def _respond(self, skill_slug: str, message: str) -> str:
        if self.responder is not None:
            try:
                return str(self.responder(skill_slug, message))
            except Exception as exc:  # noqa: BLE001
                return f"[gateway-error] {type(exc).__name__}: {exc}"
        skill = self.skills.find(skill_slug) if skill_slug else None
        if skill is None:
            return f"(no skill matched) {message}"
        return f"[{skill.slug}] {skill.name}: {message}"
