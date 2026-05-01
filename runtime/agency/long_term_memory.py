"""Long-term memory with SQLite FTS5 full-text search."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

DEFAULT_DB_PATH = Path.home() / ".agency" / "ltm.db"


class LongTermMemory:
    """SQLite-backed long-term memory with FTS5 full-text search."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        if db_path is None:
            db_path = Path(os.environ.get("AGENCY_LTM_DB", DEFAULT_DB_PATH))
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._setup()

    def _setup(self) -> None:
        cur = self._conn.cursor()
        # Main records table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                content TEXT NOT NULL,
                embedding_json TEXT
            )
        """)
        # FTS5 virtual table
        cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
            USING fts5(content, category, content='memories', content_rowid='id')
        """)
        # Triggers to keep FTS in sync
        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_ai
            AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content, category)
                VALUES (new.id, new.content, new.category);
            END
        """)
        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_ad
            AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, category)
                VALUES ('delete', old.id, old.content, old.category);
            END
        """)
        self._conn.commit()

    def store(self, content: str, category: str = "general") -> int:
        """Store a memory entry and return its row id."""
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO memories (ts, category, content) VALUES (?, ?, ?)",
            (time.time(), category, content),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """FTS5 full-text search. Returns list of {id, ts, category, content, score}."""
        cur = self._conn.cursor()
        cur.execute("""
            SELECT m.id, m.ts, m.category, m.content,
                   bm25(memories_fts) AS score
            FROM memories_fts
            JOIN memories m ON memories_fts.rowid = m.id
            WHERE memories_fts MATCH ?
            ORDER BY score
            LIMIT ?
        """, (query, limit))
        return [dict(row) for row in cur.fetchall()]

    def recall(self, category: Optional[str] = None, limit: int = 20) -> list[dict]:
        """Return recent memories, optionally filtered by category."""
        cur = self._conn.cursor()
        if category:
            cur.execute(
                "SELECT id, ts, category, content FROM memories "
                "WHERE category = ? ORDER BY ts DESC LIMIT ?",
                (category, limit),
            )
        else:
            cur.execute(
                "SELECT id, ts, category, content FROM memories "
                "ORDER BY ts DESC LIMIT ?",
                (limit,),
            )
        return [dict(row) for row in cur.fetchall()]

    def forget(self, entry_id: int) -> bool:
        """Delete a specific memory entry. Returns True if deleted."""
        cur = self._conn.cursor()
        cur.execute("DELETE FROM memories WHERE id = ?", (entry_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def stats(self) -> dict:
        """Return {total_count, categories: {name: count}, db_size_bytes}."""
        cur = self._conn.cursor()
        cur.execute("SELECT COUNT(*) FROM memories")
        total = cur.fetchone()[0]
        cur.execute("SELECT category, COUNT(*) as cnt FROM memories GROUP BY category")
        categories = {row[0]: row[1] for row in cur.fetchall()}
        db_size = self._db_path.stat().st_size if self._db_path.exists() else 0
        return {
            "total_count": total,
            "categories": categories,
            "db_size_bytes": db_size,
        }

    def close(self) -> None:
        self._conn.close()
