"""Natural language → motion command parser.

Fast regex path first; optional LLM fallback for unrecognised commands.

Usage
-----
    parser = NLPMotionParser()
    cmd = parser.parse("walk forward 2 meters")
    # MotionCommand(skill_name='walk_forward', params={'distance_m': 2.0}, ...)
    if cmd:
        parser.execute(cmd, sim)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

from ..logging import get_logger
from .simulation import SimulationBridge

log = get_logger()


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class MotionCommand:
    skill_name: str
    params: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    raw_text: str = ""


# ---------------------------------------------------------------------------
# Regex patterns (fast path, no LLM needed)
# ---------------------------------------------------------------------------

# Each entry: (compiled_regex, skill_name, param_extractor_callable)
def _float(s: str) -> float:
    return float(s.strip())


_PATTERNS: list[tuple] = [
    # "walk forward N meters / metre / m"
    (
        re.compile(
            r"walk\s+forward\s+(?P<dist>[\d.]+)\s*(?:meter|metre|meters|metres|m)?",
            re.IGNORECASE,
        ),
        "walk_forward",
        lambda m: {"distance_m": _float(m.group("dist"))},
    ),
    # "walk backward N meters"
    (
        re.compile(
            r"walk\s+(?:backward|back(?:ward)?)\s+(?P<dist>[\d.]+)\s*(?:meter|metre|meters|metres|m)?",
            re.IGNORECASE,
        ),
        "walk_backward",
        lambda m: {"distance_m": _float(m.group("dist"))},
    ),
    # "turn left N degrees"
    (
        re.compile(
            r"turn\s+left\s+(?P<angle>[\d.]+)\s*(?:degrees?|deg|°)?",
            re.IGNORECASE,
        ),
        "turn_left",
        lambda m: {"angle_deg": _float(m.group("angle"))},
    ),
    # "turn right N degrees"
    (
        re.compile(
            r"turn\s+right\s+(?P<angle>[\d.]+)\s*(?:degrees?|deg|°)?",
            re.IGNORECASE,
        ),
        "turn_right",
        lambda m: {"angle_deg": _float(m.group("angle"))},
    ),
    # "turn left" (no angle → default 90°)
    (
        re.compile(r"turn\s+left\b", re.IGNORECASE),
        "turn_left",
        lambda m: {"angle_deg": 90.0},
    ),
    # "turn right" (no angle)
    (
        re.compile(r"turn\s+right\b", re.IGNORECASE),
        "turn_right",
        lambda m: {"angle_deg": 90.0},
    ),
    # "sit down"
    (
        re.compile(r"\bsit(?:\s+down)?\b", re.IGNORECASE),
        "sit_down",
        lambda m: {},
    ),
    # "stand up"
    (
        re.compile(r"\bstand(?:\s+up)?\b", re.IGNORECASE),
        "stand_up",
        lambda m: {},
    ),
    # "wave" / "wave hand" / "wave right/left hand"
    (
        re.compile(r"\bwave\b(?:\s+(?P<hand>right|left)\s+hand)?", re.IGNORECASE),
        "wave_hand",
        lambda m: {"hand": (m.group("hand") or "right").lower()},
    ),
    # "nod" / "nod head N times"
    (
        re.compile(r"\bnod(?:\s+head)?(?:\s+(?P<n>\d+)\s+times?)?\b", re.IGNORECASE),
        "nod_head",
        lambda m: {"times": int(m.group("n") or 2)},
    ),
    # "reach forward N meters"
    (
        re.compile(
            r"reach\s+forward\s*(?:(?P<dist>[\d.]+)\s*(?:meter|metre|meters|metres|m)?)?",
            re.IGNORECASE,
        ),
        "reach_forward",
        lambda m: {"distance_m": _float(m.group("dist")) if m.group("dist") else 0.3},
    ),
    # "pick up X" / "grab X" / "grasp X"
    (
        re.compile(
            r"(?:pick\s+up|grab|grasp)\s+(?P<obj>.+)",
            re.IGNORECASE,
        ),
        "grasp_object",
        lambda m: {"object_name": m.group("obj").strip()},
    ),
    # "pick up" with no object
    (
        re.compile(r"(?:pick\s+up|grab|grasp)\b", re.IGNORECASE),
        "grasp_object",
        lambda m: {"object_name": ""},
    ),
    # "release" / "drop"
    (
        re.compile(r"\b(?:release|drop|let\s+go)\b", re.IGNORECASE),
        "release_object",
        lambda m: {},
    ),
    # "stop" / "halt" / "freeze"
    (
        re.compile(r"\b(?:stop|halt|freeze|stand\s+still)\b", re.IGNORECASE),
        "stand_still",
        lambda m: {},
    ),
    # "walk forward" (no distance → default 1 m)
    (
        re.compile(r"walk\s+forward\b", re.IGNORECASE),
        "walk_forward",
        lambda m: {"distance_m": 1.0},
    ),
    # "walk backward" (no distance → default 1 m)
    (
        re.compile(r"walk\s+(?:backward|back)\b", re.IGNORECASE),
        "walk_backward",
        lambda m: {"distance_m": 1.0},
    ),
]


# ---------------------------------------------------------------------------
# Skill dispatcher map
# ---------------------------------------------------------------------------

def _get_skill_fn(name: str):
    """Import and return the motion skill callable by name."""
    from . import motion_skills as ms  # lazy import avoids circular deps
    return getattr(ms, name, None)


# ---------------------------------------------------------------------------
# NLPMotionParser
# ---------------------------------------------------------------------------

class NLPMotionParser:
    """Parse natural-language commands into MotionCommand objects.

    Parameters
    ----------
    use_llm_fallback:
        If True and regex fails, attempts an LLM call to interpret the text.
        Default False (no network / API required in CI).
    """

    def __init__(self, use_llm_fallback: bool = False) -> None:
        self._use_llm = use_llm_fallback

    # --- public API ---

    def parse(self, text: str) -> Optional[MotionCommand]:
        """Parse *text* and return a MotionCommand, or None if unrecognised."""
        text = text.strip()
        if not text:
            return None

        # Fast path: regex
        cmd = self._regex_parse(text)
        if cmd:
            log.info("nlp_motion.parse regex skill=%s params=%s", cmd.skill_name, cmd.params)
            return cmd

        # Optional LLM fallback
        if self._use_llm:
            cmd = self._llm_parse(text)
            if cmd:
                log.info("nlp_motion.parse llm skill=%s params=%s", cmd.skill_name, cmd.params)
                return cmd

        log.warning("nlp_motion.parse unrecognised text=%r", text)
        return None

    def execute(self, command: MotionCommand, sim: SimulationBridge) -> bool:
        """Execute a parsed MotionCommand against the simulation.

        Returns True on success, False on failure.
        """
        fn = _get_skill_fn(command.skill_name)
        if fn is None:
            log.error("nlp_motion.execute unknown skill=%s", command.skill_name)
            return False
        try:
            result = fn(sim, **command.params)
            return bool(result)
        except Exception as exc:
            log.error("nlp_motion.execute skill=%s error=%s", command.skill_name, exc)
            return False

    # --- private ---

    def _regex_parse(self, text: str) -> Optional[MotionCommand]:
        for pattern, skill_name, extractor in _PATTERNS:
            m = pattern.search(text)
            if m:
                try:
                    params = extractor(m)
                except (IndexError, ValueError):
                    params = {}
                return MotionCommand(
                    skill_name=skill_name,
                    params=params,
                    confidence=1.0,
                    raw_text=text,
                )
        return None

    def _llm_parse(self, text: str) -> Optional[MotionCommand]:
        """Use the JARVIS LLM to interpret an unrecognised command."""
        try:
            from ..llm import AnthropicLLM, LLMConfig
            import json

            llm = AnthropicLLM(LLMConfig())
            prompt = (
                "You are a robotics command parser. "
                "Given a natural-language instruction, output ONLY valid JSON with keys: "
                '"skill_name" (one of: walk_forward, walk_backward, turn_left, turn_right, '
                "sit_down, stand_up, wave_hand, nod_head, reach_forward, grasp_object, "
                'release_object, stand_still) and "params" (object with numeric/string values). '
                f'Instruction: "{text}"'
            )
            raw = llm.complete(prompt, max_tokens=128)
            data = json.loads(raw)
            return MotionCommand(
                skill_name=data["skill_name"],
                params=data.get("params", {}),
                confidence=0.7,
                raw_text=text,
            )
        except Exception as exc:
            log.warning("nlp_motion.llm_parse failed: %s", exc)
            return None
