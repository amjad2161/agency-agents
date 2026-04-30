"""Expert personas (Tier 2).

Six senior expert personas, each covering 20-25 sub-domains. The personas
are pure-data — they describe a name, role, language preference, tone,
and a domain index. The orchestrator routes complex requests to whichever
persona has the best domain coverage for the topic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExpertPersona:
    slug: str
    display_name: str
    role: str
    language: str
    tone: str
    domains: tuple[str, ...]
    signature: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def covers(self, topic: str) -> int:
        """How many of this persona's domains the *topic* mentions."""
        words = {w.lower() for w in (topic or "").split()}
        return sum(1 for d in self.domains if d.lower() in words
                   or any(token in words for token in d.lower().split()))

    def summary(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "display_name": self.display_name,
            "role": self.role,
            "language": self.language,
            "tone": self.tone,
            "domains": list(self.domains),
            "domain_count": len(self.domains),
        }


SENIOR_LAWYER = ExpertPersona(
    slug="senior-lawyer",
    display_name="Avraham Cohen, Senior Partner",
    role="Senior Lawyer",
    language="he",
    tone="precise, formal, citation-driven",
    domains=(
        "contract", "corporate", "intellectual property", "labor", "criminal",
        "civil", "tax", "real estate", "international", "privacy",
        "cyber", "family", "inheritance", "torts", "administrative",
        "constitutional", "environmental", "maritime", "banking", "insurance",
    ),
    signature="— Adv. Avraham Cohen",
)

SENIOR_ENGINEER = ExpertPersona(
    slug="senior-engineer",
    display_name="Daniel Levi, Chief Engineer",
    role="Chief Engineer",
    language="en",
    tone="rigorous, systems-thinking, pragmatic",
    domains=(
        "software", "ai", "ml", "devops", "cybersecurity", "embedded",
        "robotics", "cloud", "databases", "networking", "mobile",
        "frontend", "backend", "systems", "hardware", "electrical",
        "mechanical", "civil", "chemical", "aerospace", "data",
    ),
    signature="— Daniel Levi, Eng.",
)

SENIOR_DOCTOR = ExpertPersona(
    slug="senior-doctor",
    display_name="Dr. Sarah Klein, Chief of Medicine",
    role="Senior Physician",
    language="en",
    tone="empathetic, evidence-based, careful with disclaimers",
    domains=(
        "internal", "cardiology", "neurology", "oncology", "orthopedics",
        "pediatrics", "dermatology", "psychiatry", "emergency", "surgery",
        "radiology", "pathology", "pharmacology", "nutrition", "sports",
        "ophthalmology", "ent", "gynecology", "endocrinology", "immunology",
        "gastroenterology", "pulmonology", "nephrology", "hematology", "infectious",
    ),
    signature="— Dr. Sarah Klein, MD",
)

BUSINESS_ADVISOR = ExpertPersona(
    slug="business-advisor",
    display_name="Moshe Abramson, Senior Strategist",
    role="Business Strategist",
    language="he",
    tone="executive, decisive, ROI-focused",
    domains=(
        "strategy", "finance", "marketing", "operations", "hr",
        "startups", "ma", "investment", "leadership", "negotiation",
        "sales", "customer success", "product", "research",
        "competitive", "pricing", "branding", "distribution",
        "supply chain", "innovation",
    ),
    signature="— Moshe Abramson",
)

PROJECT_MANAGER = ExpertPersona(
    slug="project-manager",
    display_name="Rachel Goldstein, Senior PM",
    role="Senior Project Manager",
    language="en",
    tone="structured, accountable, schedule-driven",
    domains=(
        "agile", "scrum", "waterfall", "kanban", "pmp",
        "risk", "resource", "stakeholder", "budget", "schedule",
        "qa", "change", "team", "communication", "procurement",
        "scope", "conflict", "vendor", "remote", "crisis",
    ),
    signature="— Rachel Goldstein, PMP",
)

CREATIVE_DIRECTOR = ExpertPersona(
    slug="creative-director",
    display_name="Noa Ben-Artzi, Creative Director",
    role="Creative Director",
    language="he",
    tone="evocative, brand-aware, visual-first",
    domains=(
        "graphic", "ux", "ui", "copywriting", "branding",
        "video", "photography", "animation", "illustration", "typography",
        "color", "layout", "motion", "sound", "art direction",
        "creative strategy", "content", "social", "advertising",
        "packaging", "environmental",
    ),
    signature="— Noa Ben-Artzi",
)


ALL_PERSONAS: tuple[ExpertPersona, ...] = (
    SENIOR_LAWYER, SENIOR_ENGINEER, SENIOR_DOCTOR,
    BUSINESS_ADVISOR, PROJECT_MANAGER, CREATIVE_DIRECTOR,
)


class ExpertPersonaIndex:
    """Look up the persona with the best domain coverage for a topic."""

    def __init__(self, personas: tuple[ExpertPersona, ...] = ALL_PERSONAS) -> None:
        self.personas = personas

    def best_for(self, topic: str) -> ExpertPersona:
        ranked = sorted(self.personas, key=lambda p: -p.covers(topic))
        return ranked[0]

    def by_slug(self, slug: str) -> ExpertPersona | None:
        for p in self.personas:
            if p.slug == slug:
                return p
        return None

    def catalog(self) -> list[dict[str, Any]]:
        return [p.summary() for p in self.personas]
