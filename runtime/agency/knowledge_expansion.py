"""Knowledge expansion — fetch, summarise, and ingest new knowledge into JARVIS.

Pipeline:
  fetch(url/text) → chunk → summarise → tag → store in ContextManager / VectorStore
"""

from __future__ import annotations

import hashlib
import re
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .logging import get_logger

log = get_logger()

DEFAULT_CHUNK_SIZE = 800   # words per chunk
DEFAULT_CHUNK_OVERLAP = 80


@dataclass
class KnowledgeChunk:
    """One processed chunk of ingested knowledge."""

    chunk_id: str
    source: str
    text: str
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    domain: str = "general"
    ingested_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class KnowledgeExpansion:
    """Fetch → chunk → summarise → tag → persist new knowledge.

    Usage::

        ke = KnowledgeExpansion()
        chunks = ke.ingest_text("Transformers use self-attention...", domain="AI")
        chunks = ke.ingest_url("https://arxiv.org/abs/1706.03762", domain="AI")
        results = ke.search("attention mechanism")
    """

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        context_manager: Any | None = None,
        vector_store: Any | None = None,
    ) -> None:
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._context_manager = context_manager
        self._vector_store = vector_store
        self._chunks: list[KnowledgeChunk] = []

    # ── public API ────────────────────────────────────────────────────────────

    def ingest_text(
        self,
        text: str,
        source: str = "manual",
        domain: str = "general",
        tags: list[str] | None = None,
    ) -> list[KnowledgeChunk]:
        """Chunk, summarise, and store *text*. Returns list of KnowledgeChunk."""
        tags = tags or self._auto_tag(text, domain)
        raw_chunks = self._split(text)
        chunks: list[KnowledgeChunk] = []

        for i, chunk_text in enumerate(raw_chunks):
            cid = self._chunk_id(source, i, chunk_text)
            summary = self._summarise(chunk_text)
            chunk = KnowledgeChunk(
                chunk_id=cid,
                source=source,
                text=chunk_text,
                summary=summary,
                tags=list(tags),
                domain=domain,
            )
            chunks.append(chunk)
            self._store_chunk(chunk)

        log.info("knowledge_expansion: ingested %d chunks from '%s'", len(chunks), source)
        return chunks

    def ingest_url(
        self,
        url: str,
        domain: str = "general",
        tags: list[str] | None = None,
        timeout: float = 10.0,
    ) -> list[KnowledgeChunk]:
        """Fetch URL, extract text, and ingest. Falls back to stub on failure."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-KB/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            text = self._strip_html(raw)
            log.info("knowledge_expansion: fetched %d chars from %s", len(text), url)
        except Exception as exc:
            log.warning("knowledge_expansion: fetch failed for %s — %s", url, exc)
            text = f"[fetch failed: {exc}]"

        return self.ingest_text(text, source=url, domain=domain, tags=tags)

    def search(
        self,
        query: str,
        domain: str | None = None,
        top_k: int = 5,
    ) -> list[KnowledgeChunk]:
        """Simple keyword search over ingested chunks.

        Delegates to VectorStore if available; falls back to BM25-style overlap.
        """
        if self._vector_store and hasattr(self._vector_store, "search"):
            try:
                results = self._vector_store.search(query, top_k=top_k)
                # VectorStore returns list[dict]; convert to KnowledgeChunk if possible
                return [
                    KnowledgeChunk(
                        chunk_id=r.get("id", ""),
                        source=r.get("source", ""),
                        text=r.get("text", ""),
                        summary=r.get("summary", ""),
                        tags=r.get("tags", []),
                        domain=r.get("domain", "general"),
                    )
                    for r in results[:top_k]
                ]
            except Exception as e:  # noqa: BLE001
                log.warning("knowledge_expansion: vector search failed: %s", e)

        # Fallback: keyword overlap
        query_terms = set(query.lower().split())
        scored: list[tuple[float, KnowledgeChunk]] = []
        for chunk in self._chunks:
            if domain and chunk.domain != domain:
                continue
            chunk_words = set((chunk.text + " " + chunk.summary).lower().split())
            overlap = len(query_terms & chunk_words) / max(len(query_terms), 1)
            if overlap > 0:
                scored.append((overlap, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:top_k]]

    def list_domains(self) -> list[str]:
        return list({c.domain for c in self._chunks})

    def stats(self) -> dict[str, Any]:
        return {
            "total_chunks": len(self._chunks),
            "domains": self.list_domains(),
            "sources": list({c.source for c in self._chunks}),
        }

    # ── internals ─────────────────────────────────────────────────────────────

    def _split(self, text: str) -> list[str]:
        """Split text into overlapping word-based chunks."""
        words = text.split()
        if len(words) <= self._chunk_size:
            return [text]
        chunks: list[str] = []
        step = self._chunk_size - self._chunk_overlap
        for start in range(0, len(words), step):
            chunk = " ".join(words[start : start + self._chunk_size])
            chunks.append(chunk)
            if start + self._chunk_size >= len(words):
                break
        return chunks

    def _summarise(self, text: str) -> str:
        """Extractive summary: first 2 sentences."""
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        return " ".join(sentences[:2])

    def _auto_tag(self, text: str, domain: str) -> list[str]:
        """Heuristic tagging from frequent content words."""
        stopwords = {
            "the", "a", "an", "is", "in", "of", "to", "and", "for",
            "that", "this", "with", "are", "was", "be", "as", "at",
        }
        words = [w.lower().strip(".,;:!?\"'()") for w in text.split()]
        freq: dict[str, int] = {}
        for w in words:
            if len(w) > 4 and w not in stopwords:
                freq[w] = freq.get(w, 0) + 1
        top = sorted(freq, key=lambda k: freq[k], reverse=True)[:5]
        return [domain] + top

    def _chunk_id(self, source: str, idx: int, text: str) -> str:
        digest = hashlib.md5(text[:100].encode()).hexdigest()[:8]
        return f"{source[:20]}-{idx}-{digest}"

    def _store_chunk(self, chunk: KnowledgeChunk) -> None:
        self._chunks.append(chunk)

        if self._context_manager:
            try:
                self._context_manager.store(
                    key=chunk.chunk_id,
                    value=chunk.to_dict(),
                    domain=f"kb:{chunk.domain}",
                    tags=chunk.tags,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("knowledge_expansion: context_manager store failed: %s", e)

        if self._vector_store and hasattr(self._vector_store, "add"):
            try:
                self._vector_store.add(
                    chunk.text,
                    metadata={
                        "id": chunk.chunk_id,
                        "source": chunk.source,
                        "summary": chunk.summary,
                        "tags": chunk.tags,
                        "domain": chunk.domain,
                    },
                )
            except Exception as e:  # noqa: BLE001
                log.warning("knowledge_expansion: vector_store add failed: %s", e)

    @staticmethod
    def _strip_html(html: str) -> str:
        """Strip HTML tags and collapse whitespace."""
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
