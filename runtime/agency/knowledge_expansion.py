"""Knowledge-expansion store.

Append-only chunk store for ingested text/URL content. Supports
domain-scoped substring search. Designed as a lightweight
complement to `vector_memory` — when you don't need semantic
similarity, just want to look up "what did we ingest about X?".

Storage: JSONL at `~/.agency/knowledge.jsonl` (override via
`AGENCY_KNOWLEDGE_JSONL`). One chunk per line.

URL ingestion is opt-in: `ingest_url` only fetches if `httpx` is
importable AND the URL is non-private (consistent with the runtime's
SSRF rules in `tools.py`). A non-network build can still call
`ingest_text` for pre-fetched content.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


DEFAULT_KNOWLEDGE_JSONL = "knowledge.jsonl"


def knowledge_jsonl_path() -> Path:
    override = os.environ.get("AGENCY_KNOWLEDGE_JSONL")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".agency" / DEFAULT_KNOWLEDGE_JSONL


def _hash_id(content: str, source: str) -> str:
    h = hashlib.sha1((source + "::" + content).encode("utf-8"))
    return h.hexdigest()[:16]


_TAG_RE = re.compile(r"#(\w[\w-]{1,30})")


def _extract_tags(text: str) -> tuple[str, ...]:
    return tuple(sorted({m.lower() for m in _TAG_RE.findall(text)}))


@dataclass(frozen=True)
class KnowledgeChunk:
    """One ingested unit. Immutable; replaced by re-ingesting."""

    id: str
    source: str
    domain: str
    content: str
    tags: tuple[str, ...] = field(default_factory=tuple)
    embedding_hint: str = ""
    created_at: float = 0.0

    def to_json(self) -> str:
        d = asdict(self)
        d["tags"] = list(self.tags)
        return json.dumps(d, ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> "KnowledgeChunk":
        d = json.loads(line)
        d["tags"] = tuple(d.get("tags") or ())
        return cls(**d)


class KnowledgeExpansion:
    """Append-only ingest + simple substring/tag search."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or knowledge_jsonl_path()
        self._chunks: list[KnowledgeChunk] | None = None

    # ----- write side -----

    def ingest_text(
        self,
        text: str,
        *,
        domain: str = "default",
        source: str = "manual",
        embedding_hint: str = "",
    ) -> KnowledgeChunk:
        if not text.strip():
            raise ValueError("text must not be empty")
        chunk = KnowledgeChunk(
            id=_hash_id(text, source),
            source=source,
            domain=domain,
            content=text.strip(),
            tags=_extract_tags(text),
            embedding_hint=embedding_hint,
            created_at=time.time(),
        )
        self._append(chunk)
        return chunk

    def ingest_url(
        self,
        url: str,
        *,
        domain: str = "default",
        timeout_s: float = 10.0,
    ) -> KnowledgeChunk:
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("url must be http or https")
        try:
            import httpx  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "ingest_url requires httpx — `pip install httpx`"
            ) from e
        # Reuse the same SSRF guards the agent uses for web_fetch.
        try:
            from .tools import _is_metadata_host, _is_private_host  # type: ignore
        except ImportError:
            _is_private_host = lambda h: False  # noqa: E731
            _is_metadata_host = lambda h: False  # noqa: E731
        parsed = httpx.URL(url)
        host = parsed.host or ""
        if not host:
            raise ValueError("url has no host")
        if _is_metadata_host(host) or _is_private_host(host):
            raise PermissionError(
                f"refusing to fetch private/metadata host {host!r}"
            )
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.get(url, follow_redirects=True)
            resp.raise_for_status()
            text = resp.text
        return self.ingest_text(text, domain=domain, source=url)

    def _append(self, chunk: KnowledgeChunk) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(chunk.to_json() + "\n")
        if self._chunks is not None:
            self._chunks.append(chunk)

    # ----- read side -----

    def _load(self, *, refresh: bool = False) -> list[KnowledgeChunk]:
        if self._chunks is not None and not refresh:
            return self._chunks
        out: list[KnowledgeChunk] = []
        if self.path.is_file():
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(KnowledgeChunk.from_json(line))
                    except (ValueError, KeyError, TypeError):
                        continue
        self._chunks = out
        return out

    def search(
        self, query: str, *, domain: str | None = None, top_k: int = 5
    ) -> list[KnowledgeChunk]:
        """Substring / tag match scored by token overlap. Not a
        replacement for vector search — just a fast fallback when an
        embedding store isn't available."""
        if not query.strip():
            return []
        terms = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 2]
        if not terms:
            return []
        chunks = self._load()
        if domain is not None:
            chunks = [c for c in chunks if c.domain == domain]

        def score(c: KnowledgeChunk) -> int:
            body = c.content.lower()
            s = 0
            for t in terms:
                s += body.count(t)
                if t in c.tags:
                    s += 5  # tag hits are stronger than body hits
            return s

        scored = [(score(c), c) for c in chunks]
        scored = [(s, c) for (s, c) in scored if s > 0]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for (_, c) in scored[:top_k]]

    def stats(self) -> dict:
        chunks = self._load()
        domains: dict[str, int] = {}
        for c in chunks:
            domains[c.domain] = domains.get(c.domain, 0) + 1
        return {
            "total_chunks": len(chunks),
            "domains": domains,
            "path": str(self.path),
        }
