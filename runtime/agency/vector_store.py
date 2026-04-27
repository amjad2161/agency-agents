"""Vector storage for agent memory.

Inspired by ChromaDB. Two backends:
- TFIDFVectorStore: in-memory TF-IDF cosine similarity, no deps
- ChromaVectorStore: persistent, requires `chromadb` (optional)

The `AgentMemory` facade hides the backend choice and adds TTL,
agent-namespacing, and metadata filtering.
"""

from __future__ import annotations

import math
import re
import threading
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .logging import get_logger

log = get_logger()

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


@dataclass
class VectorEntry:
    """One stored entry with its embedding and metadata."""

    id: str
    content: str
    embedding: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    agent_id: str = "default"
    ttl_seconds: float | None = None

    def is_expired(self, now: float | None = None) -> bool:
        if self.ttl_seconds is None:
            return False
        return (now or time.time()) > self.created_at + self.ttl_seconds

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TFIDFVectorStore:
    """In-memory TF-IDF cosine similarity store. No external deps."""

    def __init__(self) -> None:
        self.entries: dict[str, VectorEntry] = {}
        self.df: Counter[str] = Counter()  # document frequency
        self._lock = threading.RLock()

    def _idf(self, term: str) -> float:
        n = len(self.entries)
        if n == 0:
            return 0.0
        return math.log((1 + n) / (1 + self.df.get(term, 0))) + 1.0

    def _tfidf_vec(self, text: str) -> dict[str, float]:
        tokens = _tokenize(text)
        if not tokens:
            return {}
        tf = Counter(tokens)
        return {term: (count / len(tokens)) * self._idf(term) for term, count in tf.items()}

    @staticmethod
    def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        # iterate smaller
        small, large = (a, b) if len(a) <= len(b) else (b, a)
        dot = sum(v * large.get(k, 0.0) for k, v in small.items())
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def add(self, entry: VectorEntry) -> str:
        with self._lock:
            self.entries[entry.id] = entry
            for term in set(_tokenize(entry.content)):
                self.df[term] += 1
            return entry.id

    def get(self, id: str) -> VectorEntry | None:
        return self.entries.get(id)

    def delete(self, id: str) -> bool:
        with self._lock:
            entry = self.entries.pop(id, None)
            if entry is None:
                return False
            for term in set(_tokenize(entry.content)):
                self.df[term] = max(0, self.df[term] - 1)
                if self.df[term] == 0:
                    del self.df[term]
            return True

    def query(
        self,
        text: str,
        top_k: int = 5,
        agent_id: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[tuple[VectorEntry, float]]:
        qvec = self._tfidf_vec(text)
        out: list[tuple[VectorEntry, float]] = []
        now = time.time()
        with self._lock:
            for entry in self.entries.values():
                if entry.is_expired(now):
                    continue
                if agent_id is not None and entry.agent_id != agent_id:
                    continue
                if metadata_filter:
                    if any(entry.metadata.get(k) != v for k, v in metadata_filter.items()):
                        continue
                evec = self._tfidf_vec(entry.content)
                score = self._cosine(qvec, evec)
                out.append((entry, score))
        out.sort(key=lambda t: t[1], reverse=True)
        return out[:top_k]

    def all_entries(self) -> list[VectorEntry]:
        return list(self.entries.values())

    def __len__(self) -> int:
        return len(self.entries)


class ChromaVectorStore:
    """ChromaDB-backed store. Requires chromadb. Optional."""

    def __init__(self, collection: str = "agency", persist_dir: str | None = None) -> None:
        try:
            import chromadb  # type: ignore
        except ImportError as e:
            raise RuntimeError(f"chromadb not installed: {e}")
        if persist_dir:
            self.client = chromadb.PersistentClient(path=persist_dir)
        else:
            self.client = chromadb.Client()
        self.collection = self.client.get_or_create_collection(name=collection)
        self._lock = threading.RLock()

    def add(self, entry: VectorEntry) -> str:  # pragma: no cover
        with self._lock:
            self.collection.add(
                ids=[entry.id],
                documents=[entry.content],
                metadatas=[
                    {
                        **entry.metadata,
                        "agent_id": entry.agent_id,
                        "created_at": entry.created_at,
                        "ttl_seconds": entry.ttl_seconds or -1,
                    }
                ],
            )
            return entry.id

    def query(
        self,
        text: str,
        top_k: int = 5,
        agent_id: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[tuple[VectorEntry, float]]:  # pragma: no cover
        where = dict(metadata_filter or {})
        if agent_id is not None:
            where["agent_id"] = agent_id
        res = self.collection.query(
            query_texts=[text], n_results=top_k, where=where or None
        )
        out: list[tuple[VectorEntry, float]] = []
        for i, doc in enumerate(res.get("documents", [[]])[0]):
            md = res.get("metadatas", [[]])[0][i] or {}
            score = 1.0 - float(res.get("distances", [[0.0]])[0][i])
            entry = VectorEntry(
                id=res["ids"][0][i],
                content=doc,
                metadata={k: v for k, v in md.items() if k not in {"agent_id", "created_at", "ttl_seconds"}},
                agent_id=md.get("agent_id", "default"),
                created_at=float(md.get("created_at", time.time())),
                ttl_seconds=None if md.get("ttl_seconds", -1) == -1 else float(md["ttl_seconds"]),
            )
            out.append((entry, score))
        return out

    def delete(self, id: str) -> bool:  # pragma: no cover
        with self._lock:
            try:
                self.collection.delete(ids=[id])
                return True
            except Exception:
                return False

    def all_entries(self) -> list[VectorEntry]:  # pragma: no cover
        return []


class AgentMemory:
    """Facade over a vector backend with TTL, namespacing, and metadata."""

    def __init__(self, backend: TFIDFVectorStore | ChromaVectorStore | None = None) -> None:
        self.backend = backend or TFIDFVectorStore()

    def store(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
        agent_id: str = "default",
        ttl: float | None = None,
    ) -> str:
        entry = VectorEntry(
            id=uuid.uuid4().hex,
            content=content,
            metadata=dict(metadata or {}),
            agent_id=agent_id,
            ttl_seconds=ttl,
        )
        return self.backend.add(entry)

    def search(
        self,
        query: str,
        agent_id: str | None = None,
        top_k: int = 5,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[VectorEntry]:
        results = self.backend.query(
            query, top_k=top_k, agent_id=agent_id, metadata_filter=metadata_filter
        )
        return [r[0] for r in results]

    def search_with_scores(
        self, query: str, agent_id: str | None = None, top_k: int = 5
    ) -> list[tuple[VectorEntry, float]]:
        return self.backend.query(query, top_k=top_k, agent_id=agent_id)

    def delete(self, id: str) -> bool:
        return self.backend.delete(id)

    def expire_old(self) -> int:
        if not isinstance(self.backend, TFIDFVectorStore):
            return 0
        now = time.time()
        expired = [e.id for e in self.backend.all_entries() if e.is_expired(now)]
        for id in expired:
            self.backend.delete(id)
        return len(expired)

    def __len__(self) -> int:
        if isinstance(self.backend, TFIDFVectorStore):
            return len(self.backend)
        return 0


def get_vector_store(backend: str = "tfidf", **kwargs) -> AgentMemory:
    """Factory. backend ∈ {tfidf, chroma}."""
    if backend == "tfidf":
        return AgentMemory(TFIDFVectorStore())
    if backend == "chroma":
        return AgentMemory(ChromaVectorStore(**kwargs))
    raise ValueError(f"unknown backend: {backend}")


__all__ = [
    "VectorEntry",
    "TFIDFVectorStore",
    "ChromaVectorStore",
    "AgentMemory",
    "get_vector_store",
]
