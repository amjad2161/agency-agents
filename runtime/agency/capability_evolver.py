"""Capability evolver.

Tracks per-domain success/failure rates and surfaces "weakest"
domains so the agent can focus learning effort where it lags.

Storage: JSON at `~/.agency/capabilities.json` (override via
`AGENCY_CAPABILITIES_JSON`). One object per domain slug. Atomic
writes via tmp + rename so a crashed process never leaves a partial
file.

A `proficiency_score` in [0, 1] is computed from:
  - Success ratio (60%)
  - Average confidence over recent outcomes (30%)
  - Volume bonus (10%, saturating around 50 requests)

Volume matters because a 100% success rate over 2 requests is less
trustworthy than 90% over 200.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


DEFAULT_CAPABILITIES_JSON = "capabilities.json"


def capabilities_json_path() -> Path:
    override = os.environ.get("AGENCY_CAPABILITIES_JSON")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".agency" / DEFAULT_CAPABILITIES_JSON


@dataclass
class DomainProfile:
    """Per-domain proficiency state. Mutable — counters tick over time."""

    slug: str
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    avg_confidence: float = 0.0
    proficiency_score: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DomainProfile":
        return cls(
            slug=d["slug"],
            total_requests=int(d.get("total_requests", 0)),
            successful=int(d.get("successful", 0)),
            failed=int(d.get("failed", 0)),
            avg_confidence=float(d.get("avg_confidence", 0.0)),
            proficiency_score=float(d.get("proficiency_score", 0.0)),
        )


def _compute_proficiency(p: DomainProfile) -> float:
    if p.total_requests == 0:
        return 0.0
    success_ratio = p.successful / p.total_requests
    volume_bonus = min(1.0, p.total_requests / 50.0)
    return round(
        0.6 * success_ratio + 0.3 * p.avg_confidence + 0.1 * volume_bonus,
        4,
    )


class CapabilityEvolver:
    """Per-domain proficiency tracker with persistent state."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or capabilities_json_path()
        self._profiles: dict[str, DomainProfile] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        if self.path.is_file():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                raw = {}
            for slug, body in (raw or {}).items():
                try:
                    self._profiles[slug] = DomainProfile.from_dict(body)
                except (KeyError, TypeError, ValueError):
                    continue
        self._loaded = True

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        body = {slug: p.to_dict() for slug, p in self._profiles.items()}
        tmp.write_text(json.dumps(body, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    # ----- write side -----

    def record_outcome(
        self, slug: str, *, success: bool, confidence: float
    ) -> DomainProfile:
        """Update the profile for `slug`. Persists immediately so a
        crash between calls doesn't lose the increment."""
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence must be in [0,1], got {confidence}")
        self._ensure_loaded()
        prof = self._profiles.get(slug) or DomainProfile(slug=slug)
        prev_total = prof.total_requests
        prof.total_requests += 1
        if success:
            prof.successful += 1
        else:
            prof.failed += 1
        # Running mean: avg_n = (avg_(n-1)*(n-1) + new)/n
        prof.avg_confidence = (
            (prof.avg_confidence * prev_total) + confidence
        ) / prof.total_requests
        prof.proficiency_score = _compute_proficiency(prof)
        self._profiles[slug] = prof
        self._save()
        return prof

    # ----- read side -----

    def get(self, slug: str) -> DomainProfile | None:
        self._ensure_loaded()
        return self._profiles.get(slug)

    def all_profiles(self) -> list[DomainProfile]:
        self._ensure_loaded()
        return list(self._profiles.values())

    def weakest_domains(self, n: int = 5) -> list[DomainProfile]:
        """Return the `n` lowest-proficiency domains. Domains with no
        data are excluded — you can't improve what you've never tried."""
        self._ensure_loaded()
        seen = [p for p in self._profiles.values() if p.total_requests > 0]
        return sorted(seen, key=lambda p: p.proficiency_score)[:n]

    def growth_report(self) -> dict:
        """Aggregate snapshot across all tracked domains."""
        self._ensure_loaded()
        profiles = list(self._profiles.values())
        if not profiles:
            return {
                "domains_tracked": 0,
                "total_requests": 0,
                "avg_proficiency": 0.0,
                "weakest": [],
                "strongest": [],
            }
        total = sum(p.total_requests for p in profiles)
        avg = sum(p.proficiency_score for p in profiles) / len(profiles)
        weakest = self.weakest_domains(3)
        strongest = sorted(
            profiles, key=lambda p: p.proficiency_score, reverse=True
        )[:3]
        return {
            "domains_tracked": len(profiles),
            "total_requests": total,
            "avg_proficiency": round(avg, 4),
            "weakest": [p.slug for p in weakest],
            "strongest": [p.slug for p in strongest],
        }
