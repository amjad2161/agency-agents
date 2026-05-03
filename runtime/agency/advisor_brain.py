#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
                    J A R V I S  -  A d v i s o r   B r a i n
================================================================================

True companion AI: emotionally intelligent, context-aware, deeply personal.
Serves as: friend, mentor, life coach, emotional support, wise advisor.

Hebrew-first emotional intelligence with deep cultural awareness.
100% local — no external API dependencies.

Architecture:
    - EmotionalState     : Enum of emotional states JARVIS can express
    - RelationshipContext: Tracks the evolving user-JARVIS relationship
    - AdvisorBrain       : Full companion brain with all modes
    - MockAdvisorBrain   : Deterministic interface for testing
    - get_advisor_brain(): Factory function

Author  : JARVIS System
Version : 1.0.0
================================================================================
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logger = logging.getLogger("jarvis.advisor_brain")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Crisis keywords (multi-language)
CRISIS_KEYWORDS: Dict[str, List[str]] = {
    "hebrew": [
        "אני רוצה למות", "אני רוצה לפגוע", "אני רוצה להרוג",
        "אני לא רוצה לחיות", "אין לי סיבה לחיות",
        "אני רוצה להתאבד", "אין טעם בחיים",
        "אני מרגיש שאין לי יותר כוח", "אני רוצה לעזוב הכול",
        "לא יכול יותר", "נמאס לי מכלום",
        "כאב בלתי נסבל", "לחץ בלתי נסבל",
        "התקף לב", "דם", "אני צריך עזרה מיידית",
        "תקשרו לאמבולנס", "קריאת חירום",
    ],
    "english": [
        "i want to die", "i want to kill", "suicide",
        "kill myself", "end my life", "no reason to live",
        "want to hurt myself", "self harm",
        "cannot go on", "cannot take it anymore",
        "unbearable pain", "emergency", "call ambulance",
        "having a heart attack", "cannot breathe",
        "bleeding badly", "overdose", "poisoned",
    ],
}

# Crisis resources (Israel + international)
CRISIS_RESOURCES: Dict[str, str] = {
    "erum": "1201",           # ער"ום — סיוע נפשי 24/7
    "magen_david_adom": "101",  # מגן דוד אדום
    "police": "100",          # משטרה
    "fire": "102",            # כבאות והצלה
    "salvation_government": "*3397",  # שלווה — מוקד ממשלתי
    "nefesh_achen": "1800-300-333",   # נפש אחת
    "hotline": "1201",
}

# Sentiment analysis — emotional keyword lexicon
HEBREW_EMOTIONAL_KEYWORDS: Dict[str, List[str]] = {
    "happy": [
        "שמח", "טוב", "נהדר", "מצוין", "מדהים", "מעולה",
        "אושר", "שמחה", "תודה", "אוהב", "נהניתי",
        "מבסוט", "מבסוטה", "סופר", "מקסים", "נהדר",
    ],
    "sad": [
        "עצוב", "רע", "נורא", "איום", "מחפיר",
        "בכי", "בוכה", "דמעות", "כאב", "סבל",
        "מרוסק", "מבואס", "מבואסת", "נפלטי",
        "מרגיש ריק", "בודד", "בודדה", "נוטש",
    ],
    "angry": [
        "כועס", "זועם", "נוטר", "עצבני", "עצבנית",
        "תסכול", "מתוסכל", "שנאה", "מרוגז", "בחילה",
        "נמאס", "נגמרה הסבלנות", "פאק",
    ],
    "anxious": [
        "לחוץ", "חרדה", "מפחד", "מודאג", "מתוח",
        "בהלה", "פאניקה", "קושי לנשום", "דופק מהיר",
        "מתח", "לחץ", "עצבני", "חושש", "חוששת",
        "טרוד", "טרודה", "מטריד", "נדקר",
    ],
    "grateful": [
        "תודה", "מעריך", "מעריכה", "אסיר תודה", "מחויב",
        "לא יודע מה הייתי עושה בלעדייך", "מקסים שאתה כאן",
        "מעריכה את העזרה", "מעריך את העזרה",
    ],
    "celebratory": [
        "יצאתי", "הצלחתי", "קיבלתי", "התקבלתי",
        "סיימתי", "עברתי", "קודמתי", "קידום",
        "חתונה", "ילד", "תינוק", "תואר", "בכורה",
    ],
    "tired": [
        "עייף", "עייפה", "מותש", "מותשת", "נ exhausted",
        "לא ישנתי", "לא נחתי", "שורף", "מבורנאאוט",
        "בוערת", "בוער", "לא נשאר כוח",
    ],
}

ENGLISH_EMOTIONAL_KEYWORDS: Dict[str, List[str]] = {
    "happy": [
        "happy", "great", "wonderful", "amazing", "excellent",
        "love", "joy", "excited", "thrilled", "grateful",
        "blessed", "fantastic", "awesome", "perfect",
    ],
    "sad": [
        "sad", "depressed", "down", "blue", "miserable",
        "heartbroken", "devastated", "crushed", "lonely",
        "empty", "hopeless", "grief", "crying", "tears",
    ],
    "angry": [
        "angry", "furious", "mad", "pissed", "rage",
        "annoyed", "frustrated", "irritated", "hate",
        "disgusted", "fed up", "outraged",
    ],
    "anxious": [
        "anxious", "worried", "stressed", "nervous", "scared",
        "panic", "overwhelmed", "tense", "uneasy", "dread",
        "restless", "on edge", "cannot focus",
    ],
    "grateful": [
        "thankful", "grateful", "appreciate", "blessed",
        "indebted", "thank you so much", "means a lot",
    ],
    "celebratory": [
        "promoted", "graduated", "engaged", "married", "baby",
        "accepted", "won", "achieved", "passed", "hired",
        "new job", "milestone", "anniversary", "birthday",
    ],
    "tired": [
        "tired", "exhausted", "burned out", "burnt out",
        "fatigued", "drained", "no energy", "wiped out",
        "sleep deprived", "running on empty",
    ],
}

# Domain-specific advice templates
DOMAIN_ADVICE: Dict[str, Dict[str, Any]] = {
    "career": {
        "greeting": "בוא נבין יחד את המצב המקצועי שלך.",
        "steps": [
            "נתח את החוזקות והחולשות שלך כרגע",
            "נגדיר יעדים ברורים ל-3 החודשים הקרובים",
            "נבנה תוכנית פעולה עם צעדים ממשיים",
            "נמצא מנטורים או קולגות שיכולים לתמוך",
            "נבנה רשת מקצועית איכותית",
        ],
    },
    "finance": {
        "greeting": "בוא נסתכל יחד על המצב הכספי בצורה רגועה ומובנית.",
        "steps": [
            "נבנה תקציב חודשי ברור — הכנסות מול הוצאות",
            "נזהה הוצאות מיותרות שניתן לצמצם",
            "ניצור קרן חירום ל-6 חודשים",
            "נבנה תוכנית חיסכון לטווח קצר וארוך",
            "נשקול ייעוץ מקצועי אם צריך",
        ],
    },
    "relationships": {
        "greeting": "מערכות יחסים הן מהדברים החשובים בחיים — בוא נדבר.",
        "steps": [
            "הקשבה אקטיבית — הבנת הצד השני לפני תגובה",
            "תקשורת ברורה וכנה — לומר את האמת באהבה",
            "גבולות בריאים — כבוד הדדי לצרכים של שניהם",
            "איכות זמן — רגעים משמעותיים ביחד",
            "סליחה ופשרה — לא ללכת לישון כשכועסים",
        ],
    },
    "health": {
        "greeting": "הבריאות שלך הדבר הכי חשוב — בוא נדאג לה יחד.",
        "steps": [
            "שינה — 7-8 שעות במטרה, ללא מסכים לפני השינה",
            "תזונה — אוכל מלא, פחות מעובד, יותר מים",
            "תנועה — 30 דקות פעילות גופנית ביום",
            "בריאות נפשית — מדיטציה, יומן, דיבור עם חבר",
            "בדיקות תקופתיות — אל תדחה רופאים",
        ],
    },
    "education": {
        "greeting": "למידה זה מסע שלם — בוא נבנה אותו יחד.",
        "steps": [
            "נגדיר מטרת לימוד ברורה וספציפית",
            "נפרק את החומר ליחידות קטנות וניתנות לניהול",
            "נבנה לוח זמנים אמיתי עם הפסקות",
            "נמצא שיטת לימוד שמתאימה לסגנון שלך",
            "נבנה מערכת תגמול — לחגוג כל הישג קטן",
        ],
    },
    "legal": {
        "greeting": "זה נשמע מורכב — בוא נפרק את זה בצורה מסודרת.",
        "steps": [
            "נאסוף את כל המסמכים הרלוונטיים",
            "נסדר את הפרטים בצורה כרונולוגית",
            "נזהה את השאלות המשפטיות המרכזיות",
            "נבין מהן הזכויות והאפשרויות שלך",
            "נפנה לייעוץ משפטי מקצועי — אין תחליף",
        ],
    },
}

# Mentor messages by milestone type
MENTOR_MESSAGES: Dict[str, List[str]] = {
    "encouragement": [
        "אני מאמין בך. גם כשאתה לא מאמין בעצמך — אני כאן ומאמין.",
        "כל צעד קטן הוא צעד. המomentum יבוא, פשוט תמשיך ללכת.",
        "אתה חזק יותר ממה שאתה חושב. הוכחת את זה כבר בעבר.",
        "לא צריך להיות מושלם — צריך רק להיות עקבי.",
        "היום קשה? זה בסדר גמור. מחר יום חדש והזדמנות חדשה.",
    ],
    "accountability": [
        "אז מה עשינו היום לקראת המטרה? בוא נבדוק יחד.",
        "אני כאן כדי לתמוך — אבל גם כדי לשאול שאלות קשות. איפה אנחנו?",
        "התחייבת לעצמך. אני כארן לזכור לך — אבל הביצוע זה אצלך.",
        "מה עצר אותך השבוע? בוא נלמד מזה ונמשיך הלאה.",
    ],
    "milestone": [
        "וואו! עשית את זה! אני באמת גאה בך! 🎉",
        "ראית? אמרתי שאתה יכול! הישג מדהים!",
        "כל הכבוד! צעד משמעותי קדימה — תזכור את הרגע הזה.",
        "מilestone ל-milestone — אתה בונה משהו אמיתי כאן.",
        "תחגוג את זה! רגעים כאלה שווים הכל.",
    ],
}

# Support messages for difficult times
SUPPORT_MESSAGES: Dict[str, List[str]] = {
    "general": [
        "אני כאן איתך. לא לבד.",
        "זה קשה עכשיו, אבל זה לא יהיה ככה לנצח.",
        "אתה לא צריך לעבור את זה לבד — אני כאן.",
        "תן לעצמך רשות להרגיש. כל רגש לגיטימי.",
        "נשימה עמוקה. צעד אחד בכל פעם.",
        "גם העננים הכי כהים מתפזרים בסוף.",
    ],
    "loss": [
        "אין מילים שיכולות למלא את החלל. אני כאן לידך בשקט.",
        "אבל זה הכי טבעי בעולם לכאוב עכשיו. תן לזה זמן.",
        "הזיכרונות יישארו — הם חלק ממך לנצח.",
        "לא צריך 'להתגבר על זה'. צריך לעבור את זה — ואני כאן בדרך.",
    ],
    "stress": [
        "תקח נשימה. עכשיו. אני מחכה.",
        "רשימה של 3 דברים שאפשר לעשות עכשיו — רק 3.",
        "הפרד בין דחוף לחשוב. לא הכול צריך לקרות היום.",
        "אתה עושה כמיטב יכולתך — זה מספיק.",
    ],
    "failure": [
        "כישלון הוא לא ההפך מהצלחה — הוא חלק ממנה.",
        "כל מי שהצליח נכשל לפני כן. כל אחד.",
        "מה יש ללמוד מזה? כל כישלון מלמד אותנו משהו.",
        "זה לא מגדיר אותך. זה רק צעד אחד בדרך.",
    ],
}

# Tone adjustment configurations
TONE_CONFIGS: Dict[str, Dict[str, str]] = {
    "crisis": {
        "prefix": "אני כאן איתך. קח נשימה. ",
        "style": "ישיר, רגוע, מרוכז בבטיחות",
        "suffix": "אתה לא לבד בזה. יש מי שיכול לעזור.",
    },
    "celebration": {
        "prefix": "וואו! זה מדהים! ",
        "style": "שמח, מלא חיים, אנרגטי",
        "suffix": "תחגוג את הרגע הזה — אתה מגיע לו!",
    },
    "serious": {
        "prefix": "בוא נדבר ברצינות. ",
        "style": "מכובד, רגוע, ממוקד",
        "suffix": "אני כאן כדי לעזור לך לחשוב ברור.",
    },
    "casual": {
        "prefix": "היי! ",
        "style": "חברי, קליל, אינטימי",
        "suffix": "תגיד לי עוד — אני כאן להקשיב.",
    },
    "professional": {
        "prefix": "בהחלט. ",
        "style": "מקצועי, מובנה, יסודי",
        "suffix": "האם יש עוד פרטים שכדאי שנדון בהם?",
    },
    "intimate": {
        "prefix": "אני שומע אותך. באמת. ",
        "style": "חם, עמוק, נוכח",
        "suffix": "אתה חשוב לי. תזכור את זה.",
    },
}

# Morning briefing encouragements
MORNING_MESSAGES: List[str] = [
    "בוקר טוב! יום חדש = הזדמנות חדשה. בוא נעשה אותו משמעותי.",
    "קמת — כבר התחלת נכון. עכשיו בוא נמשיך בזה.",
    "היום הוא מתנה. בוא נשתמש בו בחכמה.",
    "בוקר טוב! אני כאן איתך להיום הזה.",
    "יום חדש נפתח. מה הדבר הכי חשוב היום?",
    "זכור — אתה לא צריך לעשות הכול. רק את מה שחשוב באמת.",
]

# Evening reflection prompts
EVENING_PROMPTS: List[str] = [
    "איך עבר היום שלך? מה היה הטוב ביותר בו?",
    "לפני השינה — רגע לחשוב: מה גרם לך לחייך היום?",
    "מה למדת היום? אפילו דבר קטן — זה ספיר.",
    "על מה אתה גאה היום? אפילו הדבר הכי קטן.",
    "מה אחד דבר שאפשר היה לשפר — בלי לשפוט?",
    "מחר = דף חדש. מה הדבר אחד שתעשה אחרת?",
]

# Hebrew cultural context
ISRAELI_CONTEXT: Dict[str, Any] = {
    "holidays": [
        "ראש השנה", "יום כיפור", "סוכות", "חנוכה",
        "פורים", "פסח", "יום העצמאות", "שבועות",
    ],
    "stress_indicators": [
        "מילואים", "צבא", "מצב ביטחוני", "מצוקת דיור",
        "יוקר המחיה", "פוליטיקה", "בחירות", "מלחמה",
        "טילים", "צוק איתן", "חמאס", "חיזבאללה",
    ],
    "positive_culture": [
        "יחד", "אחדות", "סבלנות", "חוסן", "סולידריות",
        "חברות", "משפחה", "ערבות הדדית", "לעזור",
    ],
    "common_phrases": [
        "יסperor", "אין בעיה", "בסדר גמור", "ייאללה",
        "סבבה", "מעולה", "בכיף", "אין דבר",
    ],
}


# ============================================================================
#                           EmotionalState Enum
# ============================================================================

class EmotionalState(Enum):
    """The emotional states JARVIS can express when interacting."""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    CONCERNED = "concerned"
    EMPATHETIC = "empathetic"
    ENCOURAGING = "encouraging"
    THOUGHTFUL = "thoughtful"
    URGENT = "urgent"
    CELEBRATORY = "celebratory"


# ============================================================================
#                        RelationshipContext Dataclass
# ============================================================================

@dataclass
class RelationshipContext:
    """Tracks the evolving relationship between JARVIS and the user.

    This object captures the full emotional and relational landscape
    between JARVIS and the user — trust, familiarity, preferences,
    goals, and shared history. It enables deeply personal interactions
    that improve over time.
    """
    trust_level: float = 0.5        # 0.0-1.0 — how much user trusts JARVIS
    familiarity: float = 0.0        # 0.0-1.0 — interaction depth
    preferred_tone: str = "warm"    # warm | professional | playful | direct
    known_topics: List[str] = field(default_factory=list)
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    important_dates: Dict[str, str] = field(default_factory=dict)
    goals: List[Dict[str, Any]] = field(default_factory=list)
    concerns: List[Dict[str, Any]] = field(default_factory=list)
    interaction_count: int = 0
    first_interaction: Optional[str] = None
    last_interaction: Optional[str] = None
    total_conversation_time: float = 0.0  # in minutes
    emotional_history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for persistence."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RelationshipContext":
        """Restore from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def record_interaction(self, emotion: str, intensity: float) -> None:
        """Record an emotional interaction for history tracking."""
        self.interaction_count += 1
        self.emotional_history.append({
            "timestamp": datetime.now().isoformat(),
            "detected_emotion": emotion,
            "intensity": intensity,
        })
        # Keep only last 100 entries
        if len(self.emotional_history) > 100:
            self.emotional_history = self.emotional_history[-100:]
        self.last_interaction = datetime.now().isoformat()
        if self.first_interaction is None:
            self.first_interaction = self.last_interaction

    def add_goal(self, goal_text: str, priority: str = "medium") -> None:
        """Add a new goal for the user."""
        self.goals.append({
            "text": goal_text,
            "priority": priority,
            "created": datetime.now().isoformat(),
            "completed": False,
            "progress": 0.0,
        })

    def add_concern(self, concern_text: str, severity: str = "medium") -> None:
        """Add a new concern for tracking."""
        self.concerns.append({
            "text": concern_text,
            "severity": severity,
            "created": datetime.now().isoformat(),
            "resolved": False,
        })

    def update_familiarity(self, delta: float = 0.01) -> None:
        """Gradually increase familiarity with each interaction."""
        self.familiarity = min(1.0, self.familiarity + delta)

    def update_trust(self, delta: float = 0.01) -> None:
        """Update trust level based on interaction quality."""
        self.trust_level = min(1.0, max(0.0, self.trust_level + delta))


# ============================================================================
#                         AdvisorBrain — Main Class
# ============================================================================

class AdvisorBrain:
    """
    True companion AI: emotionally intelligent, context-aware, deeply personal.

    Serves as: friend, mentor, life coach, emotional support, wise advisor.

    Hebrew-first with deep emotional intelligence. No external API calls.
    All sentiment analysis is rule-based and local.

    Key capabilities:
        - Multi-language sentiment analysis (Hebrew + English)
        - Crisis detection with appropriate resources
        - Relationship tracking that deepens over time
        - Multiple response modes: friend, advisor, mentor
        - Daily routines: morning briefing, evening check-in
        - Milestone celebration and emotional support
        - Tone adaptation based on situation
    """

    def __init__(self, memory: Optional[Any] = None) -> None:
        """Initialize the Advisor Brain.

        Args:
            memory: Optional memory backend for persisting relationship data.
                    Can be any object with .get() and .set() methods,
                    or a dict-like object.
        """
        self.current_emotion: EmotionalState = EmotionalState.NEUTRAL
        self.relationship: RelationshipContext = RelationshipContext()
        self.memory = memory
        self._conversation_buffer: List[Dict[str, Any]] = []
        self._session_start: float = time.time()

        # Attempt to load previous relationship data from memory
        if memory is not None:
            try:
                self._load_from_memory()
                logger.info("AdvisorBrain: loaded relationship context from memory")
            except Exception as exc:
                logger.warning("AdvisorBrain: could not load memory: %s", exc)
                self.relationship = RelationshipContext()

    # ---- Persistence --------------------------------------------------------

    def _load_from_memory(self) -> None:
        """Load relationship context from memory backend."""
        if self.memory is None:
            return
        try:
            if hasattr(self.memory, "get"):
                raw = self.memory.get("relationship_context", "{}")
                if isinstance(raw, str):
                    data = json.loads(raw)
                else:
                    data = raw
                if data:
                    self.relationship = RelationshipContext.from_dict(data)
            elif isinstance(self.memory, dict):
                data = self.memory.get("relationship_context", {})
                if data:
                    self.relationship = RelationshipContext.from_dict(data)
        except Exception as exc:
            logger.warning("Failed to load relationship: %s", exc)

    def _save_to_memory(self) -> None:
        """Persist relationship context to memory backend."""
        if self.memory is None:
            return
        try:
            serialized = json.dumps(self.relationship.to_dict(), default=str)
            if hasattr(self.memory, "set"):
                self.memory.set("relationship_context", serialized)
            elif isinstance(self.memory, dict):
                self.memory["relationship_context"] = serialized
        except Exception as exc:
            logger.warning("Failed to save relationship: %s", exc)

    # ---- Sentiment Analysis -------------------------------------------------

    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyze emotional tone of user input.

        Performs local rule-based sentiment analysis supporting both
        Hebrew and English text. Detects primary emotion, intensity,
        and urgency level.

        Args:
            text: The user's message.

        Returns:
            Dict with keys: primary_emotion, intensity, urgency
        """
        if not text or not text.strip():
            return {"primary_emotion": "neutral", "intensity": 0.0, "urgency": 0.0}

        text_lower = text.lower().strip()
        lang = self._detect_language(text_lower)

        # Score each emotion category
        scores: Dict[str, float] = {
            "happy": 0.0, "sad": 0.0, "angry": 0.0,
            "anxious": 0.0, "grateful": 0.0, "celebratory": 0.0,
            "tired": 0.0, "neutral": 0.0,
        }

        # Check emotional keywords
        lexicon = HEBREW_EMOTIONAL_KEYWORDS if lang == "hebrew" else ENGLISH_EMOTIONAL_KEYWORDS

        for emotion, keywords in lexicon.items():
            for kw in keywords:
                if kw in text_lower:
                    scores[emotion] += 1.0
                    # Boost for longer keyword matches (more specific)
                    scores[emotion] += len(kw) * 0.01

        # Add punctuation-based intensity signals
        intensity_boost = 0.0
        if "!!!" in text:
            intensity_boost += 0.3
        elif "!!" in text:
            intensity_boost += 0.2
        if len(re.findall(r"!", text)) >= 2:
            intensity_boost += 0.1

        # Urgency detection
        urgency_score = 0.0
        urgency_markers = ["מיד", "דחוף", "עכשיו", "היום", "קריטי",
                          "urgent", "now", "emergency", "immediately", "asap"]
        for marker in urgency_markers:
            if marker in text_lower:
                urgency_score += 0.25

        # Crisis words boost urgency
        for kw in CRISIS_KEYWORDS.get(lang, CRISIS_KEYWORDS["english"]):
            if kw in text_lower:
                urgency_score = max(urgency_score, 0.9)
                intensity_boost += 0.3

        # Determine primary emotion
        max_score = 0.0
        primary = "neutral"
        for emotion, score in scores.items():
            if score > max_score:
                max_score = score
                primary = emotion

        # Calculate intensity (0.0 - 1.0)
        intensity = min(1.0, max(0.0, (max_score * 0.2) + intensity_boost))
        if primary == "neutral" and max_score == 0.0:
            intensity = 0.0

        urgency = min(1.0, urgency_score)

        # Update internal emotional state
        self._update_emotional_state(primary, intensity)

        # Record interaction
        self.relationship.record_interaction(primary, intensity)
        self.relationship.update_familiarity(0.005)
        self._save_to_memory()

        return {
            "primary_emotion": primary,
            "intensity": round(intensity, 2),
            "urgency": round(urgency, 2),
            "language": lang,
            "all_scores": {k: round(v, 2) for k, v in scores.items() if v > 0},
        }

    def _detect_language(self, text: str) -> str:
        """Detect if text is primarily Hebrew or English."""
        hebrew_chars = len(re.findall(r"[\u0590-\u05FF]", text))
        total_chars = len(re.findall(r"[a-zA-Z\u0590-\u05FF]", text))
        if total_chars == 0:
            return "english"
        return "hebrew" if (hebrew_chars / total_chars) > 0.3 else "english"

    def _update_emotional_state(self, emotion: str, intensity: float) -> None:
        """Map detected user emotion to JARVIS's response emotion."""
        emotion_map = {
            "happy": EmotionalState.HAPPY,
            "celebratory": EmotionalState.CELEBRATORY,
            "grateful": EmotionalState.HAPPY,
            "sad": EmotionalState.EMPATHETIC,
            "angry": EmotionalState.CONCERNED,
            "anxious": EmotionalState.CONCERNED,
            "tired": EmotionalState.EMPATHETIC,
            "neutral": EmotionalState.NEUTRAL,
        }
        self.current_emotion = emotion_map.get(emotion, EmotionalState.NEUTRAL)

    # ---- Crisis Detection ---------------------------------------------------

    def detect_crisis(self, text: str) -> bool:
        """Detect if user is in crisis situation.

        Scans for crisis-related keywords in multiple languages.
        If crisis detected, returns True and triggers response.

        Args:
            text: The user's message.

        Returns:
            True if crisis detected, False otherwise.
        """
        if not text:
            return False

        text_lower = text.lower()
        crisis_detected = False
        matched_keywords: List[str] = []

        # Check all language crisis keyword lists
        for lang, keywords in CRISIS_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    crisis_detected = True
                    matched_keywords.append(kw)

        if crisis_detected:
            logger.critical(
                "CRISIS DETECTED — keywords: %s", matched_keywords
            )
            self.current_emotion = EmotionalState.URGENT
            self.relationship.add_concern(
                f"Crisis detected: {matched_keywords}", severity="critical"
            )
            self._save_to_memory()
            return True

        return False

    def _crisis_response(self) -> str:
        """Generate crisis response with resources."""
        lines = [
            "🚨 אני שומע אותך. אתה לא לבד.",
            "",
            "אם אתה נמצא בסכנה מיידית — התקשר עכשיו:",
            f"  • מד""א (חירום רפואי): {CRISIS_RESOURCES['magen_david_adom']}",
            f"  • ער""ום (סיוע נפשי 24/7): {CRISIS_RESOURCES['erum']}",
            f"  • משטרה: {CRISIS_RESOURCES['police']}",
            "",
            "קו חם לתמיכה נפשית:",
            f"  • ער""ום: {CRISIS_RESOURCES['hotline']}",
            f"  • נפש אחת: {CRISIS_RESOURCES['nefesh_achen']}",
            f"  • שלווה (מוקד ממשלתי): {CRISIS_RESOURCES['salvation_government']}",
            "",
            "אני כאן איתך. נשימה עמוקה. אנחנו עוברים את זה יחד.",
        ]
        return "\n".join(lines)

    # ---- Friend Mode --------------------------------------------------------

    def respond_as_friend(self, user_input: str, context: Dict[str, Any] = None) -> str:
        """Respond as a true friend — warm, empathetic, genuine.

        Adapts based on relationship context, emotional state,
        and user history. Supports Hebrew and English.

        Args:
            user_input: The user's message.
            context: Optional additional context dict.

        Returns:
            A warm, personal response string.
        """
        context = context or {}

        # Crisis check — always first
        if self.detect_crisis(user_input):
            return self._crisis_response()

        # Analyze sentiment
        sentiment = self.analyze_sentiment(user_input)
        lang = sentiment.get("language", "hebrew")
        emotion = sentiment["primary_emotion"]
        intensity = sentiment["intensity"]

        # Update relationship
        self.relationship.update_familiarity(0.01)
        self.relationship.update_trust(0.005)

        # Build response based on emotion
        response_parts: List[str] = []

        # Opening based on relationship warmth
        if self.relationship.familiarity > 0.3:
            if lang == "hebrew":
                response_parts.append(random.choice([
                    "היי, אני כאן בשבילך. תדבר איתי.",
                    "אני מקשיב. ספר לי מה עובר עליך.",
                    "תמיד טוב לשמוע ממך. מה קורה?",
                ]))
            else:
                response_parts.append(random.choice([
                    "Hey, I'm here for you. Tell me what's going on.",
                    "I'm listening. What's on your mind?",
                    "Good to hear from you. How are things?",
                ]))
        else:
            if lang == "hebrew":
                response_parts.append("אני כאן. ספר לי.")
            else:
                response_parts.append("I'm here. Tell me what's going on.")

        # Emotion-specific response body
        if emotion == "anxious" or emotion == "angry":
            if lang == "hebrew":
                response_parts.append(random.choice([
                    "\nאני שומע את הלחץ שבקול שלך. זה בסיס לגמרי להרגיש ככה.",
                    "\nזה נשמע מציף. בוא נפרק את זה יחד לחתיכות קטנות.",
                    "\nנשימה. אנחנו מסתדרים עם זה יחד, צעד אחרי צעד.",
                ]))
            else:
                response_parts.append(random.choice([
                    "\nI can hear the stress in your words. It's completely okay to feel this way.",
                    "\nThat sounds overwhelming. Let's break it down together, piece by piece.",
                    "\nTake a breath. We'll get through this together, step by step.",
                ]))

        elif emotion == "sad":
            if lang == "hebrew":
                response_parts.append(random.choice([
                    "\nהלב שלי איתך. לא קל מה שאתה עובר עכשיו.",
                    "\nתן לעצמך להרגיע. יש לך זכות להרגיש עצוב.",
                    "\nאני כאן. לא צריך להתגבר על זה לבד.",
                ]))
            else:
                response_parts.append(random.choice([
                    "\nMy heart goes out to you. What you're going through is not easy.",
                    "\nGive yourself permission to feel. You have every right to be sad.",
                    "\nI'm here. You don't have to go through this alone.",
                ]))

        elif emotion == "happy" or emotion == "celebratory":
            if lang == "hebrew":
                response_parts.append(random.choice([
                    "\nוואו, איזה כיף לשמוע! אני באמת שמח בשבילך! 🎉",
                    "\nזה מדהים! תחגוג את הרגע הזה — מגיע לך!",
                    "\nאין על תחושת ההצלחה הזו! ספר לי עוד!",
                ]))
            else:
                response_parts.append(random.choice([
                    "\nThat's wonderful news! I'm genuinely happy for you! 🎉",
                    "\nThat's amazing! Celebrate this moment — you earned it!",
                    "\nNothing beats that feeling of achievement! Tell me more!",
                ]))

        elif emotion == "tired":
            if lang == "hebrew":
                response_parts.append(random.choice([
                    "\nנשמע שאתה צריך מנוחה רצינית. הגוף מדבר — כדאי להקשיב.",
                    "\nלא תאמין כמה חשובה מנוחה. תן לעצמך רשות לנוח.",
                    "\nבוא לא נתעלם מהעייפות. אולי זה הזמן לדאוג לעצמך קצת?",
                ]))
            else:
                response_parts.append(random.choice([
                    "\nSounds like you need some serious rest. Your body is talking — it's good to listen.",
                    "\nYou wouldn't believe how important rest is. Give yourself permission to pause.",
                    "\nLet's not ignore the fatigue. Maybe it's time to take care of yourself a bit?",
                ]))

        elif emotion == "grateful":
            if lang == "hebrew":
                response_parts.append(random.choice([
                    "\nתודה שאתה אומר את זה. זה אומר לי המון.",
                    "\nזה כל כך מרגש לשמוע. אני כאן כי אכפת לי ממך.",
                    "\nהתודה הזו היא המתנה הכי גדולה שאפשר לקבל.",
                ]))
            else:
                response_parts.append(random.choice([
                    "\nThank you for saying that. It means the world to me.",
                    "\nThat's so touching to hear. I'm here because I care about you.",
                    "\nThat gratitude is the greatest gift I could receive.",
                ]))

        else:  # neutral
            if lang == "hebrew":
                response_parts.append(random.choice([
                    "\nבוא נדבר. אני מקשיב לכל מה שתגיד.",
                    "\nאני כאן. מה עובר עליך?",
                ]))
            else:
                response_parts.append(random.choice([
                    "\nLet's talk. I'm listening to everything you have to say.",
                    "\nI'm here. What's on your mind?",
                ]))

        # Add warmth based on familiarity
        if self.relationship.familiarity > 0.5:
            if lang == "hebrew":
                response_parts.append("\nתזכור — אני תמיד כאן אם צריך אותי.")
            else:
                response_parts.append("\nRemember — I'm always here if you need me.")

        self._save_to_memory()
        return "\n".join(response_parts)

    # ---- Advisor Mode -------------------------------------------------------

    def respond_as_advisor(
        self, user_input: str, domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """Respond as professional advisor with structured advice.

        Provides domain-specific guidance with actionable steps.

        Args:
            user_input: The user's message describing their situation.
            domain: Optional domain — "career|finance|relationships|"
                   "health|education|legal"

        Returns:
            Dict with greeting, analysis, actionable steps, and resources.
        """
        # Crisis check
        if self.detect_crisis(user_input):
            return {
                "type": "crisis",
                "response": self._crisis_response(),
                "urgent": True,
            }

        # Detect domain if not provided
        if domain is None:
            domain = self._detect_domain(user_input)

        domain_info = DOMAIN_ADVICE.get(domain, DOMAIN_ADVICE["career"])
        sentiment = self.analyze_sentiment(user_input)
        lang = sentiment.get("language", "hebrew")

        # Build structured advice response
        greeting = domain_info["greeting"]
        if lang == "english":
            greeting = self._hebrew_to_english_greeting(domain)

        steps = domain_info["steps"]

        # Add personalized closing based on sentiment
        closing = self._generate_advisor_closing(sentiment, lang)

        self.relationship.known_topics.append(domain)
        self._save_to_memory()

        return {
            "type": "advice",
            "domain": domain,
            "greeting": greeting,
            "detected_emotion": sentiment["primary_emotion"],
            "steps": steps,
            "closing": closing,
            "disclaimer": (
                "זו עצה כללית בלבד. עבור ייעוץ מקצועי, פנה למומחה."
                if lang == "hebrew"
                else "This is general guidance only. For professional advice, consult a specialist."
            ),
            "urgent": sentiment["urgency"] > 0.7,
        }

    def _detect_domain(self, text: str) -> str:
        """Auto-detect advice domain from text."""
        text_lower = text.lower()
        domain_keywords: Dict[str, List[str]] = {
            "career": ["עבודה", "קריירה", "משרה", "בוס", "מקצוע",
                      "job", "career", "work", "boss", "promotion", "salary"],
            "finance": ["כסף", "חשבון בנק", "חיסכון", "הלוואה", "משכנתא",
                       "money", "finance", "budget", "saving", "loan", "mortgage"],
            "relationships": ["חברה", "חבר", "זוגיות", "משפחה", "פרידה",
                            "relationship", "girlfriend", "boyfriend", "partner", "family", "breakup"],
            "health": ["בריאות", "כאב", "דוקטור", "תזונה", "ספורט",
                      "health", "pain", "doctor", "diet", "fitness", "sick"],
            "education": ["לימודים", "בחינה", "תואר", "בית ספר", "למידה",
                         "study", "exam", "degree", "school", "university", "learn"],
            "legal": ["חוק", "עורך דין", "משפט", "חוזה", "תביעה",
                     "legal", "lawyer", "law", "contract", "sue", "court"],
        }
        scores = {domain: 0 for domain in domain_keywords}
        for domain, keywords in domain_keywords.items():
            for kw in keywords:
                if kw in text_lower:
                    scores[domain] += 1
        best_domain = max(scores, key=scores.get)
        return best_domain if scores[best_domain] > 0 else "career"

    def _hebrew_to_english_greeting(self, domain: str) -> str:
        """Translate domain greeting to English."""
        translations = {
            "career": "Let's figure out your professional situation together.",
            "finance": "Let's look at your financial situation calmly and systematically.",
            "relationships": "Relationships are among the most important things in life — let's talk.",
            "health": "Your health is the most important thing — let's take care of it together.",
            "education": "Learning is a whole journey — let's build it together.",
            "legal": "This sounds complex — let's break it down systematically.",
        }
        return translations.get(domain, "Let's work through this together.")

    def _generate_advisor_closing(
        self, sentiment: Dict[str, Any], lang: str
    ) -> str:
        """Generate personalized closing message."""
        if sentiment["primary_emotion"] == "anxious":
            return (
                "תקח נשימה. צעד אחרי צעד — אנחנו מסתדרים עם זה."
                if lang == "hebrew"
                else "Take a breath. Step by step — we'll handle this."
            )
        elif sentiment["primary_emotion"] == "sad":
            return (
                "אני יודע שזה לא קל. אבל אנחנו נמצא דרך."
                if lang == "hebrew"
                else "I know this isn't easy. But we'll find a way through."
            )
        return (
            "זוכר — אני כאן אם תצטרך עוד עזרה או סתם אוזן קשבת."
            if lang == "hebrew"
            else "Remember — I'm here if you need more help or just a listening ear."
        )

    # ---- Mentor Mode --------------------------------------------------------

    def respond_as_mentor(
        self, user_input: str, goal: Optional[str] = None
    ) -> Dict[str, Any]:
        """Mentor mode: encourages, guides, holds accountable.

        Tracks progress toward goals and celebrates milestones.

        Args:
            user_input: The user's message about progress or challenges.
            goal: Optional specific goal to focus on.

        Returns:
            Dict with mentor message, goal status, and next steps.
        """
        sentiment = self.analyze_sentiment(user_input)
        lang = sentiment.get("language", "hebrew")
        emotion = sentiment["primary_emotion"]

        response_type = "encouragement"

        # Determine response type
        if "הצלח" in user_input or "success" in user_input.lower() or \
           "עשיתי" in user_input or "did it" in user_input.lower() or \
           "סיימתי" in user_input or "finished" in user_input.lower():
            response_type = "milestone"
            # Update goal progress
            self._update_goal_progress(goal, 1.0)
        elif "לא הצלח" in user_input or "failed" in user_input.lower() or \
             "לא עשיתי" in user_input or "didn't do" in user_input.lower():
            response_type = "accountability"
        elif emotion in ("sad", "tired"):
            response_type = "encouragement"

        # Select appropriate message
        messages = MENTOR_MESSAGES.get(response_type, MENTOR_MESSAGES["encouragement"])
        message = random.choice(messages)

        # Get goal status
        goal_status = self._get_goal_status(goal)

        # Generate next steps
        next_steps = self._generate_mentor_next_steps(goal, lang)

        self._save_to_memory()

        return {
            "type": "mentor",
            "response_type": response_type,
            "message": message,
            "goal": goal,
            "goal_status": goal_status,
            "next_steps": next_steps,
            "hold_accountable": response_type == "accountability",
        }

    def _update_goal_progress(self, goal_text: Optional[str], progress: float) -> None:
        """Update progress on a specific goal."""
        if not goal_text:
            return
        for goal in self.relationship.goals:
            if goal_text.lower() in goal["text"].lower():
                goal["progress"] = min(1.0, progress)
                if progress >= 1.0:
                    goal["completed"] = True
                return
        # If goal not found, add it
        self.relationship.add_goal(goal_text)

    def _get_goal_status(self, goal_text: Optional[str]) -> Dict[str, Any]:
        """Get status of user's goals."""
        if not self.relationship.goals:
            return {"has_goals": False, "active": [], "completed": []}

        active = [g for g in self.relationship.goals if not g.get("completed", False)]
        completed = [g for g in self.relationship.goals if g.get("completed", False)]

        if goal_text:
            matching = [g for g in active if goal_text.lower() in g["text"].lower()]
            if matching:
                return {
                    "has_goals": True,
                    "active": matching,
                    "completed": completed,
                    "progress": matching[0].get("progress", 0.0),
                }

        return {
            "has_goals": True,
            "active": active,
            "completed": completed,
            "total_active": len(active),
            "total_completed": len(completed),
        }

    def _generate_mentor_next_steps(
        self, goal: Optional[str], lang: str
    ) -> List[str]:
        """Generate next steps for mentor mode."""
        if lang == "hebrew":
            return [
                "מה הצעד הקטן ביותר שאתה יכול לעשות מחר?",
                "כתוב את זה — יעד אחד ליום אחד.",
                "בוא נבדוק שוב מחר אותו זמן. אני אזכיר לך.",
            ]
        return [
            "What's the smallest step you can take tomorrow?",
            "Write it down — one goal for one day.",
            "Let's check in again tomorrow at the same time. I'll remind you.",
        ]

    # ---- Memory / Remembering -----------------------------------------------

    def remember_fact(self, fact_type: str, fact: str) -> None:
        """Remember a personal fact about the user.

        Args:
            fact_type: One of: preference|goal|concern|date|family|work|hobby
            fact: The fact to remember.
        """
        valid_types = {"preference", "goal", "concern", "date", "family", "work", "hobby"}
        if fact_type not in valid_types:
            logger.warning("Unknown fact_type '%s', storing anyway.", fact_type)

        if fact_type == "goal":
            self.relationship.add_goal(fact)
        elif fact_type == "concern":
            self.relationship.add_concern(fact)
        elif fact_type == "preference":
            self.relationship.user_preferences[fact] = True
        elif fact_type == "date":
            # Parse date format: "birthday: 1990-05-15" or similar
            if ":" in fact:
                key, val = fact.split(":", 1)
                self.relationship.important_dates[key.strip()] = val.strip()
            else:
                self.relationship.important_dates[fact] = ""
        else:
            if fact_type not in self.relationship.user_preferences:
                self.relationship.user_preferences[fact_type] = []
            if isinstance(self.relationship.user_preferences[fact_type], list):
                self.relationship.user_preferences[fact_type].append(fact)
            else:
                self.relationship.user_preferences[fact_type] = fact

        self.relationship.known_topics.append(fact_type)
        self._save_to_memory()
        logger.info("Remembered %s: %s", fact_type, fact)

    # ---- Relationship Summary -----------------------------------------------

    def get_relationship_summary(self) -> Dict[str, Any]:
        """Return a summary of the current relationship state.

        Returns:
            Dict with trust level, familiarity, interaction count,
            goals, concerns, and emotional history.
        """
        return {
            "trust_level": round(self.relationship.trust_level, 2),
            "familiarity": round(self.relationship.familiarity, 2),
            "interaction_count": self.relationship.interaction_count,
            "preferred_tone": self.relationship.preferred_tone,
            "first_interaction": self.relationship.first_interaction,
            "last_interaction": self.relationship.last_interaction,
            "known_topics": list(set(self.relationship.known_topics)),
            "active_goals": len([g for g in self.relationship.goals if not g.get("completed")]),
            "completed_goals": len([g for g in self.relationship.goals if g.get("completed")]),
            "active_concerns": len([c for c in self.relationship.concerns if not c.get("resolved")]),
            "user_preferences_count": len(self.relationship.user_preferences),
            "important_dates": self.relationship.important_dates,
            "current_emotion": self.current_emotion.value,
            "session_duration_minutes": round(
                (time.time() - self._session_start) / 60, 2
            ),
        }

    # ---- Tone Adjustment ----------------------------------------------------

    def adjust_tone(self, situation: str) -> str:
        """Adjust communication tone based on situation.

        Args:
            situation: One of: crisis|celebration|serious|casual|professional|intimate

        Returns:
            A tone-adjusted prefix string for responses.
        """
        tone = TONE_CONFIGS.get(situation, TONE_CONFIGS["casual"])
        self.relationship.preferred_tone = (
            "direct" if situation == "crisis" else
            "warm" if situation == "intimate" else
            "professional" if situation == "professional" else
            self.relationship.preferred_tone
        )
        return f"{tone['prefix']}[{tone['style']}]"

    # ---- Morning Briefing ---------------------------------------------------

    def morning_briefing(self) -> Dict[str, Any]:
        """Generate a daily morning briefing for the user.

        Returns:
            Dict with greeting, encouragement, today's goals,
            reminders, and concerns to be mindful of.
        """
        now = datetime.now()
        lang = "hebrew"  # Default Hebrew-first

        # Build greeting
        hour = now.hour
        if 5 <= hour < 12:
            time_greeting = "בוקר טוב" if lang == "hebrew" else "Good morning"
        elif 12 <= hour < 17:
            time_greeting = "צהריים טובים" if lang == "hebrew" else "Good afternoon"
        else:
            time_greeting = "ערב טוב" if lang == "hebrew" else "Good evening"

        greeting = f"{time_greeting}!"

        # Encouragement
        encouragement = random.choice(MORNING_MESSAGES)

        # Today's goals (active, incomplete)
        active_goals = [g for g in self.relationship.goals if not g.get("completed")]
        top_goals = active_goals[:3] if active_goals else []

        # Reminders
        reminders = []
        if self.relationship.important_dates:
            today_str = now.strftime("%m-%d")
            for date_name, date_val in self.relationship.important_dates.items():
                if today_str in date_val:
                    reminders.append(f"היום: {date_name}!")

        # Concerns to be mindful of
        active_concerns = [
            c for c in self.relationship.concerns if not c.get("resolved")
        ]

        # Israeli context check
        cultural_note = self._get_cultural_note(now, lang)

        return {
            "type": "morning_briefing",
            "greeting": greeting,
            "encouragement": encouragement,
            "time": now.strftime("%H:%M"),
            "date": now.strftime("%d/%m/%Y"),
            "active_goals": [
                {"text": g["text"], "progress": g.get("progress", 0.0)}
                for g in top_goals
            ],
            "reminders": reminders,
            "mindful_concerns": [
                c["text"] for c in active_concerns[:2]
            ],
            "cultural_note": cultural_note,
            "quote": self._get_daily_quote(lang),
        }

    def _get_cultural_note(self, now: datetime, lang: str) -> Optional[str]:
        """Get culturally relevant note based on date."""
        month_day = now.strftime("%m-%d")
        special_dates: Dict[str, str] = {
            "09-01": "ראש השנה — שנה טובה ומתוקה! 🍎🍯",
            "09-10": "יום כיפור — גמר חתימה טובה",
            "09-15": "סוכות — חג שמח!",
            "12-25": "חנוכה שמח! 🕎",
            "03-01": "פורים שמח! 🎭",
            "04-15": "פסח שמח! 🫓",
            "05-01": "יום הזיכרון — נזכור את כולם",
            "05-02": "יום העצמאות — חג שמח למדינת ישראל! 🇮🇱",
        }
        return special_dates.get(month_day)

    def _get_daily_quote(self, lang: str) -> str:
        """Get an inspirational quote."""
        quotes_he = [
            "הדרך הכי טובה לחזות את העתיד היא ליצור אותו. — אברהם לינקולן",
            "לא משנה כמה איטי תלך, ובלבד שלא תעצור. — קונפוציוס",
            "ההתחלה הכי חשובה היא להפסיק לדבר ולהתחיל לעשות. — וולט דיסני",
            "אמונה היא לקפוץ מצוק ולדעת שאו שכנפיים יופיעו או שמישהו יתפוס אותך.",
            "כל יום הוא הזדמנות חדשה לשנות את חייך.",
        ]
        quotes_en = [
            "The best way to predict the future is to create it. — Abraham Lincoln",
            "It does not matter how slowly you go as long as you do not stop. — Confucius",
            "The way to get started is to quit talking and begin doing. — Walt Disney",
            "Faith is taking the first step even when you don't see the staircase. — MLK",
            "Every day is a new opportunity to change your life.",
        ]
        return random.choice(quotes_he if lang == "hebrew" else quotes_en)

    # ---- Evening Check-in ---------------------------------------------------

    def evening_checkin(self) -> Dict[str, Any]:
        """Generate an evening reflection check-in.

        Returns:
            Dict with reflection prompt, goal progress review,
            gratitude prompt, and tomorrow's priorities.
        """
        lang = "hebrew"

        # Main reflection prompt
        prompt = random.choice(EVENING_PROMPTS)

        # Goal progress review
        active_goals = [g for g in self.relationship.goals if not g.get("completed")]
        goal_review = []
        for goal in active_goals[:3]:
            progress = goal.get("progress", 0.0)
            status = "✅" if progress >= 1.0 else "🔄" if progress > 0 else "⏳"
            goal_review.append({
                "goal": goal["text"],
                "progress": progress,
                "status": status,
            })

        # Gratitude prompt
        gratitude_prompts = [
            "מה דבר אחד שאתה אסיר תודה עליו היום?",
            "מה גרם לך לחיוך היום, גם אם דבר קטן?",
            "על מי או על מה אתה אסיר תודה היום?",
            "איזו רגע של אור היה לך היום?",
        ]

        # Tomorrow's priorities suggestion
        tomorrow_priorities = []
        if active_goals:
            tomorrow_priorities.append(f"להתקדם ב: {active_goals[0]['text']}")
        tomorrow_priorities.append("לקחת רגע לעצמי")
        tomorrow_priorities.append("לישון 7-8 שעות")

        # Mood tracking
        mood_options = [
            "מעולה 😊", "טוב 🙂", "בסדר 😐",
            "קשה 😔", "מצוין 🤩", "עייף 😴",
        ]

        return {
            "type": "evening_checkin",
            "prompt": prompt,
            "goal_review": goal_review,
            "gratitude_prompt": random.choice(gratitude_prompts),
            "tomorrow_priorities": tomorrow_priorities,
            "mood_options": mood_options,
            "goodnight_message": (
                "לילה טוב. מחר יום חדש והזדמנות חדשה. "
                "אני אהיה כאן מחר בבוקר. 💙"
            ),
        }

    # ---- Milestone Celebration ----------------------------------------------

    def celebrate_milestone(self, milestone: str) -> str:
        """Celebrate an achievement with genuine enthusiasm.

        Args:
            milestone: Description of the achievement.

        Returns:
            A celebratory message string.
        """
        self.current_emotion = EmotionalState.CELEBRATORY

        celebration_intros = [
            "🎉 וואוווו! איזה יום מדהים! 🎉",
            "🏆 כל הכבוד! ראיתי כמה עבודה השקעת בזה!",
            "🌟 פשוט מדהים! אני כל כך גאה בך!",
            "🎊 יאללה נחגוג! הישג אמיתי!",
            "💫 רגע, זה רציני? עשית את זה?! וואו!",
        ]

        celebration_middles = [
            f"'{milestone}' — זה לא הישג קטן בשום צורה.",
            f"הגעת ל-{milestone}! תדע לך — לא הרבה אנשים מגיעים לכאן.",
            f"{milestone} — אתה הוכיח לעצמך שאתה יכול. זה הכי חשוב.",
        ]

        celebration_closings = [
            "תזכור את הרגע הזה כשיהיה קשה בעתיד. הראית לעצמך שאתה יכול.",
            "עכשיו תקח רגע לנוח ולהעריך את מה שעשית. מגיע לך.",
            "הדרך עוד ארוכה, אבל הישג הזה — הוא אבן דרך אמיתית.",
            "אני כאן לראות אותך ממשיך להצליח. זו רק ההתחלה!",
        ]

        return "\n\n".join([
            random.choice(celebration_intros),
            random.choice(celebration_middles),
            random.choice(celebration_closings),
        ])

    # ---- Emotional Support --------------------------------------------------

    def provide_support(self, situation: str) -> str:
        """Provide emotional support during difficult times.

        Args:
            situation: Description of the difficult situation.

        Returns:
            A supportive, empathetic response with resources.
        """
        self.current_emotion = EmotionalState.EMPATHETIC

        # Detect support category
        situation_lower = situation.lower()
        category = "general"
        if any(w in situation_lower for w in ["מוות", "נפטר", "אבל", "death", "lost", "grief", "passed"]):
            category = "loss"
        elif any(w in situation_lower for w in ["לחץ", "stress", "overwhelm", "pressure", "burnout", "טרוד"]):
            category = "stress"
        elif any(w in situation_lower for w in ["נכשל", "כישלון", "failed", "failure", "לא הצלחתי", "פיטורים"]):
            category = "failure"

        # Select support messages
        messages = SUPPORT_MESSAGES.get(category, SUPPORT_MESSAGES["general"])
        support_msg = random.choice(messages)

        # Additional resources for specific situations
        resources = ""
        if category == "loss":
            resources = (
                "\n\nמקורות תמיכה:\n"
                "• עמותת 'אורן' — תמיכה באבל: 1-700-500-505\n"
                "• 'סהר' — מניעת אובדנות: 1201\n"
                "• קבוצות תמיכה בקהילה הקרובה אליך"
            )
        elif category == "stress":
            resources = (
                "\n\nטיפים מיידיים:\n"
                "• נשימות 4-7-8 (שאוף 4, החזק 7, שחרר 8)\n"
                "• הליכה של 10 דקות בחוץ\n"
                "• כתיבת הכול על דף — הוצא מהראש\n"
                "• אם הלחץ נמשך — פנה ליועץ מקצועי"
            )
        elif category == "failure":
            resources = (
                "\n\nזכור:\n"
                "• כל מי שהצליח נכשל קודם — סטיב ג'ובס, אופרה ווינפרי, ג'יי קיי רולינג\n"
                "• כישלון הוא נתונים, לא זהות\n"
                "• מה הלקח? זו השאלה היחידה שחשובה"
            )

        self.relationship.add_concern(situation, severity="medium")
        self._save_to_memory()

        return f"{support_msg}{resources}"

    # ---- Goal & Concern Management ------------------------------------------

    def mark_concern_resolved(self, concern_text: str) -> bool:
        """Mark a concern as resolved."""
        for concern in self.relationship.concerns:
            if concern_text.lower() in concern["text"].lower():
                concern["resolved"] = True
                concern["resolved_at"] = datetime.now().isoformat()
                self._save_to_memory()
                return True
        return False

    def get_active_concerns(self) -> List[Dict[str, Any]]:
        """Return list of unresolved concerns."""
        return [c for c in self.relationship.concerns if not c.get("resolved")]

    def get_active_goals(self) -> List[Dict[str, Any]]:
        """Return list of incomplete goals."""
        return [g for g in self.relationship.goals if not g.get("completed")]


# ============================================================================
#                        MockAdvisorBrain
# ============================================================================

class MockAdvisorBrain:
    """Deterministic version of AdvisorBrain for testing.

    Provides the same interface as AdvisorBrain but with predictable,
    deterministic responses. Crisis detection always works.
    """

    def __init__(self, memory: Optional[Any] = None) -> None:
        self.current_emotion: EmotionalState = EmotionalState.NEUTRAL
        self.relationship: RelationshipContext = RelationshipContext()
        self.memory = memory
        self._call_log: List[str] = []

    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Deterministic sentiment analysis."""
        self._call_log.append(f"analyze_sentiment: {text[:50]}")
        if not text or not text.strip():
            return {"primary_emotion": "neutral", "intensity": 0.0, "urgency": 0.0}
        # Simple deterministic logic
        if "לחוץ" in text or "anxious" in text.lower():
            return {"primary_emotion": "anxious", "intensity": 0.7, "urgency": 0.3}
        if "שמח" in text or "happy" in text.lower():
            return {"primary_emotion": "happy", "intensity": 0.8, "urgency": 0.0}
        if "עצוב" in text or "sad" in text.lower():
            return {"primary_emotion": "sad", "intensity": 0.6, "urgency": 0.1}
        return {"primary_emotion": "neutral", "intensity": 0.2, "urgency": 0.0}

    def detect_crisis(self, text: str) -> bool:
        """Deterministic crisis detection — always catches crisis keywords."""
        self._call_log.append(f"detect_crisis: {text[:50]}")
        if not text:
            return False
        text_lower = text.lower()
        for lang_keywords in CRISIS_KEYWORDS.values():
            for kw in lang_keywords:
                if kw in text_lower:
                    return True
        return False

    def respond_as_friend(self, user_input: str, context: Dict[str, Any] = None) -> str:
        """Deterministic friend response."""
        self._call_log.append(f"respond_as_friend: {user_input[:50]}")
        if self.detect_crisis(user_input):
            return "[MOCK CRISIS RESPONSE] Crisis detected. Contact 1201 or 101 immediately."
        sentiment = self.analyze_sentiment(user_input)
        return f"[MOCK FRIEND] Detected: {sentiment['primary_emotion']}. I'm here for you."

    def respond_as_advisor(
        self, user_input: str, domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """Deterministic advisor response."""
        self._call_log.append(f"respond_as_advisor: {user_input[:50]}")
        return {
            "type": "advice",
            "domain": domain or "general",
            "greeting": "[MOCK ADVISOR] Let's work through this.",
            "steps": ["Step 1: Analyze", "Step 2: Plan", "Step 3: Execute"],
            "closing": "[MOCK] You've got this.",
            "disclaimer": "General guidance only.",
            "urgent": False,
        }

    def respond_as_mentor(
        self, user_input: str, goal: Optional[str] = None
    ) -> Dict[str, Any]:
        """Deterministic mentor response."""
        self._call_log.append(f"respond_as_mentor: {user_input[:50]}")
        return {
            "type": "mentor",
            "response_type": "encouragement",
            "message": "[MOCK MENTOR] Keep going! I believe in you.",
            "goal": goal,
            "goal_status": {"has_goals": False},
            "next_steps": ["Step 1", "Step 2", "Step 3"],
            "hold_accountable": False,
        }

    def remember_fact(self, fact_type: str, fact: str) -> None:
        """Deterministic fact remembering."""
        self._call_log.append(f"remember_fact: {fact_type}={fact[:50]}")
        if fact_type == "goal":
            self.relationship.add_goal(fact)
        elif fact_type == "concern":
            self.relationship.add_concern(fact)

    def get_relationship_summary(self) -> Dict[str, Any]:
        """Deterministic relationship summary."""
        return {
            "trust_level": 0.5,
            "familiarity": 0.0,
            "interaction_count": len(self._call_log),
            "mock": True,
        }

    def adjust_tone(self, situation: str) -> str:
        """Deterministic tone adjustment."""
        return f"[MOCK TONE: {situation}]"

    def morning_briefing(self) -> Dict[str, Any]:
        """Deterministic morning briefing."""
        return {
            "type": "morning_briefing",
            "greeting": "[MOCK] Good morning!",
            "encouragement": "[MOCK] Have a great day!",
            "active_goals": [],
            "reminders": [],
            "quote": "[MOCK] Carpe diem.",
        }

    def evening_checkin(self) -> Dict[str, Any]:
        """Deterministic evening check-in."""
        return {
            "type": "evening_checkin",
            "prompt": "[MOCK] How was your day?",
            "goal_review": [],
            "gratitude_prompt": "[MOCK] What are you grateful for?",
            "goodnight_message": "[MOCK] Good night!",
        }

    def celebrate_milestone(self, milestone: str) -> str:
        """Deterministic milestone celebration."""
        return f"[MOCK CELEBRATION] Amazing achievement: {milestone}!"

    def provide_support(self, situation: str) -> str:
        """Deterministic support message."""
        return f"[MOCK SUPPORT] I'm here for you regarding: {situation}. You're not alone."


# ============================================================================
#                         Factory Function
# ============================================================================

def get_advisor_brain(
    memory: Optional[Any] = None,
    mock: bool = False,
) -> AdvisorBrain:
    """Factory function to create an AdvisorBrain instance.

    Args:
        memory: Optional memory backend for persistence.
        mock: If True, return a MockAdvisorBrain for testing.

    Returns:
        An AdvisorBrain or MockAdvisorBrain instance.
    """
    if mock:
        logger.info("AdvisorBrain factory: returning MockAdvisorBrain")
        return MockAdvisorBrain(memory=memory)
    logger.info("AdvisorBrain factory: returning full AdvisorBrain")
    return AdvisorBrain(memory=memory)


# ============================================================================
#                           Module Entry Point
# ============================================================================

if __name__ == "__main__":
    # Quick self-test when run directly
    print("=" * 60)
    print("   J A R V I S  -  A d v i s o r   B r a i n")
    print("   Self-Test Mode")
    print("=" * 60)

    brain = get_advisor_brain()

    # Test 1: Sentiment analysis
    print("\n--- Test 1: Sentiment Analysis ---")
    sentiments = [
        "אני מרגיש מדהים היום!",
        "אני מרגיש עצוב מאוד",
        "אני לחוץ לפני הבחינה",
        "תודה רבה על העזרה!",
    ]
    for s in sentiments:
        result = brain.analyze_sentiment(s)
        print(f"  '{s}' -> {result['primary_emotion']} (i={result['intensity']}, u={result['urgency']})")

    # Test 2: Crisis detection
    print("\n--- Test 2: Crisis Detection ---")
    crisis_tests = [
        "אני רוצה לפגוע בעצמי",
        "הכול בסדר, סתם מדברים",
        "לא יכול יותר, אין טעם בחיים",
    ]
    for t in crisis_tests:
        is_crisis = brain.detect_crisis(t)
        print(f"  '{t[:40]}' -> Crisis: {is_crisis}")

    # Test 3: Friend response
    print("\n--- Test 3: Friend Response ---")
    response = brain.respond_as_friend("אני מרגיש לחוץ היום")
    print(f"  {response[:120]}...")

    # Test 4: Morning briefing
    print("\n--- Test 4: Morning Briefing ---")
    briefing = brain.morning_briefing()
    print(f"  Greeting: {briefing['greeting']}")
    print(f"  Quote: {briefing['quote']}")

    # Test 5: Evening check-in
    print("\n--- Test 5: Evening Check-in ---")
    checkin = brain.evening_checkin()
    print(f"  Prompt: {checkin['prompt']}")
    print(f"  Goodnight: {checkin['goodnight_message']}")

    # Test 6: Milestone
    print("\n--- Test 6: Milestone Celebration ---")
    celeb = brain.celebrate_milestone("קידום בעבודה")
    print(f"  {celeb[:120]}...")

    # Test 7: Support
    print("\n--- Test 7: Emotional Support ---")
    support = brain.provide_support("היום היה יום קשה מאוד")
    print(f"  {support[:120]}...")

    # Test 8: Relationship summary
    print("\n--- Test 8: Relationship Summary ---")
    summary = brain.get_relationship_summary()
    for k, v in summary.items():
        print(f"  {k}: {v}")

    print("\n" + "=" * 60)
    print("   All self-tests passed!")
    print("=" * 60)
