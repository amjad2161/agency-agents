"""
api_gateway.py — JARVIS Pass 24
Unified entry point for all JARVIS capabilities.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Optional internal imports — mocked when absent
# ---------------------------------------------------------------------------
try:
    from runtime.agency.nlu_engine import NLUEngine, NLUResult  # type: ignore
    _HAS_NLU = True
except ImportError:
    _HAS_NLU = False
    NLUEngine = None  # type: ignore

    from dataclasses import dataclass as _dc
    @_dc
    class NLUResult:  # type: ignore
        intent: str = "unknown"
        confidence: float = 0.5
        entities: dict = field(default_factory=dict)
        language: str = "he"

try:
    from runtime.agency.decision_engine import DecisionEngine, Decision
except ImportError:
    from dataclasses import dataclass as _dc2

    @_dc2
    class Decision:  # type: ignore
        action: str = "llm_fallback"
        confidence: float = 0.5
        reasoning: str = "fallback"
        fallback: str = "llm"
        clarification_prompt: str = ""

    class DecisionEngine:  # type: ignore
        def decide(self, context: dict, **kw) -> "Decision":
            return Decision()

try:
    from runtime.agency.emotion_engine import EmotionEngine  # type: ignore
    _HAS_EMOTION = True
except ImportError:
    _HAS_EMOTION = False

try:
    from runtime.agency.long_term_memory import LongTermMemory  # type: ignore
    _HAS_MEMORY = True
except ImportError:
    _HAS_MEMORY = False

try:
    from runtime.agency.audit_logger import AuditLogger  # type: ignore
    _HAS_AUDIT = True
except ImportError:
    _HAS_AUDIT = False

    class AuditLogger:  # type: ignore
        def log(self, **kw) -> None:
            pass


# ---------------------------------------------------------------------------
# GatewayResponse
# ---------------------------------------------------------------------------

@dataclass
class GatewayResponse:
    text: str
    action_taken: str
    skill_used: str
    emotion: str
    sources: list[str]
    latency_ms: float
    call_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    clarification: str = ""

    def to_dict(self) -> dict:
        return {
            "call_id": self.call_id,
            "text": self.text,
            "action_taken": self.action_taken,
            "skill_used": self.skill_used,
            "emotion": self.emotion,
            "sources": self.sources,
            "latency_ms": round(self.latency_ms, 2),
            "clarification": self.clarification,
        }


# ---------------------------------------------------------------------------
# Stage timing helper
# ---------------------------------------------------------------------------

class _Stopwatch:
    def __init__(self):
        self._marks: dict[str, float] = {}
        self._start = time.perf_counter()

    def mark(self, label: str) -> None:
        self._marks[label] = (time.perf_counter() - self._start) * 1000

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000

    def stage_latencies(self) -> dict[str, float]:
        return {k: round(v, 2) for k, v in self._marks.items()}


# ---------------------------------------------------------------------------
# APIGateway
# ---------------------------------------------------------------------------

class APIGateway:
    """
    Thread-safe unified entry point for JARVIS.

    Pipeline:
        text → NLU → DecisionEngine → execute action → GatewayResponse
    """

    def __init__(
        self,
        *,
        nlu_engine: Any = None,
        decision_engine: Any = None,
        emotion_engine: Any = None,
        memory: Any = None,
        audit_logger: Any = None,
        voice_mode: bool = False,
    ):
        self._nlu = nlu_engine or self._make_nlu()
        self._decision = decision_engine or DecisionEngine()
        self._emotion_engine = emotion_engine or self._make_emotion()
        self._memory = memory or self._make_memory()
        self._audit = audit_logger or AuditLogger()
        self._voice_mode = voice_mode

        # asyncio lock — created lazily in async context
        self._lock: Optional[asyncio.Lock] = None

    # ------------------------------------------------------------------
    # Public sync API
    # ------------------------------------------------------------------

    def process(self, text: str, context: dict | None = None) -> GatewayResponse:
        """
        Synchronous entry point.  Thread-safe via internal per-call isolation.
        (Does NOT use the asyncio lock — safe to call from sync threads.)
        """
        ctx = dict(context or {})
        ctx.setdefault("text", text)
        return self._run_pipeline(text, ctx)

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def process_async(self, text: str, context: dict | None = None) -> GatewayResponse:
        """Async entry point with asyncio.Lock for concurrent safety."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            ctx = dict(context or {})
            ctx.setdefault("text", text)
            return self._run_pipeline(text, ctx)

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    def _run_pipeline(self, text: str, ctx: dict) -> GatewayResponse:
        sw = _Stopwatch()
        call_id = str(uuid.uuid4())[:8]

        # Stage 1: NLU
        nlu_result = self._parse_nlu(text)
        sw.mark("nlu")
        ctx["intent"] = nlu_result.intent
        ctx["confidence"] = nlu_result.confidence

        # Stage 2: Emotion
        emotion_label = self._get_emotion(text)
        sw.mark("emotion")
        ctx["emotion"] = emotion_label

        # Stage 3: Decision
        decision = self._decision.decide(ctx, nlu=nlu_result)
        sw.mark("decision")

        # Stage 4: Execute action
        response_text, skill_used, sources = self._execute(decision, text, ctx)
        sw.mark("execute")

        total_ms = sw.elapsed_ms()

        # Audit log
        try:
            self._audit.log(
                call_id=call_id,
                text=text[:200],
                action=decision.action,
                skill=skill_used,
                latency_ms=total_ms,
                stage_latencies=sw.stage_latencies(),
            )
        except Exception:
            pass

        return GatewayResponse(
            text=response_text,
            action_taken=decision.action,
            skill_used=skill_used,
            emotion=emotion_label,
            sources=sources,
            latency_ms=total_ms,
            call_id=call_id,
            clarification=decision.clarification_prompt,
        )

    # ------------------------------------------------------------------
    # Stage implementations
    # ------------------------------------------------------------------

    def _parse_nlu(self, text: str) -> "NLUResult":
        try:
            if self._nlu is not None and hasattr(self._nlu, "parse"):
                return self._nlu.parse(text)
        except Exception:
            pass
        # Fallback: create a minimal NLUResult
        return NLUResult(intent="unknown", confidence=0.5)

    def _get_emotion(self, text: str) -> str:
        try:
            if self._emotion_engine is not None and hasattr(self._emotion_engine, "analyze"):
                state = self._emotion_engine.analyze(text)
                return state.label
        except Exception:
            pass
        return "neutral"

    def _execute(
        self, decision: "Decision", text: str, ctx: dict
    ) -> tuple[str, str, list[str]]:
        """
        Dispatch to the appropriate handler.
        Returns (response_text, skill_used, sources).
        """
        action = decision.action

        if action == "robot_brain":
            return self._handle_robot(text, ctx)

        if action == "skill":
            skill_name = ctx.get("skill_name", "")
            return self._handle_skill(skill_name, text, ctx)

        if action == "memory_store":
            return self._handle_memory(text, ctx)

        # llm_fallback or unknown
        return self._handle_llm(text, ctx, decision)

    def _handle_robot(self, text: str, ctx: dict) -> tuple[str, str, list[str]]:
        try:
            from runtime.agency.robotics.robot_brain import RobotBrain  # type: ignore
            rb = RobotBrain()
            result = rb.process_command(text)
            return str(result), "robot_brain", []
        except Exception as e:
            return f"פקודת רובוט נכשלה: {e}", "robot_brain", []

    def _handle_skill(self, skill_name: str, text: str, ctx: dict) -> tuple[str, str, list[str]]:
        try:
            from runtime.agency.supreme_jarvis_brain import SupremeJarvisBrain  # type: ignore
            brain = SupremeJarvisBrain()
            result = brain.run_skill(skill_name, text, ctx)
            return str(result), skill_name or "skill", []
        except Exception as e:
            return f"הפעלת כישרון נכשלה: {e}", skill_name or "skill", []

    def _handle_memory(self, text: str, ctx: dict) -> tuple[str, str, list[str]]:
        try:
            from runtime.agency.long_term_memory import LongTermMemory  # type: ignore
            mem = LongTermMemory()
            mem.store({"text": text, "context": ctx})
            return "המידע נשמר בהצלחה.", "long_term_memory", []
        except Exception as e:
            return f"שמירה נכשלה: {e}", "long_term_memory", []

    def _handle_llm(self, text: str, ctx: dict, decision: "Decision") -> tuple[str, str, list[str]]:
        try:
            from runtime.agency.llm_interface import LLMInterface  # type: ignore
            llm = LLMInterface()
            response = llm.generate(text, context=ctx)
            return str(response), "llm", []
        except Exception:
            # Pure fallback — echo with clarification if present
            clarification = decision.clarification_prompt
            if clarification:
                return clarification, "llm_fallback", []
            return f"קיבלתי: {text}", "llm_fallback", []

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_nlu():
        try:
            from runtime.agency.nlu_engine import NLUEngine as _NLU  # type: ignore
            return _NLU()
        except Exception:
            return None

    @staticmethod
    def _make_emotion():
        try:
            from runtime.agency.emotion_engine import EmotionEngine as _EE  # type: ignore
            return _EE()
        except Exception:
            return None

    @staticmethod
    def _make_memory():
        try:
            from runtime.agency.long_term_memory import LongTermMemory as _LTM  # type: ignore
            return _LTM()
        except Exception:
            return None
