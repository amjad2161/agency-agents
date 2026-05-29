from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any


DEFAULT_EXTERNAL_CATALOG = "external_opportunities.json"
ADOPTION_MODES = frozenset(
    {
        "direct-integration",
        "adapter-integration",
        "pattern-adaptation",
        "research-only",
    }
)


def _string_tuple(raw: dict[str, Any], field: str, slug: str, *, required: bool = True) -> tuple[str, ...]:
    if field not in raw:
        if required:
            raise TypeError(f"External opportunity '{slug}' field '{field}' must be a list")
        return ()

    value = raw.get(field)
    if not isinstance(value, list):
        raise TypeError(f"External opportunity '{slug}' field '{field}' must be a list")
    if not all(isinstance(item, str) and item for item in value):
        raise TypeError(f"External opportunity '{slug}' field '{field}' must contain non-empty strings")
    return tuple(value)


@dataclass(frozen=True)
class ExternalOpportunity:
    slug: str
    name_with_owner: str
    url: str
    description: str
    stars: int
    license_key: str
    license_name: str
    updated_at: str
    domain: str
    strengthens_layers: tuple[str, ...]
    strengthens_capabilities: tuple[str, ...]
    relevant_modules: tuple[str, ...]
    adoption_mode: str
    recommendation: str
    risks: tuple[str, ...]
    tags: tuple[str, ...]
    priority_score: int

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ExternalOpportunity":
        slug = str(raw["slug"])
        adoption_mode = str(raw["adoption_mode"])
        if adoption_mode not in ADOPTION_MODES:
            raise ValueError(f"External opportunity '{slug}' has unknown adoption mode: {adoption_mode}")

        return cls(
            slug=slug,
            name_with_owner=str(raw["name_with_owner"]),
            url=str(raw["url"]),
            description=str(raw["description"]),
            stars=int(raw["stars"]),
            license_key=str(raw["license_key"]),
            license_name=str(raw["license_name"]),
            updated_at=str(raw["updated_at"]),
            domain=str(raw["domain"]),
            strengthens_layers=_string_tuple(raw, "strengthens_layers", slug),
            strengthens_capabilities=_string_tuple(raw, "strengthens_capabilities", slug, required=False),
            relevant_modules=_string_tuple(raw, "relevant_modules", slug),
            adoption_mode=adoption_mode,
            recommendation=str(raw["recommendation"]),
            risks=_string_tuple(raw, "risks", slug),
            tags=_string_tuple(raw, "tags", slug),
            priority_score=int(raw["priority_score"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name_with_owner": self.name_with_owner,
            "url": self.url,
            "description": self.description,
            "stars": self.stars,
            "license_key": self.license_key,
            "license_name": self.license_name,
            "updated_at": self.updated_at,
            "domain": self.domain,
            "strengthens_layers": list(self.strengthens_layers),
            "strengthens_capabilities": list(self.strengthens_capabilities),
            "relevant_modules": list(self.relevant_modules),
            "adoption_mode": self.adoption_mode,
            "recommendation": self.recommendation,
            "risks": list(self.risks),
            "tags": list(self.tags),
            "priority_score": self.priority_score,
        }


@dataclass(frozen=True)
class ExternalOpportunityCatalog:
    opportunities: tuple[ExternalOpportunity, ...]
    source: str
    searched_at: str

    def top_candidates(self, limit: int = 10) -> tuple[ExternalOpportunity, ...]:
        usable = [item for item in self.opportunities if item.adoption_mode != "research-only"]
        return tuple(sorted(usable, key=lambda item: (-item.priority_score, -item.stars, item.slug))[:limit])

    def for_module(self, module_slug: str) -> tuple[ExternalOpportunity, ...]:
        return tuple(
            sorted(
                (item for item in self.opportunities if module_slug in item.relevant_modules),
                key=lambda item: (-item.priority_score, item.slug),
            )
        )

    def for_layer(self, layer: str) -> tuple[ExternalOpportunity, ...]:
        return tuple(
            sorted(
                (item for item in self.opportunities if layer in item.strengthens_layers),
                key=lambda item: (-item.priority_score, item.slug),
            )
        )


def _read_external_catalog(path: Path | None = None) -> bytes:
    if path is not None:
        return path.read_bytes()
    return resources.files("singularity_nexus.catalog").joinpath(DEFAULT_EXTERNAL_CATALOG).read_bytes()


def load_external_opportunities(path: str | Path | None = None) -> ExternalOpportunityCatalog:
    raw_path = Path(path) if path is not None else None
    payload: dict[str, Any] = json.loads(_read_external_catalog(raw_path).decode("utf-8"))
    opportunities = tuple(ExternalOpportunity.from_dict(item) for item in payload["opportunities"])
    _validate(opportunities)
    return ExternalOpportunityCatalog(
        opportunities=opportunities,
        source=str(payload["source"]),
        searched_at=str(payload["searched_at"]),
    )


def _validate(opportunities: tuple[ExternalOpportunity, ...]) -> None:
    slugs = [item.slug for item in opportunities]
    if len(slugs) != len(set(slugs)):
        raise ValueError("External opportunities catalog contains duplicate slugs")

    for item in opportunities:
        if not item.url.startswith("https://github.com/"):
            raise ValueError(f"External opportunity '{item.slug}' must reference a GitHub URL")
        if item.priority_score < 0 or item.priority_score > 100:
            raise ValueError(f"External opportunity '{item.slug}' priority_score must be 0..100")
