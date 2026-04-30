"""Vector store — inspired by ChromaDB.

Pure-Python persistent vector collection. Re-uses :class:`LocalMemory`
under the hood so we don't duplicate similarity logic; this module adds
the *collection* abstraction and metadata filtering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .local_memory import LocalMemory


@dataclass
class Collection:
    name: str
    memory: LocalMemory

    def add(self, text: str, **metadata: Any) -> str:
        return self.memory.add(text, **metadata)

    def query(self, text: str, *, top_k: int = 5,
              where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        results = self.memory.search(text, top_k=top_k * 4)  # over-fetch then filter
        if where:
            results = [
                r for r in results
                if all(r["metadata"].get(k) == v for k, v in where.items())
            ]
        return results[:top_k]

    def count(self) -> int:
        return self.memory.health()["count"]


class VectorStore:
    """Multi-collection facade compatible with ChromaDB-shaped clients."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or Path.home() / ".agency" / "vectors").expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self._collections: dict[str, Collection] = {}

    def collection(self, name: str) -> Collection:
        if name not in self._collections:
            self._collections[name] = Collection(
                name=name,
                memory=LocalMemory(path=self.root / f"{name}.json"),
            )
        return self._collections[name]

    def list_collections(self) -> list[str]:
        return sorted(self._collections)

    def stats(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "collections": {n: c.count() for n, c in self._collections.items()},
        }
