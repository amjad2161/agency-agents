from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from ..models import IntegrationEdge, RepoModule, SingularityCatalog


DEFAULT_CATALOG = "repositories.json"
KNOWN_RUN_PROFILES = frozenset(
    {
        "full-stack-ai-ops",
        "real-world-autonomy",
        "research-to-runtime",
    }
)


def _read_catalog_bytes(path: Path | None = None) -> bytes:
    if path is not None:
        return path.read_bytes()
    return resources.files(__name__).joinpath(DEFAULT_CATALOG).read_bytes()


def load_catalog(path: str | Path | None = None) -> SingularityCatalog:
    raw_path = Path(path) if path is not None else None
    payload: dict[str, Any] = json.loads(_read_catalog_bytes(raw_path).decode("utf-8"))

    modules = tuple(RepoModule.from_dict(item) for item in payload["modules"])
    edges = tuple(IntegrationEdge.from_dict(item) for item in payload["integration_edges"])
    _validate_catalog(modules, edges)
    return SingularityCatalog(modules=modules, integration_edges=edges)


def _validate_catalog(modules: tuple[RepoModule, ...], edges: tuple[IntegrationEdge, ...]) -> None:
    slugs = [module.slug for module in modules]
    if len(slugs) != len(set(slugs)):
        raise ValueError("Catalog contains duplicate module slugs")

    known = set(slugs)
    for module in modules:
        if not module.capabilities:
            raise ValueError(f"Catalog module has no capabilities: {module.slug}")
        if not module.integration_modes:
            raise ValueError(f"Catalog module has no integration modes: {module.slug}")
        unknown_profiles = set(module.run_profiles) - KNOWN_RUN_PROFILES
        if unknown_profiles:
            unknown = ", ".join(sorted(unknown_profiles))
            raise ValueError(f"Catalog module '{module.slug}' references unknown run profiles: {unknown}")

    for edge in edges:
        if edge.source not in known:
            raise ValueError(f"Integration edge has unknown source: {edge.source}")
        if edge.target not in known:
            raise ValueError(f"Integration edge has unknown target: {edge.target}")
