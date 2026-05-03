"""
Local Vector Memory for JARVIS BRAINIAC
======================================
100% local vector database using ChromaDB and FAISS.
Stores capabilities, conversations, learned skills.
Zero cloud dependency.

Architecture:
    ChromaDB (persistent) → FAISS (in-memory) → MockMemory (dict + JSON)
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Dependency probes  (lazy, fail-soft)
# ---------------------------------------------------------------------------
_CHROMADB_AVAILABLE = False
_FAISS_AVAILABLE = False
_SENTENCE_TRANSFORMERS_AVAILABLE = False


def _probe_chromadb() -> bool:
    global _CHROMADB_AVAILABLE
    if _CHROMADB_AVAILABLE:
        return True
    try:
        import chromadb
        _CHROMADB_AVAILABLE = True
    except Exception:
        _CHROMADB_AVAILABLE = False
    return _CHROMADB_AVAILABLE


def _probe_faiss() -> bool:
    global _FAISS_AVAILABLE
    if _FAISS_AVAILABLE:
        return True
    try:
        import faiss
        _FAISS_AVAILABLE = True
    except Exception:
        _FAISS_AVAILABLE = False
    return _FAISS_AVAILABLE


def _probe_sentence_transformers() -> bool:
    global _SENTENCE_TRANSFORMERS_AVAILABLE
    if _SENTENCE_TRANSFORMERS_AVAILABLE:
        return True
    try:
        import sentence_transformers
        _SENTENCE_TRANSFORMERS_AVAILABLE = True
    except Exception:
        _SENTENCE_TRANSFORMERS_AVAILABLE = False
    return _SENTENCE_TRANSFORMERS_AVAILABLE


# ---------------------------------------------------------------------------
# Base memory interface
# ---------------------------------------------------------------------------
class BaseVectorMemory(ABC):
    """Abstract base for all vector memory backends."""

    @abstractmethod
    def store(
        self,
        collection: str,
        text: str,
        metadata: dict | None = None,
        doc_id: str | None = None,
    ) -> str:
        ...

    @abstractmethod
    def search(self, collection: str, query: str, top_k: int = 5) -> list[dict]:
        ...

    @abstractmethod
    def get(self, collection: str, doc_id: str) -> dict | None:
        ...

    @abstractmethod
    def delete(self, collection: str, doc_id: str) -> bool:
        ...

    @abstractmethod
    def list_collections(self) -> list[str]:
        ...

    @abstractmethod
    def stats(self) -> dict[str, Any]:
        ...

    # -- specialised helpers ------------------------------------------------

    def store_skill(
        self,
        skill_name: str,
        code: str,
        source: str,
        tags: list[str] | None = None,
    ) -> str:
        metadata = {
            "name": skill_name,
            "source": source,
            "tags": tags or [],
            "timestamp": time.time(),
            "language": _detect_language(code),
        }
        text = f"Skill: {skill_name}\nSource: {source}\nTags: {', '.join(tags or [])}\n```\n{code}\n```"
        return self.store("skills", text, metadata, doc_id=f"skill:{skill_name}")

    def find_similar_skills(self, query: str, top_k: int = 3) -> list[dict]:
        return self.search("skills", query, top_k)

    def store_conversation(
        self,
        user_input: str,
        agent_response: str,
        context: dict | None = None,
    ) -> str:
        metadata = {
            "user_input": user_input,
            "agent_response": agent_response,
            "timestamp": time.time(),
            **(context or {}),
        }
        text = f"User: {user_input}\nAgent: {agent_response}"
        return self.store("conversations", text, metadata)

    def get_conversation_history(self, limit: int = 10) -> list[dict]:
        all_convs = self.search("conversations", "conversation", top_k=9999)
        all_convs.sort(key=lambda x: x.get("metadata", {}).get("timestamp", 0), reverse=True)
        return all_convs[:limit]

    def store_github_repo(
        self,
        repo_url: str,
        code_summary: str,
        capabilities: list[str],
    ) -> str:
        metadata = {
            "repo_url": repo_url,
            "capabilities": capabilities,
            "timestamp": time.time(),
        }
        text = f"Repo: {repo_url}\nSummary: {code_summary}\nCapabilities: {', '.join(capabilities)}"
        doc_id = hashlib.md5(repo_url.encode()).hexdigest()
        return self.store("github_repos", text, metadata, doc_id=doc_id)


# ---------------------------------------------------------------------------
# MockMemory – pure-Python fallback
# ---------------------------------------------------------------------------
class MockMemory(BaseVectorMemory):
    """
    In-memory fallback with simple string-matching search.
    Persists to JSON on disk.
    """

    def __init__(self, db_path: str = "~/.jarvis/vector_db") -> None:
        self.db_path = Path(db_path).expanduser()
        self.db_path.mkdir(parents=True, exist_ok=True)
        self._file = self.db_path / "mock_memory.json"
        self._data: dict[str, dict[str, dict]] = {}
        self._ensure_collections()
        self._load()

    def _ensure_collections(self) -> None:
        for name in ("skills", "conversations", "github_repos", "errors"):
            if name not in self._data:
                self._data[name] = {}

    def _load(self) -> None:
        if self._file.exists():
            try:
                raw = json.loads(self._file.read_text(encoding="utf-8"))
                self._data = {k: v for k, v in raw.items()}
                self._ensure_collections()
            except Exception:
                self._data = {}
                self._ensure_collections()

    def _save(self) -> None:
        self._file.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")

    # -- Core API -----------------------------------------------------------

    def store(
        self,
        collection: str,
        text: str,
        metadata: dict | None = None,
        doc_id: str | None = None,
    ) -> str:
        if collection not in self._data:
            self._data[collection] = {}
        if doc_id is None:
            doc_id = f"doc_{hashlib.sha256(text.encode()).hexdigest()[:16]}"
        self._data[collection][doc_id] = {
            "id": doc_id,
            "text": text,
            "metadata": metadata or {},
        }
        self._save()
        return doc_id

    def search(self, collection: str, query: str, top_k: int = 5) -> list[dict]:
        if collection not in self._data:
            return []
        query_lower = query.lower()
        scored: list[tuple[float, dict]] = []
        for doc in self._data[collection].values():
            text = doc["text"].lower()
            score = 0.0
            # simple TF-ish score
            for word in query_lower.split():
                if word in text:
                    score += 1.0
            # bonus for exact substring
            if query_lower in text:
                score += 5.0
            scored.append((score, {
                "id": doc["id"],
                "text": doc["text"],
                "metadata": doc.get("metadata", {}),
                "distance": -score,  # negative score so "lower distance = better"
            }))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in scored[:top_k]]

    def get(self, collection: str, doc_id: str) -> dict | None:
        return self._data.get(collection, {}).get(doc_id)

    def delete(self, collection: str, doc_id: str) -> bool:
        if collection in self._data and doc_id in self._data[collection]:
            del self._data[collection][doc_id]
            self._save()
            return True
        return False

    def list_collections(self) -> list[str]:
        return list(self._data.keys())

    def stats(self) -> dict[str, Any]:
        total = sum(len(v) for v in self._data.values())
        size_bytes = self._file.stat().st_size if self._file.exists() else 0
        return {
            "backend": "MockMemory",
            "total_documents": total,
            "collections": len(self._data),
            "collection_names": list(self._data.keys()),
            "storage_size_bytes": size_bytes,
        }


# ---------------------------------------------------------------------------
# LocalVectorMemory – ChromaDB primary, FAISS fallback
# ---------------------------------------------------------------------------
class LocalVectorMemory(BaseVectorMemory):
    """
    Local vector memory: stores capabilities, conversations, learned skills.
    Uses ChromaDB (persistent) with FAISS fallback.
    Zero cloud dependency.
    """

    def __init__(
        self,
        db_path: str = "~/.jarvis/vector_db",
        embedding_model: str = "all-MiniLM-L6-v2",
    ) -> None:
        self.db_path = Path(db_path).expanduser()
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.embedding_model_name = embedding_model
        self._embedding_fn: Any = None
        self._client: Any = None
        self._backend: str = "unknown"

        self._init_embedding_function()
        self._init_chromadb()
        if self._backend == "chromadb":
            return
        self._init_faiss()
        if self._backend == "faiss":
            return
        # Should not reach here when called through get_memory(), but be safe.
        self._backend = "mock"

    # -- initialisation helpers ---------------------------------------------

    def _init_embedding_function(self) -> None:
        if _probe_sentence_transformers():
            from sentence_transformers import SentenceTransformer
            self._embedding_fn = SentenceTransformer(self.embedding_model_name)
        else:
            self._embedding_fn = None

    def _embed(self, text: str) -> list[float]:
        if self._embedding_fn is not None:
            import numpy as np
            vec = self._embedding_fn.encode(text, convert_to_numpy=True)
            return vec.astype(np.float32).tolist()
        # ultra-light deterministic fallback (not semantic, but stable)
        import numpy as np
        h = hashlib.sha256(text.encode()).digest()
        seed = int.from_bytes(h[:4], "big")
        rng = np.random.RandomState(seed)
        return rng.randn(384).astype(np.float32).tolist()

    def _init_chromadb(self) -> None:
        if not _probe_chromadb():
            return
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=str(self.db_path / "chromadb"))
            self._backend = "chromadb"
            self._ensure_chroma_collections()
        except Exception:
            self._client = None
            self._backend = "unknown"

    def _ensure_chroma_collections(self) -> None:
        for name in ("skills", "conversations", "github_repos", "errors"):
            try:
                self._client.get_or_create_collection(name)
            except Exception:
                pass

    def _init_faiss(self) -> None:
        if not _probe_faiss():
            return
        try:
            import faiss
            self._faiss_path = self.db_path / "faiss"
            self._faiss_path.mkdir(parents=True, exist_ok=True)
            self._faiss_indices: dict[str, Any] = {}
            self._faiss_docs: dict[str, dict[str, dict]] = {}
            self._faiss_dim: int = 384
            self._backend = "faiss"
            self._load_faiss_collections()
        except Exception:
            self._backend = "unknown"

    def _load_faiss_collections(self) -> None:
        import numpy as np
        import faiss
        for name in ("skills", "conversations", "github_repos", "errors"):
            idx_file = self._faiss_path / f"{name}.faiss"
            meta_file = self._faiss_path / f"{name}.json"
            if idx_file.exists() and meta_file.exists():
                idx = faiss.read_index(str(idx_file))
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            else:
                idx = faiss.IndexFlatIP(self._faiss_dim)
                meta = {}
            self._faiss_indices[name] = idx
            self._faiss_docs[name] = meta

    def _save_faiss_collection(self, name: str) -> None:
        import faiss
        faiss.write_index(self._faiss_indices[name], str(self._faiss_path / f"{name}.faiss"))
        (self._faiss_path / f"{name}.json").write_text(
            json.dumps(self._faiss_docs[name], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # -- helper: _collection(name) resolves backend-specific accessor --------

    def _collection(self, name: str):
        if self._backend == "chromadb":
            return self._client.get_or_create_collection(name)
        return name  # for faiss / mock we handle directly

    # -- Core API -----------------------------------------------------------

    def store(
        self,
        collection: str,
        text: str,
        metadata: dict | None = None,
        doc_id: str | None = None,
    ) -> str:
        metadata = metadata or {}
        if doc_id is None:
            doc_id = f"doc_{hashlib.sha256(text.encode()).hexdigest()[:16]}"

        if self._backend == "chromadb":
            col = self._collection(collection)
            col.add(
                documents=[text],
                metadatas=[metadata],
                ids=[doc_id],
            )
            return doc_id

        if self._backend == "faiss":
            import numpy as np
            vec = np.array([self._embed(text)], dtype=np.float32)
            idx = self._faiss_indices.get(collection)
            if idx is None:
                import faiss
                idx = faiss.IndexFlatIP(self._faiss_dim)
                self._faiss_indices[collection] = idx
                self._faiss_docs[collection] = {}
            idx.add(vec)
            self._faiss_docs[collection][doc_id] = {
                "id": doc_id,
                "text": text,
                "metadata": metadata,
            }
            self._save_faiss_collection(collection)
            return doc_id

        raise RuntimeError("LocalVectorMemory has no active backend")

    def search(self, collection: str, query: str, top_k: int = 5) -> list[dict]:
        if self._backend == "chromadb":
            col = self._collection(collection)
            results = col.query(query_texts=[query], n_results=top_k)
            out: list[dict] = []
            ids = results.get("ids", [[]])[0]
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            dists = results.get("distances", [[]])[0]
            for i in range(len(ids)):
                out.append({
                    "id": ids[i],
                    "text": docs[i],
                    "metadata": metas[i] or {},
                    "distance": dists[i] if dists else 0.0,
                })
            return out

        if self._backend == "faiss":
            import numpy as np
            idx = self._faiss_indices.get(collection)
            if idx is None or idx.ntotal == 0:
                return []
            vec = np.array([self._embed(query)], dtype=np.float32)
            distances, indices = idx.search(vec, min(top_k, idx.ntotal))
            docs = self._faiss_docs.get(collection, {})
            out = []
            for dist, i in zip(distances[0], indices[0]):
                # FAISS returns indices; map back to doc_id via insertion order
                doc_id = list(docs.keys())[i]
                doc = docs[doc_id]
                out.append({
                    "id": doc["id"],
                    "text": doc["text"],
                    "metadata": doc.get("metadata", {}),
                    "distance": float(dist),
                })
            return out

        return []

    def get(self, collection: str, doc_id: str) -> dict | None:
        if self._backend == "chromadb":
            col = self._collection(collection)
            try:
                res = col.get(ids=[doc_id])
                if res and res.get("ids") and res["ids"]:
                    return {
                        "id": res["ids"][0],
                        "text": res["documents"][0],
                        "metadata": res["metadatas"][0] or {},
                    }
            except Exception:
                pass
            return None

        if self._backend == "faiss":
            return self._faiss_docs.get(collection, {}).get(doc_id)

        return None

    def delete(self, collection: str, doc_id: str) -> bool:
        if self._backend == "chromadb":
            col = self._collection(collection)
            try:
                col.delete(ids=[doc_id])
                return True
            except Exception:
                return False

        if self._backend == "faiss":
            # FAISS flat indices don't support removal by ID cleanly without
            # reconstruction. Rebuild the index minus the deleted vector.
            docs = self._faiss_docs.get(collection, {})
            if doc_id not in docs:
                return False
            del docs[doc_id]
            import numpy as np
            import faiss
            new_idx = faiss.IndexFlatIP(self._faiss_dim)
            for remaining_doc in docs.values():
                vec = np.array([self._embed(remaining_doc["text"])], dtype=np.float32)
                new_idx.add(vec)
            self._faiss_indices[collection] = new_idx
            self._save_faiss_collection(collection)
            return True

        return False

    def list_collections(self) -> list[str]:
        if self._backend == "chromadb":
            try:
                return [c.name for c in self._client.list_collections()]
            except Exception:
                return []
        if self._backend == "faiss":
            return list(self._faiss_indices.keys())
        return []

    def stats(self) -> dict[str, Any]:
        total = 0
        collection_names = self.list_collections()
        for name in collection_names:
            if self._backend == "chromadb":
                col = self._collection(name)
                try:
                    total += col.count()
                except Exception:
                    pass
            elif self._backend == "faiss":
                idx = self._faiss_indices.get(name)
                if idx:
                    total += idx.ntotal

        # storage size
        size_bytes = 0
        if self.db_path.exists():
            for p in self.db_path.rglob("*"):
                if p.is_file():
                    size_bytes += p.stat().st_size

        return {
            "backend": self._backend,
            "total_documents": total,
            "collections": len(collection_names),
            "collection_names": collection_names,
            "embedding_model": self.embedding_model_name,
            "storage_size_bytes": size_bytes,
            "db_path": str(self.db_path),
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def get_memory(
    db_path: str = "~/.jarvis/vector_db",
    embedding_model: str = "all-MiniLM-L6-v2",
) -> BaseVectorMemory:
    """
    Return the best available memory backend.
    Order: ChromaDB → FAISS → MockMemory
    """
    # 1. Try ChromaDB (needs both chromadb + sentence-transformers for good UX)
    if _probe_chromadb():
        try:
            mem = LocalVectorMemory(db_path=db_path, embedding_model=embedding_model)
            if mem._backend == "chromadb":
                return mem
        except Exception:
            pass

    # 2. Try FAISS
    if _probe_faiss():
        try:
            mem = LocalVectorMemory(db_path=db_path, embedding_model=embedding_model)
            if mem._backend == "faiss":
                return mem
        except Exception:
            pass

    # 3. MockMemory – always works
    return MockMemory(db_path=db_path)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def _detect_language(code: str) -> str:
    """Naive language detection from code block."""
    if "def " in code or "import " in code or "class " in code:
        return "python"
    if "function " in code or "const " in code or "let " in code:
        return "javascript"
    if "package main" in code or "func main" in code:
        return "go"
    if "#include" in code:
        return "c/c++"
    if "<?php" in code:
        return "php"
    return "unknown"


# ---------------------------------------------------------------------------
# Self-test (run as `python local_memory.py`)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mem = get_memory()
    print(f"Backend : {mem.stats()['backend']}")
    print(f"Collections : {mem.list_collections()}")

    # store / search demo
    doc_id = mem.store("skills", "Python function to list files recursively")
    print(f"Stored doc_id: {doc_id}")

    results = mem.search("skills", "recursive file listing")
    print(f"Search results: {len(results)}")

    # specialised methods
    mem.store_skill("file_lister", "def list_files(): ...", "user_request", ["filesystem"])
    skills = mem.find_similar_skills("file listing")
    print(f"Similar skills: {len(skills)}")

    mem.store_conversation("Hello", "Hi there!")
    hist = mem.get_conversation_history()
    print(f"Conversation history: {len(hist)}")

    print("\nStats:", mem.stats())
    print("OK")
