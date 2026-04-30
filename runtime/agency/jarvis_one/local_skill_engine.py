"""Local skill engine (Tier 5) — dynamic markdown-skill loader & hot-swap.

Wraps the existing :class:`agency.skills.SkillRegistry` with a hot-reload
hook so freshly added persona files can be picked up without a process
restart. The hot-swap interface is also used by :mod:`hot_reload`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..skills import Skill, SkillRegistry, discover_repo_root


@dataclass
class SkillSnapshot:
    count: int
    categories: list[str]
    by_category: dict[str, int]


class LocalSkillEngine:
    """Hot-swappable skill registry."""

    def __init__(self, repo: Path | None = None) -> None:
        self.repo = repo if repo else discover_repo_root()
        self.registry = SkillRegistry.load(self.repo)

    # ------------------------------------------------------------------
    def reload(self) -> SkillSnapshot:
        self.registry = SkillRegistry.load(self.repo)
        return self.snapshot()

    def snapshot(self) -> SkillSnapshot:
        cats = self.registry.categories()
        by_cat: dict[str, int] = {c: 0 for c in cats}
        for s in self.registry.all():
            by_cat[s.category] = by_cat.get(s.category, 0) + 1
        return SkillSnapshot(
            count=len(self.registry),
            categories=cats,
            by_category=by_cat,
        )

    def find(self, slug: str) -> Skill | None:
        for s in self.registry.all():
            if s.slug == slug:
                return s
        return None

    def search(self, query: str) -> Iterable[Skill]:
        return self.registry.search(query)

    def health(self) -> dict[str, Any]:
        snap = self.snapshot()
        return {
            "repo": str(self.repo),
            "count": snap.count,
            "categories": snap.categories,
        }
