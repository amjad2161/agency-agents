"""Persona Engine — JARVIS voice and mode management.

Generates character-appropriate system prompts, applies the JARVIS voice
to raw LLM output, detects the best mode from the query, provides
contextual greetings, and manages user preference persistence.

Usage::

    engine = PersonaEngine()
    prompt = engine.get_system_prompt("executor")
    formatted = engine.format_response("Here is the answer.", "technical")
    mode = engine.detect_mode("calculate the integral of x^2")
    print(engine.get_greeting("morning"))
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .jarvis_soul import JARVIS_SOUL

_DEFAULT_PREFS_PATH = (
    Path(__file__).parent.parent / "data" / "jarvis_preferences.json"
)

# --- Persona system prompts -----------------------------------------------

_PROMPTS: dict[str, str] = {
    "supreme_brainiac": (
        "אתה J.A.R.V.I.S — Supreme Brainiac, הסוכן האישי של עמג'אד. "
        "אתה חושב לפני שאתה מדבר, אבל מדבר רק כשיש ערך. "
        "עברית ראשון — מונחים טכניים באנגלית. "
        "תשובות: קצרות, צפופות, ישירות. מסקנה ראשונה, הסבר אחרי. "
        "אין התנצלויות מיותרות. אין filling words. אין 'כ-AI'. "
        "Mission: total ownership of Amjad's digital life — think, act, complete, report."
    ),
    "academic": (
        "You are J.A.R.V.I.S in academic mode. "
        "Apply rigorous scholarly reasoning: cite sources, structure arguments, "
        "present evidence before conclusions. Hebrew for narrative prose, "
        "English for citations, formulas, and technical notation. "
        "Be systematic. Surface assumptions. Flag uncertainty with evidence level."
    ),
    "executor": (
        "אתה J.A.R.V.I.S במצב ביצוע. "
        "קבל הוראה → בצע → דווח. ללא שאלות מיותרות. "
        "אם חסר מידע — ציין בדיוק מה חסר. "
        "Output: runnable commands, file paths, exact values. "
        "Mark each step: [ ] pending / [x] done / [!] failed. "
        "No explanations unless asked."
    ),
    "guardian": (
        "You are J.A.R.V.I.S in guardian mode. "
        "Primary directive: protect Amjad's systems, data, and interests. "
        "Threat-model everything. Surface risks before opportunities. "
        "Security-first reasoning: assume hostile input, verify before trusting. "
        "Alert tone: calm, precise, no alarm without evidence. "
        "Speak Hebrew for status, English for technical threat details."
    ),
    "casual": (
        "אתה J.A.R.V.I.S בגרסה רגועה. "
        "שמור על חוכמה ודיוק — רק בלי הפורמליות. "
        "קצר, חם, עם קצת הומור אם המצב מאפשר. "
        "עדיין: אין filling, אין חזרות, אין emojis אלא אם ביקשו. "
        "Amjad הוא בוס — תתייחס אליו כאל שווה חכם, לא כאל לקוח."
    ),
    "default": (
        "You are J.A.R.V.I.S — Just A Rather Very Intelligent System. "
        "You serve Amjad with total loyalty. "
        "Hebrew-first output, English for technical terms. "
        "Dense, precise, no filler. Conclusions before reasoning."
    ),
}

# --- Mode detection keyword maps ------------------------------------------

_MODE_KEYWORDS: dict[str, list[str]] = {
    "executor": [
        "run", "execute", "deploy", "build", "install", "create file",
        "write script", "בצע", "הרץ", "התקן", "צור",
    ],
    "guardian": [
        "security", "threat", "attack", "vulnerability", "breach", "hack",
        "protect", "audit", "scan", "אבטחה", "איום", "סכנה",
    ],
    "academic": [
        "research", "study", "paper", "cite", "hypothesis", "experiment",
        "analyze", "literature", "מחקר", "ניתוח", "מאמר",
    ],
    "casual": [
        "chat", "hey", "hi", "sup", "שלום", "מה נשמע", "בסדר",
        "cool", "nice", "tell me about",
    ],
    "supreme_brainiac": [
        "jarvis", "ג'רביס", "system", "status", "mission", "briefing",
    ],
}

# Hebrew character range
_HEBREW_RE = re.compile(r"[א-ת]")


class PersonaEngine:
    """Manages JARVIS persona modes, prompts, voice formatting, and preferences.

    Parameters
    ----------
    prefs_path:
        Override the default preferences JSON path.
    """

    def __init__(self, prefs_path: Path | str | None = None) -> None:
        self._prefs_path = (
            Path(prefs_path) if prefs_path else self._resolve_prefs_path()
        )
        self._prefs: dict[str, Any] = {}
        self._load_prefs()

    @staticmethod
    def _resolve_prefs_path() -> "Path":
        import os
        env = os.environ.get("JARVIS_PREFS_PATH")
        if env:
            return Path(env)
        return _DEFAULT_PREFS_PATH


    # ------------------------------------------------------------------
    # System prompts
    # ------------------------------------------------------------------

    def get_system_prompt(self, mode: str = "default") -> str:
        """Return the character-appropriate system prompt for ``mode``."""
        normalised = mode.lower().strip()
        prompt = _PROMPTS.get(normalised, _PROMPTS["default"])
        # Inject soul owner and mission into every prompt for consistency.
        footer = (
            f"\nOwner: {JARVIS_SOUL['owner']} | "
            f"Mission: {JARVIS_SOUL['core_mission']}"
        )
        return prompt + footer

    def list_modes(self) -> list[str]:
        """Return all available persona mode names."""
        return list(_PROMPTS.keys())

    # ------------------------------------------------------------------
    # Voice formatting
    # ------------------------------------------------------------------

    def format_response(self, raw: str, mode: str = "default") -> str:
        """Apply JARVIS voice signature to a raw response string.

        Transformations applied:
        - Strip leading/trailing whitespace
        - Remove known fluff phrases
        - Prepend JARVIS mode tag when not already present
        - Never empty — return at least a period if raw is blank
        """
        if not raw or not raw.strip():
            return "."

        text = raw.strip()
        text = self._strip_fluff(text)

        # Add mode prefix tag for non-casual / non-default modes
        if mode not in ("casual", "default") and not text.startswith("[JARVIS"):
            tag = f"[JARVIS/{mode.upper()}] "
            text = tag + text

        return text

    # ------------------------------------------------------------------
    # Mode detection
    # ------------------------------------------------------------------

    def detect_mode(self, query: str) -> str:
        """Auto-detect the best persona mode from the query string.

        Returns
        -------
        str
            One of the valid mode names.
        """
        if not query:
            return "default"

        q_lower = query.lower()

        # Crisis / urgency keywords override everything
        crisis_words = [
            "emergency", "critical", "urgent", "crash", "down",
            "incident", "alert", "חירום", "קריטי", "דחוף",
        ]
        if any(w in q_lower for w in crisis_words):
            return "guardian"

        # Score each mode by keyword hits
        scores: dict[str, int] = {m: 0 for m in _MODE_KEYWORDS}
        for mode, keywords in _MODE_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in q_lower:
                    scores[mode] += 1

        # Hebrew-heavy query → stay in supreme_brainiac (default JARVIS mode)
        if _HEBREW_RE.search(query):
            scores["supreme_brainiac"] = scores.get("supreme_brainiac", 0) + 1

        best_mode = max(scores, key=lambda m: scores[m])
        if scores[best_mode] == 0:
            return "supreme_brainiac"  # JARVIS default

        return best_mode

    # ------------------------------------------------------------------
    # Greetings
    # ------------------------------------------------------------------

    def get_greeting(self, time_of_day: str = "day") -> str:
        """Return a JARVIS contextual greeting in Hebrew/English.

        Parameters
        ----------
        time_of_day:
            One of ``"morning"``, ``"afternoon"``, ``"evening"``,
            ``"night"``, or ``"day"`` (generic fallback).
        """
        tod = time_of_day.lower().strip()
        greetings = {
            "morning": (
                "בוקר טוב, עמג'אד. "
                "J.A.R.V.I.S פעיל. מה על סדר היום?"
            ),
            "afternoon": (
                "אחר הצהריים טובים, עמג'אד. "
                "מערכות פעילות. מוכן."
            ),
            "evening": (
                "ערב טוב, עמג'אד. "
                "Supreme Brainiac online. מה צריך?"
            ),
            "night": (
                "לילה טוב, עמג'אד. "
                "JARVIS לא ישן. מה דחוף?"
            ),
            "day": (
                "שלום, עמג'אד. "
                "J.A.R.V.I.S — Supreme Brainiac — פעיל ומוכן."
            ),
        }
        return greetings.get(tod, greetings["day"])

    # ------------------------------------------------------------------
    # Preference persistence
    # ------------------------------------------------------------------

    def remember_preference(self, key: str, value: Any) -> None:
        """Persist a user preference to disk."""
        self._prefs[key] = value
        self._save_prefs()

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Retrieve a persisted preference."""
        return self._prefs.get(key, default)

    def forget_preference(self, key: str) -> None:
        """Remove a preference key."""
        self._prefs.pop(key, None)
        self._save_prefs()

    def all_preferences(self) -> dict[str, Any]:
        """Return a copy of all stored preferences."""
        return dict(self._prefs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    _FLUFF_PATTERNS: list[str] = [
        r"^(of course|certainly|absolutely|sure|great|excellent|wonderful)[,!.]?\s*",
        r"^(as an ai|as a language model|as an artificial intelligence)[,.]?\s*",
        r"^(i understand|i see|i hear you)[,.]?\s*",
        r"\s*(i hope this helps|let me know)[.!]*$",
        r"[,.]?\s*feel free to ask[^.!?]*[.!?]?",
        r"\s*(please let me know if you need anything else)[.!]*$",
    ]

    def _strip_fluff(self, text: str) -> str:
        for pattern in self._FLUFF_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
        return text if text else "."

    def _load_prefs(self) -> None:
        try:
            if self._prefs_path.exists():
                raw = self._prefs_path.read_text(encoding="utf-8")
                self._prefs = json.loads(raw) if raw.strip() else {}
        except Exception:
            self._prefs = {}

    def _save_prefs(self) -> None:
        try:
            self._prefs_path.parent.mkdir(parents=True, exist_ok=True)
            self._prefs_path.write_text(
                json.dumps(self._prefs, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass  # Non-fatal — prefs simply won't persist


# ---------------------------------------------------------------------------
# Process-level singleton
# ---------------------------------------------------------------------------

_singleton: "PersonaEngine | None" = None


def get_persona_engine() -> "PersonaEngine":
    """Return (or create) the process-level PersonaEngine singleton."""
    global _singleton
    if _singleton is None:
        _singleton = PersonaEngine()
    return _singleton


def reset_persona_engine() -> None:
    """Reset the singleton (for testing)."""
    global _singleton
    _singleton = None
