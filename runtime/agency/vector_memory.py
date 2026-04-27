"""Vector memory: similarity search over the cross-session lessons journal.

Pure-Python implementation — no external embedding model, no pip
installs at import time. Uses a TF-IDF representation with a SQLite
backing store, which gives us:

  - Persistent, cumulative storage across sessions
  - O(log n) lookup by ID
  - Cosine similarity ranking on top-K queries
  - Zero new dependencies (sqlite3 is in the stdlib)

The trade-off vs sentence-transformers / dense embeddings: TF-IDF
matches on shared vocabulary, not semantic meaning. For a personal
lessons journal — full of concrete tokens like file paths, error
messages, and tool names — that's actually a strength: the lookup is
precise and explainable. Swap in a dense model later if needed via
`set_embedder()`.

Usage:

    from agency.vector_memory import VectorMemory
    vm = VectorMemory()
    vm.upsert("lesson-1", "the trust gate ships well")
    vm.upsert("lesson-2", "rm -rf $UNDEFINED expanded to rm -rf /")
    hits = vm.search("the rm danger", k=3)
    for h in hits:
        print(h.score, h.id, h.text[:80])
"""

from __future__ import annotations

import math
import os
import re
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

# Default location: ~/.agency/vector_memory.db
DEFAULT_DB = Path.home() / ".agency" / "vector_memory.db"

# Tokenizer: split on whitespace + punctuation, lowercase, drop very
# short tokens. Keep `_` and `.` so paths and identifiers stay intact.
_TOKEN_RE = re.compile(r"[A-Za-z0-9_\./]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1]


@dataclass(frozen=True)
class Hit:
    id: str
    text: str
    score: float
    metadata: dict


def _vector_path() -> Path:
    override = os.environ.get("AGENCY_VECTOR_DB")
    if override:
        return Path(override).expanduser()
    return DEFAULT_DB


class VectorMemory:
    """A simple TF-IDF vector store with a SQLite backing file.

    Thread-safe per-instance via `check_same_thread=False` and the GIL —
    the runtime instantiates one VectorMemory per Executor run, so
    concurrent writes from a single agent loop are serialized.
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or _vector_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            isolation_level=None,  # autocommit
        )
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._embedder: Callable[[str], dict[str, float]] | None = None
        self._init_schema()

    # ----- schema --------------------------------------------------

    def _init_schema(self) -> None:
        c = self._conn
        c.execute("""
            CREATE TABLE IF NOT EXISTS docs (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS terms (
                doc_id TEXT NOT NULL,
                term TEXT NOT NULL,
                tf REAL NOT NULL,
                PRIMARY KEY (doc_id, term),
                FOREIGN KEY (doc_id) REFERENCES docs(id) ON DELETE CASCADE
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_terms_term ON terms(term);")

    # ----- write path ---------------------------------------------

    def upsert(self, doc_id: str, text: str, metadata: dict | None = None) -> None:
        """Insert or replace a document. Recomputes its TF vector."""
        import json as _json

        now = time.time()
        meta_json = _json.dumps(metadata or {}, default=str)
        with self._conn:
            self._conn.execute(
                "INSERT INTO docs (id, text, metadata, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET text=excluded.text, "
                "metadata=excluded.metadata, updated_at=excluded.updated_at",
                (doc_id, text, meta_json, now, now),
            )
            self._conn.execute("DELETE FROM terms WHERE doc_id=?", (doc_id,))
            tf = self._tf(text)
            self._conn.executemany(
                "INSERT INTO terms (doc_id, term, tf) VALUES (?, ?, ?)",
                [(doc_id, t, w) for t, w in tf.items()],
            )

    def delete(self, doc_id: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM docs WHERE id=?", (doc_id,))

    def clear(self) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM terms")
            self._conn.execute("DELETE FROM docs")

    # ----- read path ----------------------------------------------

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]

    def get(self, doc_id: str) -> tuple[str, dict] | None:
        import json as _json

        row = self._conn.execute(
            "SELECT text, metadata FROM docs WHERE id=?", (doc_id,)
        ).fetchone()
        if not row:
            return None
        return row[0], _json.loads(row[1] or "{}")

    def search(self, query: str, k: int = 5) -> list[Hit]:
        """Return the top-k documents by cosine similarity."""
        import json as _json

        q_tf = self._tf(query)
        if not q_tf:
            return []

        n_docs = self.count()
        if n_docs == 0:
            return []

        # IDF for query terms only — that's all we need to compute similarity.
        idf: dict[str, float] = {}
        for term in q_tf:
            row = self._conn.execute(
                "SELECT COUNT(DISTINCT doc_id) FROM terms WHERE term=?", (term,)
            ).fetchone()
            df = row[0] if row else 0
            # add-one smoothing so a term that appears in every doc still has
            # a finite, small weight (avoids log(1)=0 collapsing the score).
            idf[term] = math.log((n_docs + 1) / (df + 1)) + 1.0

        q_vec = {t: q_tf[t] * idf[t] for t in q_tf}
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0

        # Aggregate: for each candidate doc, sum tf * idf for matching terms.
        # Only docs that share at least one query term can have non-zero score.
        params = list(q_tf.keys())
        placeholders = ",".join("?" * len(params))
        rows = self._conn.execute(
            f"""
            SELECT doc_id, term, tf
            FROM terms
            WHERE term IN ({placeholders})
            """,
            params,
        ).fetchall()

        # Score per doc.
        scores: dict[str, float] = {}
        for doc_id, term, tf in rows:
            scores[doc_id] = scores.get(doc_id, 0.0) + tf * idf[term] * q_vec[term]

        # Normalize by doc vector magnitude — fetch each doc's full TF.
        candidate_ids = list(scores.keys())
        if not candidate_ids:
            return []
        ph = ",".join("?" * len(candidate_ids))
        all_rows = self._conn.execute(
            f"SELECT doc_id, term, tf FROM terms WHERE doc_id IN ({ph})",
            candidate_ids,
        ).fetchall()

        # Build per-doc full vectors, lazily compute idf for any term in it.
        doc_vec_norms: dict[str, float] = {}
        # Need IDF for all terms in candidate docs to normalize.
        all_terms_in_docs = list({term for _, term, _ in all_rows})
        idf_full = dict(idf)  # start with what we have
        missing = [t for t in all_terms_in_docs if t not in idf_full]
        if missing:
            # fetch DF for missing terms in one round-trip
            ph_m = ",".join("?" * len(missing))
            df_rows = self._conn.execute(
                f"SELECT term, COUNT(DISTINCT doc_id) "
                f"FROM terms WHERE term IN ({ph_m}) GROUP BY term",
                missing,
            ).fetchall()
            df_map = {t: df for t, df in df_rows}
            for t in missing:
                df = df_map.get(t, 0)
                idf_full[t] = math.log((n_docs + 1) / (df + 1)) + 1.0

        # Aggregate per-doc magnitudes.
        per_doc: dict[str, float] = {}
        for doc_id, term, tf in all_rows:
            w = tf * idf_full[term]
            per_doc[doc_id] = per_doc.get(doc_id, 0.0) + w * w
        for doc_id, sq in per_doc.items():
            doc_vec_norms[doc_id] = math.sqrt(sq) or 1.0

        results: list[Hit] = []
        for doc_id, score in scores.items():
            cosine = score / (q_norm * doc_vec_norms.get(doc_id, 1.0))
            row = self._conn.execute(
                "SELECT text, metadata FROM docs WHERE id=?", (doc_id,)
            ).fetchone()
            if row:
                results.append(Hit(
                    id=doc_id, text=row[0],
                    score=cosine,
                    metadata=_json.loads(row[1] or "{}"),
                ))
        results.sort(key=lambda h: h.score, reverse=True)
        return results[:k]

    # ----- internals ----------------------------------------------

    def _tf(self, text: str) -> dict[str, float]:
        """Term frequencies (sub-linearly scaled — log(1 + count))."""
        if self._embedder is not None:
            return self._embedder(text)
        tokens = _tokenize(text)
        if not tokens:
            return {}
        counts = Counter(tokens)
        n = len(tokens)
        return {t: math.log1p(c) / math.log1p(n) for t, c in counts.items()}

    def set_embedder(self, fn: Callable[[str], dict[str, float]]) -> None:
        """Override the default TF tokenizer with a custom embedder.

        The function should take raw text and return a {term: weight}
        dict. Useful for swapping in a dense model wrapper later.
        """
        self._embedder = fn

    # ----- batch helpers ------------------------------------------

    def upsert_many(self, items: Iterable[tuple[str, str, dict | None]]) -> int:
        """Bulk upsert. Returns number of documents written."""
        n = 0
        for doc_id, text, meta in items:
            self.upsert(doc_id, text, meta)
            n += 1
        return n

    def all_ids(self) -> list[str]:
        return [r[0] for r in self._conn.execute(
            "SELECT id FROM docs ORDER BY updated_at DESC"
        ).fetchall()]

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass


# ----- lessons-journal indexing ------------------------------------

def index_lessons(vm: VectorMemory, lessons_text: str) -> int:
    """Split a lessons.md body into individual entries and index each.

    Convention: each entry starts with `## <date> · <topic>`. Anything
    before the first such header is skipped (the file header).
    Returns the number of entries indexed.
    """
    # Split on `\n## ` boundaries — keep the headers attached.
    parts = re.split(r"\n(?=## )", "\n" + (lessons_text or ""))
    n = 0
    for part in parts:
        part = part.strip()
        if not part.startswith("## "):
            continue
        first_line = part.splitlines()[0]
        # ID = the header itself (date + topic), good enough for upsert.
        doc_id = first_line[3:].strip()[:200] or f"entry-{n}"
        vm.upsert(doc_id, part, {"kind": "lesson"})
        n += 1
    return n
