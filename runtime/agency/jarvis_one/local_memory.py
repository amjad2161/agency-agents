"""Local vector memory (Tier 5).

ChromaDB / FAISS shaped key-value + similarity store with a deterministic
in-memory fallback. The fallback uses bag-of-words cosine similarity so
tests can assert ranking behaviour without external services.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

_TOKEN = re.compile(r"[\w\u0590-\u05FF]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


@dataclass
class MemoryRecord:
    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    _vec: Counter[str] = field(default_factory=Counter, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


class LocalMemory:
    """Append-only vector memory with optional disk persistence."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = (
            Path(path).expanduser() if path else
            Path(os.environ.get("JARVIS_MEMORY_PATH",
                                str(Path.home() / ".agency" / "memory.json"))).expanduser()
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, MemoryRecord] = {}
        self._load()

    # ------------------------------------------------------------------
    def add(self, text: str, **metadata: Any) -> str:
        rid = uuid.uuid4().hex
        rec = MemoryRecord(id=rid, text=text, metadata=metadata)
        rec._vec = Counter(_tokenize(text))
        self._records[rid] = rec
        self._save()
        return rid

    def search(self, query: str, *, top_k: int = 5) -> list[dict[str, Any]]:
        qvec = Counter(_tokenize(query))
        scored: list[tuple[float, MemoryRecord]] = []
        for rec in self._records.values():
            scored.append((_cosine(qvec, rec._vec), rec))
        scored.sort(key=lambda x: (-x[0], -x[1].created_at))
        return [
            {**rec.to_dict(), "score": round(score, 4)}
            for score, rec in scored[:top_k] if score > 0
        ]

    def all(self) -> Iterable[dict[str, Any]]:
        return (rec.to_dict() for rec in self._records.values())

    def clear(self) -> None:
        self._records.clear()
        self._save()

    def health(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "count": len(self._records),
            "engine": "in-memory+json",
        }

    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8") or "[]")
        except (OSError, json.JSONDecodeError):
            return
        for item in data:
            try:
                rec = MemoryRecord(
                    id=item["id"], text=item["text"],
                    metadata=item.get("metadata", {}),
                    created_at=item.get("created_at", time.time()),
                )
                rec._vec = Counter(_tokenize(rec.text))
                self._records[rec.id] = rec
            except (KeyError, TypeError):
                continue

    def _save(self) -> None:
        try:
            self.path.write_text(
                json.dumps([r.to_dict() for r in self._records.values()],
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass
