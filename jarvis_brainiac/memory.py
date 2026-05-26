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
"""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


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
        # FIX [MEDIUM]: single write lock — prevents "database is locked" under threads
        self._lock = threading.Lock()
        self._init_db()

    # ---------------------------------------------------------------- storage
    def _init_db(self) -> None:
        try:
            # isolation_level=None = autocommit — no implicit transactions
            con = sqlite3.connect(self.db_path, isolation_level=None)
            con.execute("PRAGMA journal_mode=DELETE")
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
        except sqlite3.OperationalError:
            # FTS5 not available — fall back
            self._mode = "jsonl"

    def _connect(self) -> sqlite3.Connection:
        # isolation_level=None = autocommit: every SELECT sees latest committed data.
        # This fixes the read-isolation problem where a new connection's implicit
        # deferred transaction would snapshot the DB before the INSERT was visible.
        con = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=DELETE")
        return con

    # --------------------------------------------------------------- public API
    def remember(self, kind: str, content: str,
                 tags: Optional[list[str]] = None,
                 source: str = "") -> MemoryEntry:
        # FIX [MEDIUM]: tags stored as JSON array — commas in values are safe
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
            with self._lock:  # FIX [MEDIUM]: serialize writes
                con = self._connect()  # autocommit mode — no explicit commit needed
                cur = con.execute(
                    "INSERT INTO memory (kind, content, tags, ts, source) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (entry.kind, entry.content, tags_json,
                     entry.ts, entry.source),
                )
                entry.id = cur.lastrowid
                # No con.commit() needed — isolation_level=None means autocommit
                con.close()
                print(f"[DEBUG REMEMBER] Inserted row id: {entry.id}, tags: {tags_json}, db_path: {self.db_path}")
        else:
            with self._lock:
                with self.fallback_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry.to_dict()) + "\n")
                print(f"[DEBUG REMEMBER] Appended fallback line, fallback_path: {self.fallback_path}")
        return entry

    def recall(self, query: str, kind: Optional[str] = None,
               limit: int = 10) -> list[MemoryEntry]:
        print(f"\n[DEBUG RECALL] Mode: {self._mode}, Query: '{query}', db_path: {self.db_path}, fallback_path: {self.fallback_path}")
        if self._mode == "sqlite-fts5":
            con = self._connect()
            sql = (
                "SELECT m.* FROM memory_fts JOIN memory m ON memory_fts.rowid = m.id "
                "WHERE memory_fts MATCH ? "
            )
            # FIX [LOW]: quote the query to handle special FTS5 chars safely
            safe_q = '"{}"'.format(query.replace('"', '""'))
            params: list = [safe_q]
            if kind:
                sql += "AND m.kind = ? "
                params.append(kind)
            sql += "ORDER BY m.ts DESC LIMIT ?"
            params.append(limit)
            try:
                rows = con.execute(sql, params).fetchall()
                print(f"[DEBUG RECALL] FTS5 MATCH rows count: {len(rows)}")
                # Fallback to LIKE on tags/content if MATCH returns empty (e.g. tokenizer mismatch)
                if not rows:
                    like_sql = "SELECT * FROM memory WHERE (content LIKE ? OR tags LIKE ?)"
                    like_params = [f"%{query}%", f"%{query}%"]
                    if kind:
                        like_sql += " AND kind = ?"
                        like_params.append(kind)
                    like_sql += " ORDER BY ts DESC LIMIT ?"
                    like_params.append(limit)
                    rows = con.execute(like_sql, like_params).fetchall()
                    print(f"[DEBUG RECALL] Fallback LIKE rows count: {len(rows)}")
            except sqlite3.OperationalError as e:
                print(f"[DEBUG RECALL] sqlite3.OperationalError: {e}")
                # Fallback: simple LIKE if FTS syntax fails (e.g. empty query)
                like_sql = "SELECT * FROM memory WHERE (content LIKE ? OR tags LIKE ?)"
                like_params = [f"%{query}%", f"%{query}%"]
                if kind:
                    like_sql += " AND kind = ?"
                    like_params.append(kind)
                like_sql += " ORDER BY ts DESC LIMIT ?"
                like_params.append(limit)
                rows = con.execute(like_sql, like_params).fetchall()
                print(f"[DEBUG RECALL] Error Fallback LIKE rows count: {len(rows)}")
            con.close()
            return [self._row_to_entry(r) for r in rows]
        else:
            print(f"[DEBUG RECALL] Reading fallback file exists: {self.fallback_path.exists()}")
            if not self.fallback_path.exists():
                return []
            entries = []
            file_content = self.fallback_path.read_text(encoding="utf-8")
            print(f"[DEBUG RECALL] fallback file content lines: {len(file_content.splitlines())}")
            for line in file_content.splitlines():
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
                    if query.lower() in e.content.lower() or any(query.lower() in t.lower() for t in e.tags):
                        entries.append(e)
                except Exception as exc:
                    print(f"[DEBUG RECALL] json parse error: {exc}")
                    continue
            print(f"[DEBUG RECALL] Fallback JSONL matched count: {len(entries)}")
            return entries[-limit:]

    def forget(self, entry_id: int) -> bool:
        """Delete a memory entry by its id. Returns True if deleted."""
        if self._mode == "sqlite-fts5":
            with self._lock:
                con = self._connect()
                cur = con.execute("DELETE FROM memory WHERE id = ?", (entry_id,))
                deleted = cur.rowcount > 0
                con.commit()
                con.close()
            return deleted
        return False  # JSONL mode doesn't support targeted deletion

    def stats(self) -> dict:
        if self._mode == "sqlite-fts5":
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
        # FIX [MEDIUM]: tags are now JSON; fall back to CSV split for legacy DBs
        raw_tags = row["tags"] or ""
        try:
            tags = json.loads(raw_tags) if raw_tags.startswith("[") else [t for t in raw_tags.split(",") if t]
        except (json.JSONDecodeError, ValueError):
            tags = [t for t in raw_tags.split(",") if t]
        return MemoryEntry(
            kind=row["kind"],
            content=row["content"],
            tags=tags,
            ts=row["ts"],
            source=row["source"] or "",
            id=row["id"],
        )
