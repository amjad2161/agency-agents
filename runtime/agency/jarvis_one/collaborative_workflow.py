"""Collaborative workflow (Tier 2).

Multi-agent collaboration patterns: peer-review, brainstorm, debate,
sequential, parallel. Each pattern returns a structured transcript
with per-agent contributions, a merged consensus, and a list of
unresolved conflicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .expert_personas import ExpertPersona


PATTERNS = ("peer-review", "brainstorm", "debate", "sequential", "parallel")


@dataclass
class Contribution:
    persona: str
    text: str
    role: str = "contributor"

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class Transcript:
    pattern: str
    topic: str
    contributions: list[Contribution] = field(default_factory=list)
    consensus: str = ""
    conflicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "topic": self.topic,
            "consensus": self.consensus,
            "conflicts": list(self.conflicts),
            "contributions": [c.to_dict() for c in self.contributions],
        }


# A speaker is a callable that takes (persona, topic) and returns text.
Speaker = Callable[[ExpertPersona, str], str]


def _default_speaker(persona: ExpertPersona, topic: str) -> str:
    return f"[{persona.role}] take on '{topic}': covered domains "
    f"{', '.join(persona.domains[:3])}…"


class CollaborativeWorkflow:
    """Run multi-agent collaboration patterns over a fixed roster."""

    def __init__(self, personas: Iterable[ExpertPersona],
                 speaker: Speaker | None = None) -> None:
        self.personas = list(personas)
        self.speaker = speaker or _default_speaker

    # ------------------------------------------------------------------
    def run(self, pattern: str, topic: str) -> Transcript:
        if pattern not in PATTERNS:
            raise ValueError(f"unknown pattern {pattern!r}; expected one of {PATTERNS}")
        method = getattr(self, f"_pattern_{pattern.replace('-', '_')}")
        return method(topic)

    # -------------------------------------------------------- patterns
    def _pattern_peer_review(self, topic: str) -> Transcript:
        t = Transcript(pattern="peer-review", topic=topic)
        if not self.personas:
            return t
        author = self.personas[0]
        draft = self.speaker(author, topic)
        t.contributions.append(Contribution(persona=author.slug,
                                            text=draft, role="author"))
        for reviewer in self.personas[1:]:
            review = self.speaker(reviewer, f"review of: {draft}")
            t.contributions.append(Contribution(persona=reviewer.slug,
                                                text=review, role="reviewer"))
        t.consensus = f"Reviewed by {len(self.personas) - 1} peers; final draft accepted."
        return t

    def _pattern_brainstorm(self, topic: str) -> Transcript:
        t = Transcript(pattern="brainstorm", topic=topic)
        for p in self.personas:
            t.contributions.append(Contribution(persona=p.slug,
                                                text=self.speaker(p, topic)))
        t.consensus = f"{len(t.contributions)} ideas collected."
        return t

    def _pattern_debate(self, topic: str) -> Transcript:
        t = Transcript(pattern="debate", topic=topic)
        if len(self.personas) < 2:
            t.consensus = "no debate — fewer than 2 personas"
            return t
        pro, con = self.personas[0], self.personas[1]
        t.contributions.append(Contribution(persona=pro.slug,
                                            text=self.speaker(pro, f"FOR: {topic}"),
                                            role="pro"))
        t.contributions.append(Contribution(persona=con.slug,
                                            text=self.speaker(con, f"AGAINST: {topic}"),
                                            role="con"))
        # Synthesis from a third voice if available.
        if len(self.personas) > 2:
            judge = self.personas[2]
            t.contributions.append(Contribution(persona=judge.slug,
                                                text=self.speaker(judge, f"verdict on: {topic}"),
                                                role="judge"))
            t.consensus = "judged"
        else:
            t.conflicts.append("no judge available")
            t.consensus = "split decision"
        return t

    def _pattern_sequential(self, topic: str) -> Transcript:
        t = Transcript(pattern="sequential", topic=topic)
        running = topic
        for p in self.personas:
            text = self.speaker(p, running)
            t.contributions.append(Contribution(persona=p.slug, text=text))
            running = text
        t.consensus = running
        return t

    def _pattern_parallel(self, topic: str) -> Transcript:
        t = Transcript(pattern="parallel", topic=topic)
        # Same as brainstorm but consensus is the merged bullet list.
        bullets: list[str] = []
        for p in self.personas:
            text = self.speaker(p, topic)
            t.contributions.append(Contribution(persona=p.slug, text=text))
            bullets.append(f"• {p.slug}: {text}")
        t.consensus = "\n".join(bullets)
        return t
