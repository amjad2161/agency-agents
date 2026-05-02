"""JARVIS Personality Engine — Pass 20.

Configurable traits that shape how JARVIS formats and colours its output.
Reads from ~/.agency/config.toml [personality] section (or uses defaults).

Usage
-----
    from agency.personality import JarvisPersonality, get_personality

    p = get_personality()
    print(p.greet())
    print(p.format_response("Calculation complete.", context="math"))

Config
------
    [personality]
    name       = "JARVIS"
    language   = "he"          # "he" = Hebrew, "en" = English
    formality  = "formal"      # "formal" | "casual"
    response_style = "concise" # "concise" | "verbose"
    catchphrases = ["בבקשה", "כמובן"]  # list of phrases

CLI
---
    agency personality set name "JARVIS" language he formality formal
    agency personality show
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Hebrew phrase banks
# ---------------------------------------------------------------------------

_HE_FORMAL_PHRASES = [
    "בבקשה",          # please / here you go
    "כמובן",          # of course
    "מייד",           # right away
    "ביצוע...",       # executing...
    "המשימה הושלמה",  # task completed
    "בהחלט",          # certainly
    "אני מבין",       # I understand
    "הנה התוצאה",     # here is the result
    "כרצונך",         # as you wish
    "עומד לרשותך",    # at your service
]

_HE_CASUAL_PHRASES = [
    "ברור",           # sure
    "נעשה",           # done / got it
    "יאללה",          # let's go
    "חכה רגע",        # wait a second
    "קיבלתי",         # received / got it
    "פצצה",           # awesome (lit. bomb)
    "סבבה",           # cool / fine
]

_EN_FORMAL_PHRASES = [
    "Of course.",
    "Right away.",
    "Certainly.",
    "Understood.",
    "Executing...",
    "Task completed.",
    "At your service.",
    "Affirmative.",
]

_EN_CASUAL_PHRASES = [
    "Sure!",
    "Got it.",
    "On it.",
    "Done.",
    "Roger that.",
]

# Greeting templates per language × formality
_GREETINGS: Dict[str, Dict[str, str]] = {
    "he": {
        "formal": "שלום. אני {name}, ממתין להוראותיך.",
        "casual": "היי! אני {name}. מה אפשר לעשות בשבילך?",
    },
    "en": {
        "formal": "Good day. I am {name}, ready to assist you.",
        "casual": "Hey! I'm {name}. How can I help?",
    },
}


# ---------------------------------------------------------------------------
# Personality dataclass
# ---------------------------------------------------------------------------

@dataclass
class JarvisPersonality:
    """Configurable traits that govern JARVIS output formatting."""

    name: str = "JARVIS"
    language: str = "he"          # "he" | "en"
    formality: str = "formal"     # "formal" | "casual"
    response_style: str = "concise"  # "concise" | "verbose"
    catchphrases: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Populate default catchphrases if none provided
        if not self.catchphrases:
            self.catchphrases = self._default_phrases()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _default_phrases(self) -> List[str]:
        if self.language == "he":
            pool = (_HE_FORMAL_PHRASES if self.formality == "formal"
                    else _HE_CASUAL_PHRASES)
        else:
            pool = (_EN_FORMAL_PHRASES if self.formality == "formal"
                    else _EN_CASUAL_PHRASES)
        return list(pool)

    def random_phrase(self) -> str:
        """Return a random catchphrase from the configured pool."""
        if not self.catchphrases:
            return ""
        return random.choice(self.catchphrases)

    # ------------------------------------------------------------------
    # Greeting
    # ------------------------------------------------------------------

    def greet(self) -> str:
        """Return a startup greeting in the configured language/formality."""
        lang = self.language if self.language in _GREETINGS else "en"
        fml  = self.formality if self.formality in ("formal", "casual") else "formal"
        tmpl = _GREETINGS[lang][fml]
        return tmpl.format(name=self.name)

    # ------------------------------------------------------------------
    # Response formatter
    # ------------------------------------------------------------------

    def format_response(self, text: str, context: str = "") -> str:
        """Wrap *text* with personality prefix/suffix based on traits.

        Parameters
        ----------
        text:    The raw assistant output.
        context: Optional hint (e.g. "error", "done", "query") for choosing
                 an appropriate prefix phrase.
        """
        phrase = self._pick_phrase(context)

        if self.response_style == "concise":
            # Short: just prefix + text (no fluff)
            if phrase:
                return f"{phrase} {text}"
            return text

        # verbose: prefix, text, suffix
        suffix = self._suffix(context)
        parts = []
        if phrase:
            parts.append(phrase)
        parts.append(text)
        if suffix:
            parts.append(suffix)
        return " ".join(parts)

    def _pick_phrase(self, context: str) -> str:
        ctx = (context or "").lower()
        if self.language == "he":
            if "error" in ctx or "fail" in ctx:
                return "מצטער," if self.formality == "formal" else "אופס,"
            if "done" in ctx or "complete" in ctx or "success" in ctx:
                return "המשימה הושלמה." if self.formality == "formal" else "נעשה!"
            if "wait" in ctx or "running" in ctx or "executing" in ctx:
                return "מייד..."
            return self.random_phrase()
        else:
            if "error" in ctx or "fail" in ctx:
                return "I apologise." if self.formality == "formal" else "Oops."
            if "done" in ctx or "complete" in ctx or "success" in ctx:
                return "Task completed." if self.formality == "formal" else "Done!"
            if "wait" in ctx or "running" in ctx:
                return "Working on it..."
            return self.random_phrase()

    def _suffix(self, context: str) -> str:
        if self.language == "he":
            return "האם יש עוד שאוכל לעשות?" if self.formality == "formal" else "עוד משהו?"
        return "Is there anything else I can assist you with?" if self.formality == "formal" else "Anything else?"

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "language": self.language,
            "formality": self.formality,
            "response_style": self.response_style,
            "catchphrases": self.catchphrases,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JarvisPersonality":
        return cls(
            name=data.get("name", "JARVIS"),
            language=data.get("language", "he"),
            formality=data.get("formality", "formal"),
            response_style=data.get("response_style", "concise"),
            catchphrases=list(data.get("catchphrases", [])),
        )


# ---------------------------------------------------------------------------
# Config-file integration
# ---------------------------------------------------------------------------

def _load_toml_personality() -> Optional[Dict[str, Any]]:
    """Try to load [personality] section from ~/.agency/config.toml."""
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return None

    path = Path.home() / ".agency" / "config.toml"
    if not path.exists():
        return None
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
        return data.get("personality")
    except Exception:
        return None


_SINGLETON: Optional[JarvisPersonality] = None


def get_personality() -> JarvisPersonality:
    """Return the global JarvisPersonality instance (loaded from config or default)."""
    global _SINGLETON
    if _SINGLETON is not None:
        return _SINGLETON

    toml_section = _load_toml_personality()
    if toml_section:
        _SINGLETON = JarvisPersonality.from_dict(toml_section)
    else:
        _SINGLETON = JarvisPersonality()

    return _SINGLETON


def set_personality(**kwargs: Any) -> JarvisPersonality:
    """Update the global personality with keyword overrides and return it."""
    global _SINGLETON
    p = get_personality()
    for key, val in kwargs.items():
        if hasattr(p, key):
            object.__setattr__(p, key) if False else setattr(p, key, val)
    # Refresh catchphrases if language/formality changed
    if "language" in kwargs or "formality" in kwargs:
        if not kwargs.get("catchphrases"):
            p.catchphrases = p._default_phrases()
    _SINGLETON = p
    return p
