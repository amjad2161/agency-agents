"""Persistent memory: vector store + chat history + facts."""
from __future__ import annotations
import json, sqlite3, time, threading
from pathlib import Path
from typing import Optional


class Memory:
    """SQLite for chat history + ChromaDB for vector recall (lazy init)."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "memory.db"
        self.chroma_path = self.root / "chroma"
        self._lock = threading.RLock()
        self._chroma = None
        self._collection = None
        self._init_sqlite()

    def _init_sqlite(self):
        with self._lock:
            con = sqlite3.connect(self.db_path)
            con.executescript("""
                CREATE TABLE IF NOT EXISTS chat (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    lang TEXT
                );
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    key TEXT UNIQUE,
                    value TEXT NOT NULL,
                    source TEXT
                );
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    sha256 TEXT,
                    indexed_ts INTEGER,
                    bytes INTEGER,
                    snippet TEXT
                );
                CREATE TABLE IF NOT EXISTS skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    division TEXT,
                    path TEXT,
                    description TEXT,
                    invocations INTEGER DEFAULT 0,
                    last_used INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_chat_ts ON chat(ts);
                CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
            """)
            con.commit()
            con.close()

    # ---------- Chat ----------
    def add_chat(self, role: str, content: str, lang: str = "en"):
        with self._lock:
            con = sqlite3.connect(self.db_path)
            con.execute("INSERT INTO chat(ts, role, content, lang) VALUES(?,?,?,?)",
                        (int(time.time()), role, content, lang))
            con.commit()
            con.close()

    def recent_chat(self, n: int = 20) -> list[dict]:
        with self._lock:
            con = sqlite3.connect(self.db_path)
            rows = con.execute(
                "SELECT role, content FROM chat ORDER BY id DESC LIMIT ?", (n,)
            ).fetchall()
            con.close()
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    # ---------- Facts ----------
    def remember(self, key: str, value: str, source: str = "user"):
        with self._lock:
            con = sqlite3.connect(self.db_path)
            con.execute(
                "INSERT INTO facts(ts, key, value, source) VALUES(?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, ts=excluded.ts, source=excluded.source",
                (int(time.time()), key, value, source))
            con.commit()
            con.close()

    def recall(self, key: str) -> Optional[str]:
        with self._lock:
            con = sqlite3.connect(self.db_path)
            row = con.execute("SELECT value FROM facts WHERE key=?", (key,)).fetchone()
            con.close()
        return row[0] if row else None

    def all_facts(self) -> dict:
        with self._lock:
            con = sqlite3.connect(self.db_path)
            rows = con.execute("SELECT key, value FROM facts").fetchall()
            con.close()
        return dict(rows)

    # ---------- Vector (lazy) ----------
    def _get_chroma(self):
        if self._chroma is None:
            try:
                import chromadb
                self._chroma = chromadb.PersistentClient(path=str(self.chroma_path))
                self._collection = self._chroma.get_or_create_collection("jarvis_memory")
            except Exception:
                self._chroma = False  # mark failed
        return self._collection if self._chroma is not False else None

    def vector_add(self, doc_id: str, text: str, metadata: dict | None = None):
        col = self._get_chroma()
        if col is None: return False
        try:
            col.upsert(ids=[doc_id], documents=[text], metadatas=[metadata or {}])
            return True
        except Exception:
            return False

    def vector_search(self, query: str, n: int = 5) -> list[dict]:
        col = self._get_chroma()
        if col is None: return []
        try:
            r = col.query(query_texts=[query], n_results=n)
            results = []
            for i, doc_id in enumerate(r.get("ids", [[]])[0]):
                results.append({
                    "id": doc_id,
                    "document": r["documents"][0][i],
                    "metadata": (r.get("metadatas") or [[{}]])[0][i],
                    "distance": (r.get("distances") or [[0]])[0][i],
                })
            return results
        except Exception:
            return []

    # ---------- Files ----------
    def index_file(self, path: str, sha256: str, bytes_: int, snippet: str):
        with self._lock:
            con = sqlite3.connect(self.db_path)
            con.execute(
                "INSERT INTO files(path, sha256, indexed_ts, bytes, snippet) VALUES(?,?,?,?,?) "
                "ON CONFLICT(path) DO UPDATE SET sha256=excluded.sha256, indexed_ts=excluded.indexed_ts, snippet=excluded.snippet",
                (path, sha256, int(time.time()), bytes_, snippet))
            con.commit()
            con.close()

    def search_files(self, q: str, n: int = 10) -> list[dict]:
        with self._lock:
            con = sqlite3.connect(self.db_path)
            rows = con.execute(
                "SELECT path, snippet FROM files WHERE path LIKE ? OR snippet LIKE ? LIMIT ?",
                (f"%{q}%", f"%{q}%", n)).fetchall()
            con.close()
        return [{"path": r[0], "snippet": r[1]} for r in rows]

    # ---------- Skills ----------
    def register_skill(self, name: str, division: str, path: str, description: str):
        with self._lock:
            con = sqlite3.connect(self.db_path)
            con.execute(
                "INSERT INTO skills(name, division, path, description) VALUES(?,?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET division=excluded.division, path=excluded.path, description=excluded.description",
                (name, division, path, description))
            con.commit()
            con.close()

    def search_skills(self, q: str, n: int = 5) -> list[dict]:
        with self._lock:
            con = sqlite3.connect(self.db_path)
            rows = con.execute(
                "SELECT name, division, description, path FROM skills "
                "WHERE name LIKE ? OR description LIKE ? OR division LIKE ? LIMIT ?",
                (f"%{q}%", f"%{q}%", f"%{q}%", n)).fetchall()
            con.close()
        return [{"name": r[0], "division": r[1], "description": r[2], "path": r[3]} for r in rows]

    def mark_skill_used(self, name: str):
        with self._lock:
            con = sqlite3.connect(self.db_path)
            con.execute("UPDATE skills SET invocations=invocations+1, last_used=? WHERE name=?",
                        (int(time.time()), name))
            con.commit()
            con.close()
