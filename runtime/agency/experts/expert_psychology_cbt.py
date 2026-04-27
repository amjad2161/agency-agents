"""JARVIS Expert: Psychology / CBT (cognitive distortion + therapy)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PsychologyCBTQuery:
    query: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class PsychologyCBTResult:
    answer: str
    confidence: float
    domain: str
    sources: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


_KEYWORDS = (
    "anxious", "anxiety", "depressed", "depression", "stress", "worry",
    "thought", "feeling", "emotion", "cognitive", "behavior", "therapy",
    "cbt", "mood", "panic", "phobia", "obsess", "compulsive", "trauma",
    "avoidance", "ruminat", "self-esteem", "guilt", "shame", "anger",
    "fear", "always", "never", "should", "must", "everyone", "nobody",
)

_DISTORTIONS = {
    "all_or_nothing": {
        "patterns": [r"\balways\b", r"\bnever\b", r"\bcompletely\b", r"\btotally\b",
                     r"\beveryone\b", r"\bnobody\b"],
        "name": "All-or-nothing thinking",
        "reframe": "Look for the middle ground — outcomes are usually on a spectrum.",
    },
    "catastrophizing": {
        "patterns": [r"disaster", r"terrible", r"end of the world", r"worst case",
                     r"can't handle", r"awful"],
        "name": "Catastrophizing",
        "reframe": "What's the realistic worst case, and could you cope with it?",
    },
    "mind_reading": {
        "patterns": [r"they think", r"he thinks", r"she thinks", r"everyone thinks",
                     r"they hate", r"they don't like"],
        "name": "Mind reading",
        "reframe": "What evidence do you have for this assumption?",
    },
    "shoulds": {
        "patterns": [r"\bshould\b", r"\bmust\b", r"\bhave to\b", r"\bought to\b"],
        "name": "Should statements",
        "reframe": "Replace 'should' with 'I would prefer' — relax the demand.",
    },
    "personalization": {
        "patterns": [r"my fault", r"because of me", r"i caused", r"i ruined"],
        "name": "Personalization",
        "reframe": "What other factors contributed besides you?",
    },
    "labeling": {
        "patterns": [r"i'?m a (?:loser|failure|idiot|fool)", r"i'?m worthless",
                     r"i'?m stupid", r"i'?m useless"],
        "name": "Labeling",
        "reframe": "Describe the behavior, not the identity.",
    },
    "filtering": {
        "patterns": [r"only the bad", r"nothing good", r"everything wrong"],
        "name": "Mental filtering",
        "reframe": "What positives or neutrals are you discounting?",
    },
    "fortune_telling": {
        "patterns": [r"will fail", r"won't work", r"going to be bad", r"never will"],
        "name": "Fortune telling",
        "reframe": "You can't predict the future — what's actually likely?",
    },
}

_TECHNIQUES = {
    "thought_record": "5-column thought record: situation → automatic thought → "
                       "emotion (0-100) → evidence for/against → balanced thought.",
    "behavioral_activation": "Schedule small rewarding activities when motivation is low.",
    "exposure": "Gradual, repeated exposure to feared situations to extinguish avoidance.",
    "cognitive_restructuring": "Identify, challenge, and reframe distortions.",
    "mindfulness": "Observe thoughts without judgment; return attention to present.",
    "problem_solving": "Define problem → brainstorm → evaluate → pick → execute → review.",
    "relaxation": "Diaphragmatic breathing or progressive muscle relaxation.",
    "values_clarification": "Identify core values → align actions, ACT-style.",
}

_PSYCHOEDUCATION = {
    "anxiety": "Anxiety is the body's threat-response (sympathetic activation). "
                "Avoidance maintains it; gradual exposure extinguishes it.",
    "depression": "Depression often follows withdrawal from rewarding activities. "
                   "Behavioral activation can break the cycle.",
    "panic": "Panic attacks are intense but time-limited (peak ~10 min). "
              "They are uncomfortable but not dangerous.",
    "ocd": "OCD: intrusive thoughts (obsessions) drive ritual behaviors (compulsions). "
            "Treatment of choice is Exposure & Response Prevention.",
}


class PsychologyCBTExpert:
    """JARVIS expert for psychology and CBT-style reasoning."""

    DOMAIN = "psychology_cbt"
    VERSION = "1.0.0"

    def analyze(self, query: str, context: dict[str, Any] | None = None) -> PsychologyCBTResult:
        confidence = self.can_handle(query)
        sources: list[str] = []
        meta: dict[str, Any] = {}
        parts: list[str] = []

        distortions = self.detect_distortions(query)
        if distortions:
            meta["distortions"] = distortions
            sources.append("CBT-distortion-list")
            names = ", ".join(d["name"] for d in distortions)
            parts.append(f"Cognitive distortions detected: {names}.")
            for d in distortions[:3]:
                parts.append(f"Reframe: {d['reframe']}")

        techniques = self.suggest_techniques(query)
        if techniques:
            meta["techniques"] = techniques
            sources.append("CBT-techniques")
            parts.append("Suggested techniques: " + "; ".join(techniques) + ".")

        psyed = self.psychoeducation(query)
        if psyed:
            meta["psychoeducation"] = psyed
            sources.append("psychoeducation")
            parts.append(psyed)

        mood = self.estimate_mood(query)
        if mood is not None:
            meta["mood_estimate"] = mood
            parts.append(f"Estimated mood valence: {mood:+.2f} (-1 negative, +1 positive).")

        if not parts:
            parts.append("Psychology query received. Share the thought, situation, and emotion "
                         "for a CBT thought-record analysis.")
            confidence = min(confidence, 0.3)

        return PsychologyCBTResult(
            answer=" ".join(parts),
            confidence=confidence,
            domain=self.DOMAIN,
            sources=sources,
            metadata=meta,
        )

    def can_handle(self, query: str) -> float:
        q = query.lower()
        hits = sum(1 for kw in _KEYWORDS if kw in q)
        # First-person psychological state strongly suggests therapy context
        if re.search(r"\bi (?:feel|am|have)\b", q) or "myself" in q:
            hits += 2
        if hits == 0:
            return 0.0
        return min(1.0, 0.3 + 0.12 * hits)

    def detect_distortions(self, query: str) -> list[dict[str, str]]:
        q = query.lower()
        found: list[dict[str, str]] = []
        for key, d in _DISTORTIONS.items():
            for pat in d["patterns"]:
                if re.search(pat, q):
                    found.append({"key": key, "name": d["name"], "reframe": d["reframe"]})
                    break
        return found

    def suggest_techniques(self, query: str) -> list[str]:
        q = query.lower()
        out: list[str] = []
        if "anxiety" in q or "panic" in q or "fear" in q:
            out.append(_TECHNIQUES["exposure"])
            out.append(_TECHNIQUES["relaxation"])
        if "depress" in q or "low mood" in q or "no motivation" in q:
            out.append(_TECHNIQUES["behavioral_activation"])
        if "thought" in q or "rumin" in q:
            out.append(_TECHNIQUES["thought_record"])
            out.append(_TECHNIQUES["cognitive_restructuring"])
        if "obsess" in q or "compulsive" in q:
            out.append(_TECHNIQUES["exposure"])
        if not out:
            out.append(_TECHNIQUES["mindfulness"])
        return out

    def psychoeducation(self, query: str) -> str | None:
        q = query.lower()
        for k, v in _PSYCHOEDUCATION.items():
            if k in q:
                return v
        return None

    def thought_record(
        self,
        situation: str,
        automatic_thought: str,
        emotion: str,
        emotion_intensity: int,
        evidence_for: str = "",
        evidence_against: str = "",
        balanced_thought: str = "",
    ) -> dict[str, Any]:
        return {
            "situation": situation,
            "automatic_thought": automatic_thought,
            "emotion": emotion,
            "intensity_0_100": max(0, min(100, emotion_intensity)),
            "evidence_for": evidence_for,
            "evidence_against": evidence_against,
            "balanced_thought": balanced_thought,
        }

    def estimate_mood(self, query: str) -> float | None:
        q = query.lower()
        positive = ["happy", "great", "good", "wonderful", "love", "excited", "calm", "grateful"]
        negative = ["sad", "anxious", "depressed", "terrible", "awful", "hopeless",
                    "worthless", "scared", "angry", "panic", "stress"]
        pos = sum(1 for w in positive if w in q)
        neg = sum(1 for w in negative if w in q)
        total = pos + neg
        if total == 0:
            return None
        return (pos - neg) / total

    def severity_level(self, mood_score: float) -> str:
        if mood_score < -0.7:
            return "severe"
        if mood_score < -0.3:
            return "moderate"
        if mood_score < 0:
            return "mild"
        return "stable"

    def crisis_check(self, query: str) -> bool:
        q = query.lower()
        flags = ["suicide", "kill myself", "end it all", "self-harm", "want to die",
                 "no reason to live"]
        return any(f in q for f in flags)

    def status(self) -> dict[str, Any]:
        return {
            "domain": self.DOMAIN,
            "version": self.VERSION,
            "ok": True,
            "distortions": list(_DISTORTIONS.keys()),
            "techniques": list(_TECHNIQUES.keys()),
        }


_singleton: PsychologyCBTExpert | None = None


def get_expert() -> PsychologyCBTExpert:
    global _singleton
    if _singleton is None:
        _singleton = PsychologyCBTExpert()
    return _singleton
