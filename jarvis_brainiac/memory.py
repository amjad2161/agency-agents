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
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, asdict
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

    def to_dict(self) -> dict:
        return asdict(self)


class UnifiedMemory:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        self.dir = self.root / ".jarvis_brainiac" / "memory"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.dir / "memory.db"
        self.fallback_path = self.dir / "memory.jsonl"
        self._init_db()

    # ---------------------------------------------------------------- storage
    def _init_db(self) -> None:
        try:
            con = sqlite3.connect(self.db_path)
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
                """
            )
            con.commit()
            con.close()
            self._mode = "sqlite-fts5"
        except sqlite3.OperationalError:
            # FTS5 not available — fall back
            self._mode = "jsonl"

    # --------------------------------------------------------------- public API
    def remember(self, kind: str, content: str,
                 tags: Optional[list[str]] = None,
                 source: str = "") -> MemoryEntry:
        entry = MemoryEntry(
            kind=kind,
            content=content,
            tags=tags or [],
            ts=datetime.now(timezone.utc).isoformat(),
            source=source,
        )
        if self._mode == "sqlite-fts5":
            con = sqlite3.connect(self.db_path)
            con.execute(
                "INSERT INTO memory (kind, content, tags, ts, source) "
                "VALUES (?, ?, ?, ?, ?)",
                (entry.kind, entry.content, ",".join(entry.tags),
                 entry.ts, entry.source),
            )
            con.commit()
            con.close()
        else:
            with self.fallback_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        return entry

    def recall(self, query: str, kind: Optional[str] = None,
               limit: int = 10) -> list[MemoryEntry]:
        if self._mode == "sqlite-fts5":
            con = sqlite3.connect(self.db_path)
            con.row_factory = sqlite3.Row
            sql = (
                "SELECT m.* FROM memory_fts JOIN memory m ON memory_fts.rowid = m.id "
                "WHERE memory_fts MATCH ? "
            )
            params: list = [query]
            if kind:
                sql += "AND m.kind = ? "
                params.append(kind)
            sql += "ORDER BY m.ts DESC LIMIT ?"
            params.append(limit)
            rows = con.execute(sql, params).fetchall()
            con.close()
            return [self._row_to_entry(r) for r in rows]
        else:
            if not self.fallback_path.exists():
                return []
            entries = []
            for line in self.fallback_path.read_text(encoding="utf-8").splitlines():
                try:
                    e = MemoryEntry(**json.loads(line))
                    if kind and e.kind != kind:
                        continue
                    if query.lower() in e.content.lower():
                        entries.append(e)
                except Exception:
                    continue
            return entries[-limit:]

    def stats(self) -> dict:
        if self._mode == "sqlite-fts5":
            con = sqlite3.connect(self.db_path)
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
        return MemoryEntry(
            kind=row["kind"],
            content=row["content"],
            tags=(row["tags"] or "").split(",") if row["tags"] else [],
            ts=row["ts"],
            source=row["source"] or "",
        )
