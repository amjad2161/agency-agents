"""Long-term semantic memory backed by SQLite + FTS5.

Stores facts, observations, and learnings across sessions.

Schema
------
memories(key TEXT PK, value TEXT, tags TEXT, importance REAL, created_at REAL, updated_at REAL)
memories_fts  — FTS5 virtual table over (key, value, tags)

Usage
-----
    mem = LongTermMemory()
    mem.remember("user.name", "Amjad", tags=["profile"], importance=2.0)
    results = mem.recall("what is the user's name", top_k=3)
    mem.forget("user.name")
    mem.consolidate()

CLI helpers (registered in amjad_jarvis_cli.py):
    agency memory set "key" "value"
    agency memory get "query"
    agency memory list
    agency memory forget "key"
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .logging import get_logger

log = get_logger()

DEFAULT_DB_PATH = Path.home() / ".agency" / "long_term_memory.db"

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class MemoryEntry:
    key: str
    value: str
    tags: List[str] = field(default_factory=list)
    importance: float = 1.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def tags_str(self) -> str:
        return " ".join(self.tags)

    @classmethod
    def from_row(cls, row: tuple) -> "MemoryEntry":
        key, value, tags_str, importance, created_at, updated_at = row
        tags = tags_str.split() if tags_str else []
        return cls(
            key=key,
            value=value,
            tags=tags,
            importance=float(importance),
            created_at=float(created_at),
            updated_at=float(updated_at),
        )


@dataclass
class RecallResult:
    entry: MemoryEntry
    score: float


# ---------------------------------------------------------------------------
# LongTermMemory
# ---------------------------------------------------------------------------


class LongTermMemory:
    """SQLite + FTS5 long-term semantic memory store."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _ensure_schema(self) -> None:
        conn = self._connect()
        cur = conn.cursor()
        # Main table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                tags        TEXT NOT NULL DEFAULT '',
                importance  REAL NOT NULL DEFAULT 1.0,
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL
            )
        """)
        # FTS5 virtual table (content= references main table)
        try:
            cur.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                USING fts5(key, value, tags, content='memories', content_rowid='rowid')
            """)
        except sqlite3.OperationalError:
            # FTS5 unavailable — fall back to LIKE-based search
            log.debug("FTS5 not available; falling back to LIKE search")

        # Triggers to keep FTS in sync
        for event, action in [("INSERT", "INSERT"), ("DELETE", "DELETE"), ("UPDATE", "UPDATE")]:
            if event == "DELETE":
                cur.execute(f"""
                    CREATE TRIGGER IF NOT EXISTS memories_fts_{event.lower()}
                    AFTER {event} ON memories BEGIN
                        INSERT INTO memories_fts(memories_fts, rowid, key, value, tags)
                        VALUES('delete', old.rowid, old.key, old.value, old.tags);
                    END
                """)
            elif event == "INSERT":
                cur.execute(f"""
                    CREATE TRIGGER IF NOT EXISTS memories_fts_{event.lower()}
                    AFTER {event} ON memories BEGIN
                        INSERT INTO memories_fts(rowid, key, value, tags)
                        VALUES (new.rowid, new.key, new.value, new.tags);
                    END
                """)
            else:  # UPDATE
                cur.execute(f"""
                    CREATE TRIGGER IF NOT EXISTS memories_fts_{event.lower()}
                    AFTER {event} ON memories BEGIN
                        INSERT INTO memories_fts(memories_fts, rowid, key, value, tags)
                        VALUES('delete', old.rowid, old.key, old.value, old.tags);
                        INSERT INTO memories_fts(rowid, key, value, tags)
                        VALUES (new.rowid, new.key, new.value, new.tags);
                    END
                """)
        conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def remember(
        self,
        key: str,
        value: str,
        tags: Optional[List[str]] = None,
        importance: float = 1.0,
    ) -> MemoryEntry:
        """Store or update a memory entry."""
        now = time.time()
        tags_str = " ".join(tags or [])
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO memories (key, value, tags, importance, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value      = excluded.value,
                tags       = excluded.tags,
                importance = excluded.importance,
                updated_at = excluded.updated_at
        """, (key, value, tags_str, importance, now, now))
        conn.commit()
        log.debug("memory.remember key=%s importance=%s", key, importance)
        return MemoryEntry(key=key, value=value, tags=tags or [], importance=importance,
                           created_at=now, updated_at=now)

    def recall(self, query: str, top_k: int = 5) -> List[RecallResult]:
        """Search memories using FTS5 + TF-IDF-like relevance scoring.

        Falls back to LIKE search if FTS5 is unavailable.
        Returns up to ``top_k`` results sorted by score descending.
        """
        conn = self._connect()
        cur = conn.cursor()

        results: List[RecallResult] = []

        # --- Try FTS5 first ---
        try:
            # Sanitize query for FTS5 (escape special chars)
            fts_query = _sanitize_fts_query(query)
            cur.execute("""
                SELECT m.key, m.value, m.tags, m.importance, m.created_at, m.updated_at,
                       bm25(memories_fts) AS rank
                FROM memories_fts
                JOIN memories m ON memories_fts.rowid = m.rowid
                WHERE memories_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, top_k * 2))
            rows = cur.fetchall()

            for row in rows:
                entry = MemoryEntry.from_row(row[:6])
                raw_rank = float(row[6])  # bm25 returns negative (lower = better)
                # Convert to positive score, weight by importance
                score = max(0.0, -raw_rank) * entry.importance
                results.append(RecallResult(entry=entry, score=score))

        except sqlite3.OperationalError:
            # FTS5 unavailable — fallback LIKE search with TF-IDF approximation
            results = self._recall_fallback(query, top_k * 2)

        # Re-score with simple TF-IDF on top of FTS5 results
        if not results:
            results = self._recall_fallback(query, top_k * 2)

        # Sort by score descending, importance as tiebreaker
        results.sort(key=lambda r: (r.score, r.entry.importance), reverse=True)
        return results[:top_k]

    def _recall_fallback(self, query: str, limit: int) -> List[RecallResult]:
        """LIKE-based fallback with manual TF-IDF scoring."""
        tokens = _tokenize(query)
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT key, value, tags, importance, created_at, updated_at FROM memories")
        rows = cur.fetchall()

        results = []
        for row in rows:
            entry = MemoryEntry.from_row(tuple(row))
            doc = f"{entry.key} {entry.value} {entry.tags_str}".lower()
            doc_tokens = _tokenize(doc)
            score = _tfidf_score(tokens, doc_tokens) * entry.importance
            if score > 0:
                results.append(RecallResult(entry=entry, score=score))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def forget(self, key: str) -> bool:
        """Remove a memory by key. Returns True if it existed."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("DELETE FROM memories WHERE key = ?", (key,))
        conn.commit()
        deleted = cur.rowcount > 0
        if deleted:
            log.debug("memory.forget key=%s", key)
        return deleted

    def list_all(self) -> List[MemoryEntry]:
        """Return all memories sorted by importance desc, updated_at desc."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT key, value, tags, importance, created_at, updated_at
            FROM memories
            ORDER BY importance DESC, updated_at DESC
        """)
        return [MemoryEntry.from_row(tuple(r)) for r in cur.fetchall()]

    def consolidate(self) -> int:
        """Merge/dedup memories with identical key-hash.

        For each duplicated key (shouldn't happen with PK, but handles
        externally-imported data), keep the highest-importance entry.
        Also removes exact-duplicate (key, value) pairs.

        Returns number of entries removed.
        """
        conn = self._connect()
        cur = conn.cursor()

        # Find exact value duplicates for different keys
        cur.execute("""
            SELECT key, value, importance
            FROM memories
            ORDER BY importance DESC, updated_at DESC
        """)
        rows = cur.fetchall()

        seen_hashes: dict[str, str] = {}  # hash → primary key to keep
        to_delete: List[str] = []

        for row in rows:
            key, value, importance = row[0], row[1], row[2]
            h = hashlib.sha256(value.strip().lower().encode()).hexdigest()
            if h in seen_hashes:
                to_delete.append(key)
            else:
                seen_hashes[h] = key

        removed = 0
        for k in to_delete:
            cur.execute("DELETE FROM memories WHERE key = ?", (k,))
            removed += cur.rowcount

        conn.commit()
        log.debug("memory.consolidate removed=%d duplicates", removed)
        return removed

    def count(self) -> int:
        """Return total number of stored memories."""
        cur = self._connect().cursor()
        cur.execute("SELECT COUNT(*) FROM memories")
        return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset([
    "a", "an", "the", "is", "it", "in", "on", "at", "to", "of", "and",
    "or", "for", "with", "this", "that", "was", "are", "be", "by", "as",
    "i", "you", "he", "she", "we", "they", "do", "does", "did", "has",
    "have", "had", "will", "would", "can", "could", "should", "may",
])


def _tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


def _tfidf_score(query_tokens: List[str], doc_tokens: List[str]) -> float:
    """Simple TF-IDF-like score: sum of log(1 + tf) for matched terms."""
    if not doc_tokens:
        return 0.0
    doc_freq: dict[str, int] = {}
    for t in doc_tokens:
        doc_freq[t] = doc_freq.get(t, 0) + 1
    score = 0.0
    for qt in set(query_tokens):
        if qt in doc_freq:
            tf = doc_freq[qt] / len(doc_tokens)
            score += math.log1p(tf * 100)
    return score


def _sanitize_fts_query(query: str) -> str:
    """Convert a free-form query to a safe FTS5 MATCH expression."""
    # Remove FTS5 special chars, then join with OR
    tokens = re.findall(r"[a-zA-Z0-9]+", query)
    if not tokens:
        return '""'
    return " OR ".join(tokens)
