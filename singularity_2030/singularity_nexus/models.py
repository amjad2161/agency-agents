from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _string_tuple(raw: dict[str, Any], field: str, slug: str, *, required: bool = True) -> tuple[str, ...]:
    if field not in raw:
        if required:
            raise ValueError(f"Catalog module '{slug}' is missing required field '{field}'")
        return ()

    value = raw[field]
    if not isinstance(value, list):
        raise TypeError(f"Catalog module '{slug}' field '{field}' must be a list of strings")
    if not all(isinstance(item, str) and item for item in value):
        raise TypeError(f"Catalog module '{slug}' field '{field}' must contain only non-empty strings")
    return tuple(value)


@dataclass(frozen=True)
class RepoModule:
    slug: str
    name: str
    repo_path: str
    layer: str
    maturity: str
    vision: str
    stack: tuple[str, ...]
    capabilities: tuple[str, ...]
    integration_modes: tuple[str, ...]
    run_profiles: tuple[str, ...]
    commands: tuple[str, ...]
    risks: tuple[str, ...]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RepoModule":
        slug = str(raw["slug"])
        return cls(
            slug=slug,
            name=str(raw["name"]),
            repo_path=str(raw["repo_path"]),
            layer=str(raw["layer"]),
            maturity=str(raw["maturity"]),
            vision=str(raw["vision"]),
            stack=_string_tuple(raw, "stack", slug, required=False),
            capabilities=_string_tuple(raw, "capabilities", slug),
            integration_modes=_string_tuple(raw, "integration_modes", slug),
            run_profiles=_string_tuple(raw, "run_profiles", slug),
            commands=_string_tuple(raw, "commands", slug, required=False),
            risks=_string_tuple(raw, "risks", slug, required=False),
        )


@dataclass(frozen=True)
class IntegrationEdge:
    source: str
    target: str
    mode: str
    contract: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "IntegrationEdge":
        return cls(
            source=str(raw["source"]),
            target=str(raw["target"]),
            mode=str(raw["mode"]),
            contract=str(raw["contract"]),
        )


@dataclass(frozen=True)
class SingularityCatalog:
    modules: tuple[RepoModule, ...]
    integration_edges: tuple[IntegrationEdge, ...]

    def module(self, slug: str) -> RepoModule:
        for module in self.modules:
            if module.slug == slug:
                return module
        raise KeyError(f"Unknown module: {slug}")


@dataclass(frozen=True)
class ExecutionProfile:
    slug: str
    name: str
    autonomy_level: str
    purpose: str
    module_slugs: tuple[str, ...]
    invariants: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "autonomy_level": self.autonomy_level,
            "purpose": self.purpose,
            "modules": list(self.module_slugs),
            "invariants": list(self.invariants),
        }
