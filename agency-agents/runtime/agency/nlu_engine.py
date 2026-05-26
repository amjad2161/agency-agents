"""
NLU Engine — Pass 23
Natural Language Understanding: intent detection + entity extraction
Backends: spaCy (he/en) → regex rule-based → MockNLU
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional

# ── dataclass ─────────────────────────────────────────────────────────────────

@dataclass
class NLUResult:
    intent: str
    entities: dict
    confidence: float
    lang: str  # "he" / "en" / "auto"

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "entities": self.entities,
            "confidence": self.confidence,
            "lang": self.lang,
        }


# ── intent definitions ─────────────────────────────────────────────────────────

INTENTS = [
    "question", "command", "greeting", "farewell", "emotion_query",
    "skill_request", "memory_store", "memory_recall", "robot_command", "unknown",
]

# Hebrew patterns
HE_GREET      = re.compile(r"שלום(?![א-ת])|היי|הי(?!\S)|בוקר טוב|ערב טוב|צהריים טובים", re.UNICODE)
HE_FAREWELL   = re.compile(r"להתראות|ביי|שלום לך|בבקשה ללכת|נתראה", re.UNICODE)
HE_COMMAND    = re.compile(r"תעשה|בצע|הפעל|תפתח|תסגור|תזיז|תשלח|תצלם|תכתוב|תמחק", re.UNICODE)
HE_QUESTION   = re.compile(r"^(מה|איך|מתי|איפה|למה|מי|האם|כמה|האם)", re.UNICODE)
HE_EMOTION    = re.compile(r"מה שלומך|מה קורה|איך אתה|איך את|מרגיש|מרגישה", re.UNICODE)
HE_MEMORY_S   = re.compile(r"תזכור|שמור ב|רשום ש", re.UNICODE)
HE_MEMORY_R   = re.compile(r"מה זכרת|מה שמרת|תזכיר לי|מה אמרתי", re.UNICODE)
HE_ROBOT      = re.compile(r"תזוז|קדימה|אחורה|שמאלה|ימינה|עצור|סובב|הסתכל", re.UNICODE)
HE_SKILL      = re.compile(r"skill|מיומנות|הפעל יכולת", re.UNICODE | re.IGNORECASE)

# English patterns
EN_GREET      = re.compile(r"\b(hi|hello|hey|good morning|good afternoon|good evening|howdy)\b", re.I)
EN_FAREWELL   = re.compile(r"\b(bye|goodbye|see you|farewell|cya|later)\b", re.I)
EN_QUESTION   = re.compile(r"^(what|how|when|where|why|who|is|are|do|does|can|could|would|will)\b", re.I)
EN_COMMAND    = re.compile(r"^(do|run|execute|start|stop|open|close|move|send|take|write|delete|fetch|get|set|show|list)\b", re.I)
EN_EMOTION    = re.compile(r"how are you|how do you feel|how's it going|you okay|are you (ok|well|happy|sad)", re.I)
EN_MEMORY_S   = re.compile(r"\b(remember|save|store|note) (that|this|it)\b", re.I)
EN_MEMORY_R   = re.compile(r"\b(what did i say|recall|remind me|what do you remember)\b", re.I)
EN_ROBOT      = re.compile(r"\b(move|go|forward|backward|left|right|stop|rotate|turn|look)\b", re.I)
EN_SKILL      = re.compile(r"\bskill\b", re.I)

# ── entity extraction ──────────────────────────────────────────────────────────

# Israeli date/time: dd/mm/yyyy HH:MM or dd/mm/yyyy
TIME_RE     = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4})(\s+\d{1,2}:\d{2})?\b")
NUMBER_RE   = re.compile(r"\b\d+(?:\.\d+)?\b")
SKILL_RE    = re.compile(r"\b([a-z][a-z0-9_-]{2,})\b", re.I)
# Very simple PERSON heuristic: Title-cased sequences of 2+ words
PERSON_RE   = re.compile(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)+)\b")
# Hebrew names: 2+ consecutive Hebrew words
HE_PERSON   = re.compile(r"[א-ת]{2,}(?:\s+[א-ת]{2,})+")
LOCATION_RE = re.compile(
    r"(?<![א-ת])(tel aviv|jerusalem|haifa|beer sheva|netanya|rishon|holon|petah tikva)"
    r"|[לבמכהוש]?(תל אביב|ירושלים|חיפה|באר שבע|נתניה|ראשון לציון|רחובות|אשדוד|אשקלון)",
    re.I | re.UNICODE,
)

_SKILL_SLUGS = {
    "search", "weather", "calendar", "email", "translate", "news", "music",
    "alarm", "reminder", "vision", "speech", "robot", "camera", "nlu",
}


def _extract_entities(text: str) -> dict:
    entities: dict = {}

    # TIME
    tm = TIME_RE.search(text)
    if tm:
        entities["TIME"] = tm.group(0).strip()

    # LOCATION
    lm = LOCATION_RE.search(text)
    if lm:
        entities["LOCATION"] = lm.group(0).strip()

    # PERSON (English)
    pm = PERSON_RE.search(text)
    if pm:
        entities["PERSON"] = pm.group(1)
    else:
        # Hebrew person
        hpm = HE_PERSON.search(text)
        if hpm:
            entities["PERSON"] = hpm.group(0)

    # SKILL_SLUG
    for tok in SKILL_RE.findall(text):
        if tok.lower() in _SKILL_SLUGS:
            entities["SKILL_SLUG"] = tok.lower()
            break

    # NUMBER
    nums = NUMBER_RE.findall(text)
    if nums:
        entities["NUMBER"] = nums[0]

    return entities


# ── language detection ─────────────────────────────────────────────────────────

_HE_CHAR = re.compile(r"[א-ת]")

def _detect_lang(text: str) -> str:
    he_chars = len(_HE_CHAR.findall(text))
    if he_chars > len(text) * 0.15:
        return "he"
    ascii_chars = sum(c.isascii() and c.isalpha() for c in text)
    if ascii_chars > 0:
        return "en"
    return "auto"


# ── intent classification (regex) ─────────────────────────────────────────────

def _classify_intent_regex(text: str, lang: str) -> tuple[str, float]:
    t = text.strip()
    if lang == "he":
        if HE_GREET.search(t):      return "greeting", 0.85
        if HE_FAREWELL.search(t):   return "farewell", 0.85
        if HE_ROBOT.search(t):      return "robot_command", 0.80
        if HE_MEMORY_S.search(t):   return "memory_store", 0.80
        if HE_MEMORY_R.search(t):   return "memory_recall", 0.80
        if HE_SKILL.search(t):      return "skill_request", 0.75
        if HE_EMOTION.search(t):    return "emotion_query", 0.80
        if HE_COMMAND.search(t):    return "command", 0.75
        if HE_QUESTION.search(t):   return "question", 0.75
        return "unknown", 0.40
    else:
        if EN_GREET.search(t):      return "greeting", 0.90
        if EN_FAREWELL.search(t):   return "farewell", 0.90
        if EN_ROBOT.search(t):      return "robot_command", 0.80
        if EN_MEMORY_S.search(t):   return "memory_store", 0.80
        if EN_MEMORY_R.search(t):   return "memory_recall", 0.80
        if EN_SKILL.search(t):      return "skill_request", 0.78
        if EN_EMOTION.search(t):    return "emotion_query", 0.85
        if EN_COMMAND.search(t):    return "command", 0.78
        if EN_QUESTION.search(t):   return "question", 0.78
        return "unknown", 0.40


# ── backends ───────────────────────────────────────────────────────────────────

class _SpaCyBackend:
    """spaCy NER + rule-based intent on top."""

    def __init__(self):
        import spacy  # noqa: F401 — may raise ImportError
        self._nlp_en = None
        self._nlp_he = None
        try:
            import spacy
            self._nlp_en = spacy.load("en_core_web_sm")
        except Exception:
            pass
        try:
            import spacy
            self._nlp_he = spacy.load("he_core_news_sm")
        except Exception:
            pass
        if self._nlp_en is None and self._nlp_he is None:
            raise RuntimeError("No spaCy models available")

    def parse(self, text: str) -> NLUResult:
        lang = _detect_lang(text)
        nlp = self._nlp_he if lang == "he" else (self._nlp_en or self._nlp_he)
        if nlp is None:
            raise RuntimeError("Model unavailable")
        doc = nlp(text)
        entities = {}
        for ent in doc.ents:
            entities[ent.label_] = ent.text
        # Merge regex entities (add missing)
        for k, v in _extract_entities(text).items():
            if k not in entities:
                entities[k] = v
        intent, conf = _classify_intent_regex(text, lang)
        return NLUResult(intent, entities, conf + 0.05, lang)


class _RegexBackend:
    def parse(self, text: str) -> NLUResult:
        lang = _detect_lang(text)
        intent, conf = _classify_intent_regex(text, lang)
        entities = _extract_entities(text)
        return NLUResult(intent, entities, conf, lang)


class _MockNLU:
    def parse(self, text: str) -> NLUResult:
        return NLUResult("unknown", {}, 0.5, "auto")


# ── public engine ──────────────────────────────────────────────────────────────

class NLUEngine:
    """
    NLU pipeline: spaCy → regex → MockNLU.
    All external imports are guarded.
    """

    def __init__(self):
        self._backend = self._init_backend()

    def _init_backend(self):
        try:
            b = _SpaCyBackend()
            return b
        except Exception:
            pass
        return _RegexBackend()

    def parse(self, text: str) -> NLUResult:
        try:
            return self._backend.parse(text)
        except Exception:
            return _MockNLU().parse(text)

    @property
    def backend_name(self) -> str:
        return type(self._backend).__name__
        return type(self._backend).__name__
