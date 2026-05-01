"""Natural Language Understanding engine.

Rule-based intent classification and entity extraction — no ML models
required.  Designed for fast offline use in the JARVIS runtime.
"""

from __future__ import annotations

import re
from enum import Enum


class Intent(str, Enum):
    QUERY = "query"
    COMMAND = "command"
    NAVIGATE = "navigate"
    CREATE = "create"
    DELETE = "delete"
    UPDATE = "update"
    HELP = "help"
    GREET = "greet"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Keyword rule sets (ordered: first match wins inside classify_intent)
# ---------------------------------------------------------------------------

_GREET_WORDS = re.compile(
    r"\b(hello|hi|hey|shalom|greetings|good\s+morning|good\s+afternoon|good\s+evening)\b",
    re.IGNORECASE,
)
_GREET_HE = re.compile(r"שלום")

_HELP_WORDS = re.compile(r"\b(help|assist|support|guide|tutorial)\b|\?", re.IGNORECASE)

_QUERY_WORDS = re.compile(
    r"\b(what|who|how|when|where|why|which|tell\s+me|explain|describe|show\s+me)\b",
    re.IGNORECASE,
)

_CREATE_WORDS = re.compile(
    r"\b(create|make|build|add|generate|produce|write|new|spawn|init(ialise|ialize)?)\b",
    re.IGNORECASE,
)

_DELETE_WORDS = re.compile(
    r"\b(delete|remove|drop|erase|destroy|wipe|purge|uninstall)\b",
    re.IGNORECASE,
)

_UPDATE_WORDS = re.compile(
    r"\b(update|edit|modify|change|set|rename|move|patch|upgrade|fix|correct)\b",
    re.IGNORECASE,
)

_NAVIGATE_WORDS = re.compile(
    r"\b(go\s+to|open|navigate|visit|browse|launch|show|switch\s+to)\b",
    re.IGNORECASE,
)

_COMMAND_WORDS = re.compile(
    r"\b(run|execute|start|stop|restart|deploy|send|download|upload|install|enable|disable)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Entity extraction patterns
# ---------------------------------------------------------------------------

_RE_URL = re.compile(
    r"https?://[^\s\"'<>]+"
    r"|www\.[^\s\"'<>]+",
    re.IGNORECASE,
)
_RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_RE_NUMBER = re.compile(r"-?\b\d+(?:\.\d+)?\b")
_RE_QUOTE = re.compile(r'"([^"]*?)"|\'([^\']*?)\'')
_RE_PATH = re.compile(
    r"(?:/[^\s\"'<>]+)"          # absolute POSIX path
    r"|(?:[A-Za-z]:\\[^\s\"'<>]+)"  # Windows absolute path
    r"|(?:\./[^\s\"'<>]+)"       # relative ./something
)

# Hebrew character range: א-ת
_RE_HEBREW = re.compile(r"[א-ת]")
_RE_ASCII_ALPHA = re.compile(r"[a-zA-Z]")


class NLUEngine:
    """Rule-based NLU: intent classification + entity extraction."""

    # ------------------------------------------------------------------
    # Intent classification
    # ------------------------------------------------------------------

    def classify_intent(self, text: str) -> Intent:
        """Return the most likely :class:`Intent` for *text*.

        Priority order (highest first):
        GREET → HELP → QUERY → CREATE → DELETE → UPDATE → NAVIGATE →
        COMMAND → UNKNOWN.
        """
        if _GREET_WORDS.search(text) or _GREET_HE.search(text):
            return Intent.GREET
        if _HELP_WORDS.search(text):
            return Intent.HELP
        if _QUERY_WORDS.search(text):
            return Intent.QUERY
        if _CREATE_WORDS.search(text):
            return Intent.CREATE
        if _DELETE_WORDS.search(text):
            return Intent.DELETE
        if _UPDATE_WORDS.search(text):
            return Intent.UPDATE
        if _NAVIGATE_WORDS.search(text):
            return Intent.NAVIGATE
        if _COMMAND_WORDS.search(text):
            return Intent.COMMAND
        return Intent.UNKNOWN

    # ------------------------------------------------------------------
    # Entity extraction
    # ------------------------------------------------------------------

    def extract_entities(self, text: str) -> dict[str, list[str]]:
        """Extract structured entities from *text*.

        Returns a dict with keys:
        ``numbers``, ``urls``, ``emails``, ``quotes``, ``paths``.
        """
        urls = _RE_URL.findall(text)
        # Remove URLs from text before extracting emails / paths to avoid
        # false positives (e.g. user@host appearing inside a URL).
        text_no_url = _RE_URL.sub(" ", text)

        emails = _RE_EMAIL.findall(text_no_url)
        text_no_email = _RE_EMAIL.sub(" ", text_no_url)

        numbers = _RE_NUMBER.findall(text)

        # Quotes: take first capturing group that matched
        quotes = [
            g1 if g1 is not None else g2
            for g1, g2 in _RE_QUOTE.findall(text)
        ]

        paths = _RE_PATH.findall(text_no_email)

        return {
            "numbers": numbers,
            "urls": urls,
            "emails": emails,
            "quotes": quotes,
            "paths": paths,
        }

    # ------------------------------------------------------------------
    # Full analysis
    # ------------------------------------------------------------------

    def analyze(self, text: str) -> dict:
        """Return a combined analysis dict.

        Keys: ``text``, ``intent``, ``entities``, ``confidence``.

        *confidence* is a heuristic 0–1 float based on how many intent
        keywords were matched.
        """
        intent = self.classify_intent(text)
        entities = self.extract_entities(text)

        # Confidence heuristic: count matched keyword groups
        matched = sum([
            bool(_GREET_WORDS.search(text) or _GREET_HE.search(text)),
            bool(_HELP_WORDS.search(text)),
            bool(_QUERY_WORDS.search(text)),
            bool(_CREATE_WORDS.search(text)),
            bool(_DELETE_WORDS.search(text)),
            bool(_UPDATE_WORDS.search(text)),
            bool(_NAVIGATE_WORDS.search(text)),
            bool(_COMMAND_WORDS.search(text)),
        ])
        if intent is Intent.UNKNOWN:
            confidence = 0.1
        elif matched >= 2:
            confidence = 0.9
        else:
            confidence = 0.75

        return {
            "text": text,
            "intent": intent.value,
            "entities": entities,
            "confidence": confidence,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def is_question(self, text: str) -> bool:
        """Return *True* if *text* looks like a question."""
        stripped = text.strip()
        if stripped.endswith("?"):
            return True
        if _QUERY_WORDS.search(stripped):
            return True
        return False

    def get_language(self, text: str) -> str:
        """Detect language: ``"he"`` | ``"en"`` | ``"unknown"``."""
        hebrew_chars = len(_RE_HEBREW.findall(text))
        ascii_chars = len(_RE_ASCII_ALPHA.findall(text))
        total = hebrew_chars + ascii_chars
        if total == 0:
            return "unknown"
        if hebrew_chars / total > 0.5:
            return "he"
        if ascii_chars / total > 0.3:
            return "en"
        return "unknown"
