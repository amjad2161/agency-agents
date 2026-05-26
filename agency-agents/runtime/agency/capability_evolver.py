"""Capability evolver — tracks JARVIS domain proficiency and suggests growth areas.

Maintains a proficiency ledger per domain slug. Every interaction updates
the score. Low-performing domains surface as improvement candidates.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .logging import get_logger

DEFAULT_PROFILE_PATH = Path.home() / ".jarvis" / "capability_profile.json"

log = get_logger()


@dataclass
class DomainProfile:
    """Proficiency record for one JARVIS domain."""

    slug: str
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    avg_confidence: float = 0.0
    last_updated: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    growth_notes: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful / self.total_requests

    @property
    def proficiency_score(self) -> float:
        """0–1 composite score: success_rate * confidence * recency bonus."""
        if self.total_requests == 0:
            return 0.0
        base = self.success_rate * 0.6 + self.avg_confidence * 0.4
        # Recency bonus: up to +0.1 for active domains (>10 requests)
        bonus = min(0.1, self.total_requests / 100.0)
        return min(1.0, base + bonus)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["success_rate"] = self.success_rate
        d["proficiency_score"] = self.proficiency_score
        return d


class CapabilityEvolver:
    """Tracks per-domain proficiency and drives continuous improvement.

    Usage::

        evolver = CapabilityEvolver()
        evolver.record_outcome("jarvis-engineering", success=True, confidence=0.9)
        weak = evolver.weakest_domains(n=3)
        strong = evolver.strongest_domains(n=5)
        report = evolver.growth_report()
    """

    def __init__(self, profile_path: Path | None = None) -> None:
        self._path = Path(profile_path or DEFAULT_PROFILE_PATH)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._profiles: dict[str, DomainProfile] | None = None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, DomainProfile]:
        if self._profiles is not None:
            return self._profiles
        profiles: dict[str, DomainProfile] = {}
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                for slug, data in raw.items():
                    # Remove computed fields before reconstruction
                    data.pop("success_rate", None)
                    data.pop("proficiency_score", None)
                    profiles[slug] = DomainProfile(**data)
            except Exception as exc:
                log.warning("capability_evolver: failed to load profile — %s", exc)
        self._profiles = profiles
        return profiles

    def _save(self) -> None:
        profiles = self._load()
        data = {slug: p.to_dict() for slug, p in profiles.items()}
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def record_outcome(
        self,
        domain_slug: str,
        success: bool,
        confidence: float = 0.7,
        note: str | None = None,
    ) -> DomainProfile:
        """Update proficiency for *domain_slug* based on interaction outcome."""
        with self._lock:
            profiles = self._load()
            if domain_slug not in profiles:
                profiles[domain_slug] = DomainProfile(slug=domain_slug)

            p = profiles[domain_slug]
            p.total_requests += 1
            if success:
                p.successful += 1
            else:
                p.failed += 1

            # Exponential moving average for confidence
            alpha = 0.2
            p.avg_confidence = alpha * confidence + (1 - alpha) * p.avg_confidence

            p.last_updated = datetime.now(timezone.utc).isoformat()
            if note:
                p.growth_notes.append(f"[{p.last_updated[:10]}] {note}")
                p.growth_notes = p.growth_notes[-20:]  # keep last 20

            self._save()
            log.debug(
                "capability_evolver: updated %s — score=%.2f",
                domain_slug,
                p.proficiency_score,
            )
            return p

    def get_profile(self, domain_slug: str) -> DomainProfile | None:
        return self._load().get(domain_slug)

    def all_profiles(self) -> list[DomainProfile]:
        return list(self._load().values())

    def weakest_domains(self, n: int = 5) -> list[DomainProfile]:
        """Return domains with lowest proficiency score (minimum 3 requests)."""
        profiles = [p for p in self._load().values() if p.total_requests >= 3]
        return sorted(profiles, key=lambda p: p.proficiency_score)[:n]

    def strongest_domains(self, n: int = 5) -> list[DomainProfile]:
        profiles = list(self._load().values())
        return sorted(profiles, key=lambda p: p.proficiency_score, reverse=True)[:n]

    def untrained_domains(self, all_slugs: list[str]) -> list[str]:
        """Return slugs from *all_slugs* that have never been exercised."""
        known = set(self._load().keys())
        return [s for s in all_slugs if s not in known]

    def suggest_improvement_targets(self, all_slugs: list[str]) -> list[str]:
        """Return slugs that most need attention: untrained + weakest."""
        untrained = self.untrained_domains(all_slugs)
        weak = [p.slug for p in self.weakest_domains(n=5)]
        # Deduplicate, untrained first
        seen: set[str] = set()
        result: list[str] = []
        for slug in untrained + weak:
            if slug not in seen:
                seen.add(slug)
                result.append(slug)
        return result

    def growth_report(self) -> str:
        """Markdown report of capability landscape."""
        profiles = self._load()
        if not profiles:
            return "No capability data yet. Start routing requests to build the profile."

        total = len(profiles)
        total_requests = sum(p.total_requests for p in profiles.values())
        avg_score = (
            sum(p.proficiency_score for p in profiles.values()) / total
            if total else 0.0
        )
        strong = self.strongest_domains(n=3)
        weak = self.weakest_domains(n=3)

        lines = [
            "# JARVIS Capability Growth Report",
            "",
            f"**Domains tracked:** {total}",
            f"**Total interactions:** {total_requests}",
            f"**Average proficiency:** {avg_score:.1%}",
            "",
            "## Top Domains",
            *[
                f"- `{p.slug}`: {p.proficiency_score:.0%} "
                f"({p.total_requests} requests, {p.success_rate:.0%} success)"
                for p in strong
            ],
            "",
            "## Domains Needing Attention",
            *[
                f"- `{p.slug}`: {p.proficiency_score:.0%} "
                f"({p.total_requests} requests, {p.success_rate:.0%} success)"
                for p in weak
            ],
        ]
        return "\n".join(lines)

    def reset_domain(self, domain_slug: str) -> bool:
        """Reset proficiency for a domain. Returns True if it existed."""
        with self._lock:
            profiles = self._load()
            if domain_slug in profiles:
                del profiles[domain_slug]
                self._save()
                return True
            return False
