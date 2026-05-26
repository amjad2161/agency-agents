"""
UnifiedMemory — single memory layer over all JARVIS BRAINIAC subsystems.

Wraps ``runtime/agency/long_term_memory.py`` (SQLite FTS5 — Pass 18 canonical)
and exposes:
    • episodic   → conversation events (rolling window + cold storage)
    • semantic   → distilled facts ("user prefers OMEGA_NEXUS XML format")
    • procedural → learned routines ("when X, do Y")
    • reference  → external pointers ("Linear INGEST tracks pipeline bugs")

If the upstream FTS5 module is unavailable (e.g. before runtime is installed),
falls back to a JSONL-based store so the orchestrator still runs.

FIXES (Code Review 2026-05-23):
  - [MEDIUM] Added threading.Lock for all SQLite writes → thread-safe under Flask workers
  - [MEDIUM] Added UPDATE + DELETE triggers to keep FTS5 index consistent
  - [MEDIUM] Tags stored as JSON array instead of CSV → commas in tag values safe
  - [LOW]    id field added to MemoryEntry + to_dict() so callers can reference/delete entries
  - [LOW]    FTS5 recall wraps query in quotes to handle special chars gracefully

FIXES (2026-05-27):
  - [CRITICAL] isolation_level=None (autocommit) on all connections — fixes read-isolation
               bug where new connections snapshotted DB before INSERT was visible
  - [CRITICAL] recall() LIKE fallback now correctly searches both content and tags columns
  - [MEDIUM]   Removed debug print statements; using stdlib logging at DEBUG level instead
  - [LOW]      forget() no longer calls commit() in autocommit mode (was a no-op, now clean)
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    kind: str            # episodic | semantic | procedural | reference
    content: str
    tags: list[str]
    ts: str
    source: str = ""
    id: Optional[int] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        # Remove id=None to keep backwards-compat; keep if set
        if d["id"] is None:
            del d["id"]
        return d


class UnifiedMemory:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        self.dir = self.root / ".jarvis_brainiac" / "memory"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.dir / "memory.db"
        self.fallback_path = self.dir / "memory.jsonl"
        # Single write lock — prevents "database is locked" under concurrent threads
        self._lock = threading.Lock()
        self._init_db()

    # ---------------------------------------------------------------- storage
    def _init_db(self) -> None:
        try:
            # isolation_level=None = autocommit — no implicit transactions
            # CR-003 FIX: WAL journal for better concurrent reads under Flask
            con = sqlite3.connect(self.db_path, isolation_level=None)
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=NORMAL")
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT,
                    ts TEXT NOT NULL,
                    source TEXT
                );
                CREATE INDEX IF NOT EXISTS memory_ts_idx ON memory(ts DESC);
                CREATE INDEX IF NOT EXISTS memory_kind_idx ON memory(kind);
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    content, tags, content='memory', content_rowid='id'
                );
                CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory BEGIN
                    INSERT INTO memory_fts(rowid, content, tags)
                    VALUES (new.id, new.content, new.tags);
                END;
                CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memory BEGIN
                    INSERT INTO memory_fts(memory_fts, rowid, content, tags)
                    VALUES ('delete', old.id, old.content, old.tags);
                END;
                CREATE TRIGGER IF NOT EXISTS memory_au AFTER UPDATE ON memory BEGIN
                    INSERT INTO memory_fts(memory_fts, rowid, content, tags)
                    VALUES ('delete', old.id, old.content, old.tags);
                    INSERT INTO memory_fts(rowid, content, tags)
                    VALUES (new.id, new.content, new.tags);
                END;
                """
            )
            con.close()
            self._mode = "sqlite-fts5"
            log.debug("UnifiedMemory: SQLite FTS5+WAL backend initialised at %s", self.db_path)
        except sqlite3.OperationalError:
            # FTS5 not available — fall back to JSONL
            self._mode = "jsonl"
            log.warning("UnifiedMemory: FTS5 unavailable, using JSONL fallback at %s", self.fallback_path)

    def _connect(self) -> sqlite3.Connection:
        # isolation_level=None = autocommit: every SELECT sees latest committed data.
        con = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")  # CR-003 FIX: WAL
        con.execute("PRAGMA synchronous=NORMAL")
        return con

    # --------------------------------------------------------------- public API
    def remember(self, kind: str, content: str,
                 tags: Optional[list[str]] = None,
                 source: str = "") -> MemoryEntry:
        """Store a memory entry and return it with its assigned id."""
        tags_list = tags or []
        entry = MemoryEntry(
            kind=kind,
            content=content,
            tags=tags_list,
            ts=datetime.now(timezone.utc).isoformat(),
            source=source,
        )
        if self._mode == "sqlite-fts5":
            tags_json = json.dumps(tags_list)
            with self._lock:  # serialize writes to prevent "database is locked"
                con = self._connect()  # autocommit — no explicit commit needed
                cur = con.execute(
                    "INSERT INTO memory (kind, content, tags, ts, source) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (entry.kind, entry.content, tags_json,
                     entry.ts, entry.source),
                )
                entry.id = cur.lastrowid
                con.close()
            log.debug("remember: inserted id=%s kind=%s tags=%s", entry.id, kind, tags_json)
        else:
            with self._lock:
                with self.fallback_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry.to_dict()) + "\n")
            log.debug("remember: appended to JSONL fallback")
        return entry

    def recall(self, query: str = "", kind: Optional[str] = None,
               limit: int = 10) -> list[MemoryEntry]:
        """Search memory for entries matching query (FTS5 or LIKE fallback).
        If query is empty, returns the most recent `limit` entries by timestamp.
        """
        log.debug("recall: mode=%s query=%r kind=%r limit=%s", self._mode, query, kind, limit)
        if self._mode == "sqlite-fts5":
            con = self._connect()
            # MR-005 FIX: empty string → return most recent entries by recency
            if not query or not query.strip():
                sql = "SELECT * FROM memory"
                params: list = []
                if kind:
                    sql += " WHERE kind = ?"
                    params.append(kind)
                sql += " ORDER BY ts DESC LIMIT ?"
                params.append(limit)
                rows = con.execute(sql, params).fetchall()
                con.close()
                return [self._row_to_entry(r) for r in rows]
            # Quote the query to handle special FTS5 characters safely
            safe_q = '"{}"'.format(query.replace('"', '""'))
            sql = (
                "SELECT m.* FROM memory_fts JOIN memory m ON memory_fts.rowid = m.id "
                "WHERE memory_fts MATCH ? "
            )
            params: list = [safe_q]
            if kind:
                sql += "AND m.kind = ? "
                params.append(kind)
            sql += "ORDER BY m.ts DESC LIMIT ?"
            params.append(limit)
            try:
                rows = con.execute(sql, params).fetchall()
                log.debug("recall: FTS5 MATCH returned %d rows", len(rows))
                # Fallback to LIKE on tags/content if MATCH returns empty
                # (e.g. FTS5 tokenizer strips special chars in short tokens)
                if not rows:
                    like_sql = "SELECT * FROM memory WHERE (content LIKE ? OR tags LIKE ?)"
                    like_params: list = [f"%{query}%", f"%{query}%"]
                    if kind:
                        like_sql += " AND kind = ?"
                        like_params.append(kind)
                    like_sql += " ORDER BY ts DESC LIMIT ?"
                    like_params.append(limit)
                    rows = con.execute(like_sql, like_params).fetchall()
                    log.debug("recall: LIKE fallback returned %d rows", len(rows))
            except sqlite3.OperationalError as exc:
                log.warning("recall: FTS5 error (%s), falling back to LIKE", exc)
                like_sql = "SELECT * FROM memory WHERE (content LIKE ? OR tags LIKE ?)"
                like_params = [f"%{query}%", f"%{query}%"]
                if kind:
                    like_sql += " AND kind = ?"
                    like_params.append(kind)
                like_sql += " ORDER BY ts DESC LIMIT ?"
                like_params.append(limit)
                rows = con.execute(like_sql, like_params).fetchall()
                log.debug("recall: error LIKE fallback returned %d rows", len(rows))
            con.close()
            return [self._row_to_entry(r) for r in rows]
        else:
            if not self.fallback_path.exists():
                return []
            entries: list[MemoryEntry] = []
            for line in self.fallback_path.read_text(encoding="utf-8").splitlines():
                try:
                    data = json.loads(line)
                    e = MemoryEntry(
                        kind=data["kind"], content=data["content"],
                        tags=data.get("tags", []), ts=data["ts"],
                        source=data.get("source", ""),
                        id=data.get("id"),
                    )
                    if kind and e.kind != kind:
                        continue
                    # Match query against content or any of the tags
                    q_lower = query.lower()
                    if q_lower in e.content.lower() or any(q_lower in t.lower() for t in e.tags):
                        entries.append(e)
                except Exception as exc:
                    log.debug("recall: JSONL parse error: %s", exc)
                    continue
            log.debug("recall: JSONL matched %d entries", len(entries))
            return entries[-limit:]

    def forget(self, entry_id: int) -> bool:
        """Delete a memory entry by its id. Returns True if a row was deleted."""
        if self._mode == "sqlite-fts5":
            with self._lock:
                con = self._connect()  # autocommit — no commit() needed
                cur = con.execute("DELETE FROM memory WHERE id = ?", (entry_id,))
                deleted = cur.rowcount > 0
                con.close()
            log.debug("forget: id=%s deleted=%s", entry_id, deleted)
            return deleted
        return False  # JSONL mode does not support targeted deletion

    def stats(self) -> dict:
        """Return summary statistics for the memory store."""
        if self._mode == "sqlite-fts5":
            # LR-005 FIX: acquire lock for consistent read during concurrent writes
            with self._lock:
                con = self._connect()
                total = con.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
                by_kind = dict(
                    con.execute(
                        "SELECT kind, COUNT(*) FROM memory GROUP BY kind"
                    ).fetchall()
                )
                con.close()
            return {"mode": self._mode, "total": total, "by_kind": by_kind}
        else:
            n = 0
            if self.fallback_path.exists():
                n = sum(1 for _ in self.fallback_path.open("r", encoding="utf-8"))
            return {"mode": self._mode, "total": n}

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
        # MR-012 FIX: removed legacy CSV tag parsing — all DBs use JSON arrays.
        # Old CSV format was used before 2026-04-01 WAL migration.
        raw_tags = row["tags"] or "[]"
        try:
            tags = json.loads(raw_tags)
        except (json.JSONDecodeError, ValueError):
            tags = []  # broken tags — default to empty
        return MemoryEntry(
            kind=row["kind"],
            content=row["content"],
            tags=tags,
            ts=row["ts"],
            source=row["source"] or "",
            id=row["id"],
        )
