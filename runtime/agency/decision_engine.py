"""
decision_engine.py — JARVIS Pass 24
Routes user intent to the correct handler based on NLU + emotion + memory context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

# ---------------------------------------------------------------------------
# Optional imports — mocked if absent
# ---------------------------------------------------------------------------
try:
    from runtime.agency.nlu_engine import NLUResult
except ImportError:
    @dataclass
    class NLUResult:
        intent: str = "unknown"
        confidence: float = 0.5
        entities: dict = field(default_factory=dict)
        language: str = "he"

try:
    from runtime.agency.emotion_engine import EmotionState
except ImportError:
    @dataclass
    class EmotionState:
        label: str = "neutral"
        valence: float = 0.0
        arousal: float = 0.0

try:
    from runtime.agency.long_term_memory import MemoryContext
except ImportError:
    @dataclass
    class MemoryContext:
        entries: list = field(default_factory=list)
        user_id: str = "unknown"


# ---------------------------------------------------------------------------
# Decision dataclass
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    action: str                   # e.g. "robot_brain", "skill", "memory_store", "llm_fallback"
    confidence: float             # 0.0 – 1.0
    reasoning: str
    fallback: str                 # fallback action if primary fails
    clarification_prompt: str = ""  # Hebrew prompt when confidence < 0.8

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "fallback": self.fallback,
            "clarification_prompt": self.clarification_prompt,
        }


# ---------------------------------------------------------------------------
# Routing constants
# ---------------------------------------------------------------------------

ROBOT_INTENTS = {
    "robot_command", "move_robot", "navigate", "arm_control",
    "gripper", "stop_robot", "robot_status",
}

SKILL_INTENTS = {
    "skill_request", "run_skill", "automation", "code_execution",
    "web_search", "file_operation", "calendar", "reminder",
}

MEMORY_INTENTS = {
    "memory_store", "remember", "save_fact", "update_profile",
}

# Confidence thresholds
THRESHOLD_HIGH = 0.8   # act directly
THRESHOLD_MID  = 0.5   # ask clarification


# ---------------------------------------------------------------------------
# Hebrew clarification templates
# ---------------------------------------------------------------------------

HEBREW_CLARIFICATIONS = {
    "robot_brain":   "לא הבנתי לגמרי את הפקודה לרובוט. האם תוכל לפרט יותר?",
    "skill":         "רצית שאפעיל יכולת מסוימת? אנא הבהר במה מדובר.",
    "memory_store":  "רצית שאשמור מידע? מה בדיוק לשמור?",
    "llm_fallback":  "לא הצלחתי לזהות בדיוק את כוונתך. תוכל לנסח מחדש?",
}


# ---------------------------------------------------------------------------
# DecisionEngine
# ---------------------------------------------------------------------------

class DecisionEngine:
    """Routes a request to the correct JARVIS subsystem."""

    def __init__(self, available_skills: list[str] | None = None):
        self.available_skills: list[str] = available_skills or []

    # ------------------------------------------------------------------
    def decide(
        self,
        context: dict,
        *,
        nlu: Optional[NLUResult] = None,
        emotion: Optional[EmotionState] = None,
        memory: Optional[MemoryContext] = None,
    ) -> Decision:
        """
        Produce a Decision from combined context.

        Parameters
        ----------
        context : dict
            Raw context dict (may include 'intent', 'confidence', 'text', etc.)
        nlu : NLUResult | None
            Pre-parsed NLU result (preferred).  Falls back to context dict.
        emotion : EmotionState | None
            Current emotion state (used for confidence boost/penalty).
        memory : MemoryContext | None
            Long-term memory context (used for entity lookup).
        """
        # ------------------------------------------------------------------
        # 1. Resolve intent + confidence
        # ------------------------------------------------------------------
        if nlu is not None:
            intent = nlu.intent
            confidence = nlu.confidence
        else:
            intent = context.get("intent", "unknown")
            confidence = float(context.get("confidence", 0.5))

        # Clamp
        confidence = max(0.0, min(1.0, confidence))

        # Emotion modulation: high arousal → slight confidence penalty
        if emotion is not None and emotion.arousal > 0.7:
            confidence = max(0.0, confidence - 0.05)

        # ------------------------------------------------------------------
        # 2. Route by intent
        # ------------------------------------------------------------------
        action, reasoning, fallback = self._route(intent, context)

        # ------------------------------------------------------------------
        # 3. Apply confidence thresholds
        # ------------------------------------------------------------------
        clarification = ""

        if confidence < THRESHOLD_MID:
            # Low confidence → force LLM fallback
            action = "llm_fallback"
            reasoning = f"Confidence {confidence:.2f} below threshold {THRESHOLD_MID}; delegating to LLM."
            clarification = HEBREW_CLARIFICATIONS.get("llm_fallback", "")

        elif confidence < THRESHOLD_HIGH:
            # Medium confidence → keep action but ask for clarification
            clarification = HEBREW_CLARIFICATIONS.get(action, HEBREW_CLARIFICATIONS["llm_fallback"])
            reasoning = f"{reasoning} (confidence {confidence:.2f} — clarification requested)"

        return Decision(
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            fallback=fallback,
            clarification_prompt=clarification,
        )

    # ------------------------------------------------------------------
    def _route(self, intent: str, context: dict) -> tuple[str, str, str]:
        """
        Returns (action, reasoning, fallback) for a given intent.
        """
        if intent in ROBOT_INTENTS:
            return (
                "robot_brain",
                f"Intent '{intent}' maps to RobotBrain subsystem.",
                "llm_fallback",
            )

        if intent in SKILL_INTENTS:
            skill_name = context.get("skill_name", "")
            if skill_name and skill_name not in self.available_skills:
                return (
                    "llm_fallback",
                    f"Skill '{skill_name}' not available; falling back to LLM.",
                    "llm_fallback",
                )
            return (
                "skill",
                f"Intent '{intent}' routes to SupremeJarvisBrain skill executor.",
                "llm_fallback",
            )

        if intent in MEMORY_INTENTS:
            return (
                "memory_store",
                f"Intent '{intent}' routes to LongTermMemory.",
                "llm_fallback",
            )

        # Default
        return (
            "llm_fallback",
            f"No specific handler for intent '{intent}'; delegating to LLM.",
            "llm_fallback",
        )


# ---------------------------------------------------------------------------
# MockDecisionEngine — always returns safe llm_fallback decision
# ---------------------------------------------------------------------------

class MockDecisionEngine:
    """Test double — no routing logic, always returns llm_fallback @ 0.5."""

    available_skills: list[str] = []

    def decide(self, context: dict, **kwargs) -> Decision:  # noqa: ARG002
        return Decision(
            action="llm_fallback",
            confidence=0.5,
            reasoning="mock",
            fallback="llm",
            clarification_prompt="",
        )
