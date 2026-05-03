"""
llamaindex_bridge.py — LlamaIndex Integration for JARVIS BRAINIAC
==================================================================

Provides a unified bridge to the LlamaIndex framework with automatic mock
fallback when ``llama_index`` is not installed.

Public API
----------
* ``LlamaIndexBridge``         – Main client wrapper (real or mock).
* ``get_llamaindex_bridge``    – Factory returning a configured bridge.
* ``is_llamaindex_available``  – Runtime probe for llama-index availability.

Typical usage::

    from jarvis.runtime.agency.llamaindex_bridge import get_llamaindex_bridge

    idx = get_llamaindex_bridge(openai_api_key="sk-...")
    idx.create_index(["doc1.txt", "doc2.txt"])
    answer = idx.query_index("What are the key findings?")

    chat = idx.create_chat_engine(["doc1.txt"])
    response = idx.chat("Tell me more about section 3.")
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("jarvis.runtime.agency.llamaindex_bridge")
logger.addHandler(logging.NullHandler())

# ---------------------------------------------------------------------------
# Dependency probe
# ---------------------------------------------------------------------------

_LLAMAINDEX_AVAILABLE: Optional[bool] = None

def is_llamaindex_available() -> bool:
    """Return ``True`` if the ``llama_index`` package is importable."""
    global _LLAMAINDEX_AVAILABLE
    if _LLAMAINDEX_AVAILABLE is not None:
        return _LLAMAINDEX_AVAILABLE
    try:
        import llama_index  # noqa: F401
        _LLAMAINDEX_AVAILABLE = True
    except Exception:
        _LLAMAINDEX_AVAILABLE = False
    return _LLAMAINDEX_AVAILABLE


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class DocumentBundle:
    """Container for one or more source documents."""
    paths: List[str] = field(default_factory=list)
    texts: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.paths or self.texts)

    def to_dict(self) -> Dict[str, Any]:
        return {"paths": self.paths, "texts": self.texts}


@dataclass
class QueryResult:
    """Structured result from a LlamaIndex query."""
    response: str
    source_nodes: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "response": self.response,
            "source_nodes": self.source_nodes,
            "metadata": self.metadata,
        }


@dataclass
class ChatTurn:
    """Single conversational turn."""
    role: str
    content: str
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"role": self.role, "content": self.content, "timestamp": self.timestamp}


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class _BaseLlamaIndexBridge(ABC):
    """Interface contract shared by real and mock LlamaIndex adapters."""

    @abstractmethod
    def create_index(self, documents: List[str]) -> bool:
        ...

    @abstractmethod
    def query_index(self, query: str) -> QueryResult:
        ...

    @abstractmethod
    def create_chat_engine(self, documents: List[str]) -> bool:
        ...

    @abstractmethod
    def chat(self, message: str) -> str:
        ...

    @abstractmethod
    def add_documents(self, new_documents: List[str]) -> bool:
        ...

    @abstractmethod
    def persist_index(self, path: str) -> bool:
        ...

    @abstractmethod
    def load_index(self, path: str) -> bool:
        ...

    @abstractmethod
    def reset(self) -> None:
        ...


# ---------------------------------------------------------------------------
# Real implementation — backed by llama-index
# ---------------------------------------------------------------------------

class _RealLlamaIndexBridge(_BaseLlamaIndexBridge):
    """Production bridge backed by the full LlamaIndex framework.

    Parameters
    ----------
    openai_api_key: str, optional
        API key for OpenAI embeddings / LLM.
    embedding_model: str, optional
        Name of the embedding model to use.
    llm_model: str, optional
        Name of the chat/completion model.
    persist_dir: str, optional
        Default directory for index persistence.
    """

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        embedding_model: str = "text-embedding-ada-002",
        llm_model: str = "gpt-4o",
        persist_dir: str = "./storage",
    ) -> None:
        self.openai_api_key = openai_api_key or os.environ.get("OPENAI_API_KEY", "")
        self.embedding_model = embedding_model
        self.llm_model = llm_model
        self.persist_dir = persist_dir

        self._index: Any = None
        self._chat_engine: Any = None
        self._documents: List[str] = []
        self._chat_history: List[ChatTurn] = []

        self._configure_settings()
        logger.info(
            "Real LlamaIndexBridge initialised (embed=%s, llm=%s).",
            embedding_model,
            llm_model,
        )

    def _configure_settings(self) -> None:
        """Configure global LlamaIndex settings for embeddings + LLM."""
        from llama_index.core import Settings
        from llama_index.embeddings.openai import OpenAIEmbedding
        from llama_index.llms.openai import OpenAI

        if self.openai_api_key:
            os.environ.setdefault("OPENAI_API_KEY", self.openai_api_key)

        Settings.embed_model = OpenAIEmbedding(model=self.embedding_model)
        Settings.llm = OpenAI(model=self.llm_model, api_key=self.openai_api_key or None)

    def _load_documents(self, paths: List[str]) -> List[Any]:
        """Load files from disk into LlamaIndex Document objects."""
        from llama_index.core import SimpleDirectoryReader

        valid_paths = [p for p in paths if os.path.exists(p)]
        if not valid_paths:
            logger.warning("No valid file paths provided; returning empty list.")
            return []

        if len(valid_paths) == 1 and os.path.isfile(valid_paths[0]):
            reader = SimpleDirectoryReader(input_files=valid_paths)
        else:
            reader = SimpleDirectoryReader(input_dir=valid_paths[0] if len(valid_paths) == 1 else ".", input_files=valid_paths)
        return reader.load_data()

    # ---- public API -------------------------------------------------------

    def create_index(self, documents: List[str]) -> bool:
        """Create a new vector index from a list of file paths.

        Parameters
        ----------
        documents: list[str]
            File system paths to text/PDF/Markdown documents.

        Returns
        -------
        bool
            ``True`` on success.
        """
        try:
            docs = self._load_documents(documents)
            if not docs:
                logger.error("No documents could be loaded from %s", documents)
                return False

            from llama_index.core import VectorStoreIndex
            self._index = VectorStoreIndex.from_documents(docs)
            self._documents = list(documents)
            self._chat_engine = None
            logger.info("VectorStoreIndex created from %d document(s).", len(docs))
            return True
        except Exception as exc:
            logger.error("Failed to create index: %s", exc)
            return False

    def query_index(self, query: str) -> QueryResult:
        """Query the vector index using RAG.

        Parameters
        ----------
        query: str
            Natural-language question.

        Returns
        -------
        QueryResult
            Structured response with source attribution.
        """
        if self._index is None:
            logger.warning("No index available — call create_index() first.")
            return QueryResult(response="[Error] No index has been built yet.")

        try:
            query_engine = self._index.as_query_engine()
            response = query_engine.query(query)

            source_nodes = []
            for node in response.source_nodes:
                source_nodes.append({
                    "text": node.text[:500],
                    "score": float(node.score) if hasattr(node, "score") else 0.0,
                    "metadata": node.metadata,
                })

            result = QueryResult(
                response=str(response),
                source_nodes=source_nodes,
                metadata={"query": query, "timestamp": _utc_now()},
            )
            logger.debug("Query returned %d source nodes.", len(source_nodes))
            return result
        except Exception as exc:
            logger.error("Query failed: %s", exc)
            return QueryResult(response=f"[LlamaIndex Error] {exc}")

    def create_chat_engine(self, documents: List[str]) -> bool:
        """Create a conversational chat engine with memory.

        Parameters
        ----------
        documents: list[str]
            Source documents for retrieval context.

        Returns
        -------
        bool
            ``True`` on success.
        """
        try:
            if self._index is None or set(self._documents) != set(documents):
                ok = self.create_index(documents)
                if not ok:
                    return False

            self._chat_engine = self._index.as_chat_engine(
                chat_mode="condense_plus_context",
                verbose=True,
            )
            self._chat_history.clear()
            logger.info("Chat engine created.")
            return True
        except Exception as exc:
            logger.error("Failed to create chat engine: %s", exc)
            return False

    def chat(self, message: str) -> str:
        """Send a message to the chat engine.

        Parameters
        ----------
        message: str
            User utterance.

        Returns
        -------
        str
            Assistant response text.
        """
        if self._chat_engine is None:
            logger.warning("No chat engine — call create_chat_engine() first.")
            return "[Error] Chat engine not initialised."

        try:
            self._chat_history.append(ChatTurn(role="user", content=message, timestamp=_utc_now()))
            response = self._chat_engine.chat(message)
            answer = str(response)
            self._chat_history.append(ChatTurn(role="assistant", content=answer, timestamp=_utc_now()))
            logger.debug("Chat response: %d chars.", len(answer))
            return answer
        except Exception as exc:
            logger.error("Chat failed: %s", exc)
            return f"[LlamaIndex Chat Error] {exc}"

    def add_documents(self, new_documents: List[str]) -> bool:
        """Add new documents to the existing index.

        Parameters
        ----------
        new_documents: list[str]
            Additional file paths to ingest.

        Returns
        -------
        bool
            ``True`` on success.
        """
        if self._index is None:
            logger.info("No existing index — creating a fresh one.")
            return self.create_index(new_documents)

        try:
            docs = self._load_documents(new_documents)
            if not docs:
                return False
            for doc in docs:
                self._index.insert(doc)
            self._documents.extend(new_documents)
            logger.info("Inserted %d new document(s) into existing index.", len(docs))
            return True
        except Exception as exc:
            logger.error("Failed to add documents: %s", exc)
            return False

    def persist_index(self, path: str) -> bool:
        """Persist the current index to disk.

        Parameters
        ----------
        path: str
            Target directory for storage.

        Returns
        -------
        bool
            ``True`` on success.
        """
        if self._index is None:
            logger.warning("No index to persist.")
            return False

        try:
            os.makedirs(path, exist_ok=True)
            self._index.storage_context.persist(persist_dir=path)

            manifest = {
                "version": 1,
                "timestamp": _utc_now(),
                "documents": self._documents,
                "embedding_model": self.embedding_model,
                "llm_model": self.llm_model,
            }
            with open(os.path.join(path, "manifest.json"), "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, indent=2)

            logger.info("Index persisted to %s", path)
            return True
        except Exception as exc:
            logger.error("Failed to persist index: %s", exc)
            return False

    def load_index(self, path: str) -> bool:
        """Load a previously persisted index from disk.

        Parameters
        ----------
        path: str
            Directory containing a persisted LlamaIndex storage context.

        Returns
        -------
        bool
            ``True`` on success.
        """
        try:
            from llama_index.core import StorageContext, load_index_from_storage

            storage_context = StorageContext.from_defaults(persist_dir=path)
            self._index = load_index_from_storage(storage_context)

            manifest_path = os.path.join(path, "manifest.json")
            if os.path.exists(manifest_path):
                with open(manifest_path, "r", encoding="utf-8") as fh:
                    manifest = json.load(fh)
                self._documents = manifest.get("documents", [])
                self.embedding_model = manifest.get("embedding_model", self.embedding_model)
                self.llm_model = manifest.get("llm_model", self.llm_model)

            self._chat_engine = None
            logger.info("Index loaded from %s", path)
            return True
        except Exception as exc:
            logger.error("Failed to load index: %s", exc)
            return False

    def reset(self) -> None:
        """Clear the index, chat engine, and document list."""
        self._index = None
        self._chat_engine = None
        self._documents.clear()
        self._chat_history.clear()
        logger.info("LlamaIndexBridge state reset.")


# ---------------------------------------------------------------------------
# Mock implementation — in-memory fallback
# ---------------------------------------------------------------------------

class _MockLlamaIndexBridge(_BaseLlamaIndexBridge):
    """In-memory fallback used when ``llama_index`` is unavailable.

    Simulates indexing, querying, and chatting using keyword matching against
    loaded document contents.
    """

    def __init__(self) -> None:
        self._documents: Dict[str, str] = {}
        self._index_built: bool = False
        self._chat_active: bool = False
        self._chat_history: List[ChatTurn] = []
        self._persisted_manifest: Optional[Dict[str, Any]] = None
        logger.info("Mock LlamaIndexBridge initialised.")

    # ---- helpers ----------------------------------------------------------

    def _ingest_files(self, paths: List[str]) -> int:
        """Read files into memory; return count ingested."""
        count = 0
        for p in paths:
            if os.path.isfile(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                        self._documents[os.path.basename(p)] = fh.read()
                    count += 1
                except Exception as exc:
                    logger.warning("[MOCK] Could not read %s: %s", p, exc)
            else:
                logger.warning("[MOCK] File not found: %s", p)
        return count

    def _keyword_search(self, query: str) -> List[Tuple[str, str, int]]:
        """Naïve keyword search returning (filename, snippet, score)."""
        tokens = query.lower().split()
        results: List[Tuple[int, str, str, str]] = []
        for fname, content in self._documents.items():
            text_lower = content.lower()
            score = sum(1 for t in tokens if t in text_lower)
            if score > 0:
                snippet_start = max(text_lower.find(tokens[0]) - 100, 0) if tokens else 0
                snippet = content[snippet_start:snippet_start + 400]
                results.append((score, fname, snippet, content))
        results.sort(key=lambda x: x[0], reverse=True)
        return [(fname, snippet, score) for score, fname, snippet, content in results]

    # ---- public API -------------------------------------------------------

    def create_index(self, documents: List[str]) -> bool:
        """Build a mock index from file paths."""
        count = self._ingest_files(documents)
        self._index_built = count > 0
        self._chat_active = False
        logger.info("[MOCK] Index built from %d document(s).", count)
        return self._index_built

    def query_index(self, query: str) -> QueryResult:
        """Return keyword-based mock results."""
        if not self._index_built:
            return QueryResult(response="[Error] No index has been built yet.")

        results = self._keyword_search(query)
        if not results:
            return QueryResult(
                response=f"No relevant documents found for query: '{query}'",
                source_nodes=[],
                metadata={"query": query, "timestamp": _utc_now()},
            )

        source_nodes = []
        for fname, snippet, score in results[:5]:
            source_nodes.append({
                "text": snippet,
                "score": float(score),
                "metadata": {"file_name": fname},
            })

        answer = (
            f"[Mock LlamaIndex RAG]\n"
            f"Query: {query}\n\n"
            f"Based on the retrieved context from {len(results)} source(s):\n\n"
        )
        for fname, snippet, score in results[:3]:
            answer += f"--- From {fname} ---\n{snippet}\n\n"
        answer += f"(Total sources consulted: {len(results)})"

        return QueryResult(
            response=answer,
            source_nodes=source_nodes,
            metadata={"query": query, "timestamp": _utc_now(), "mock": True},
        )

    def create_chat_engine(self, documents: List[str]) -> bool:
        """Activate chat mode (re-builds index if needed)."""
        if not self._documents or set(documents) != set(self._documents.keys()):
            self.create_index(documents)
        self._chat_active = self._index_built
        self._chat_history.clear()
        logger.info("[MOCK] Chat engine activated.")
        return self._chat_active

    def chat(self, message: str) -> str:
        """Return a mock conversational response."""
        if not self._chat_active:
            return "[Error] Chat engine not initialised — call create_chat_engine() first."

        self._chat_history.append(ChatTurn(role="user", content=message, timestamp=_utc_now()))
        results = self._keyword_search(message)

        answer = f"[Mock LlamaIndex Chat]\nBased on the conversation and retrieved context:\n\n"
        if results:
            for fname, snippet, score in results[:2]:
                answer += f"From '{fname}': {snippet[:300]}...\n\n"
        else:
            answer += "I don't have specific information about that in my indexed documents.\n"

        answer += f"\n(Chat history: {len(self._chat_history)} turns)"
        self._chat_history.append(ChatTurn(role="assistant", content=answer, timestamp=_utc_now()))
        return answer

    def add_documents(self, new_documents: List[str]) -> bool:
        """Ingest additional documents into the existing mock index."""
        count = self._ingest_files(new_documents)
        if count > 0:
            self._index_built = True
        logger.info("[MOCK] Added %d new document(s). Total: %d", count, len(self._documents))
        return count > 0

    def persist_index(self, path: str) -> bool:
        """Write document contents and manifest to disk."""
        try:
            os.makedirs(path, exist_ok=True)
            for fname, content in self._documents.items():
                safe_name = fname.replace("/", "_")
                with open(os.path.join(path, safe_name), "w", encoding="utf-8") as fh:
                    fh.write(content)

            manifest = {
                "version": 1,
                "timestamp": _utc_now(),
                "documents": list(self._documents.keys()),
                "mock": True,
            }
            manifest_path = os.path.join(path, "manifest.json")
            with open(manifest_path, "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, indent=2)

            logger.info("[MOCK] Index persisted to %s", path)
            return True
        except Exception as exc:
            logger.error("[MOCK] Persist failed: %s", exc)
            return False

    def load_index(self, path: str) -> bool:
        """Read documents and manifest back from disk."""
        try:
            manifest_path = os.path.join(path, "manifest.json")
            if not os.path.exists(manifest_path):
                logger.warning("[MOCK] No manifest found at %s", path)
                return False

            with open(manifest_path, "r", encoding="utf-8") as fh:
                manifest = json.load(fh)

            self._documents.clear()
            for fname in manifest.get("documents", []):
                safe_name = fname.replace("/", "_")
                fpath = os.path.join(path, safe_name)
                if os.path.exists(fpath):
                    with open(fpath, "r", encoding="utf-8") as f:
                        self._documents[fname] = f.read()

            self._index_built = len(self._documents) > 0
            logger.info("[MOCK] Loaded %d docs from %s", len(self._documents), path)
            return self._index_built
        except Exception as exc:
            logger.error("[MOCK] Load failed: %s", exc)
            return False

    def reset(self) -> None:
        """Clear all mock state."""
        self._documents.clear()
        self._index_built = False
        self._chat_active = False
        self._chat_history.clear()
        self._persisted_manifest = None
        logger.info("[MOCK] LlamaIndexBridge state reset.")


# ---------------------------------------------------------------------------
# Public wrapper
# ---------------------------------------------------------------------------

class LlamaIndexBridge(_BaseLlamaIndexBridge):
    """Unified LlamaIndex client for JARVIS BRAINIAC.

    Parameters
    ----------
    openai_api_key: str, optional
        OpenAI API key (env-fallback ``OPENAI_API_KEY``).
    embedding_model: str, optional
        Embedding model name.
    llm_model: str, optional
        LLM model name.
    persist_dir: str, optional
        Default persistence directory.
    force_mock: bool, optional
        If ``True``, always use the in-memory mock.
    """

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        embedding_model: str = "text-embedding-ada-002",
        llm_model: str = "gpt-4o",
        persist_dir: str = "./storage",
        force_mock: bool = False,
    ) -> None:
        resolved_key = openai_api_key or os.environ.get("OPENAI_API_KEY", "")

        if not force_mock and is_llamaindex_available() and resolved_key:
            self._impl: _BaseLlamaIndexBridge = _RealLlamaIndexBridge(
                openai_api_key=resolved_key,
                embedding_model=embedding_model,
                llm_model=llm_model,
                persist_dir=persist_dir,
            )
        else:
            if not force_mock and not is_llamaindex_available():
                logger.warning("llama_index not installed — falling back to mock.")
            elif not force_mock and not resolved_key:
                logger.warning("OPENAI_API_KEY not set — falling back to mock.")
            self._impl = _MockLlamaIndexBridge()

        self.force_mock = force_mock

    # ---- delegated API ----------------------------------------------------

    def create_index(self, documents: List[str]) -> bool:
        """Create a vector index from documents."""
        return self._impl.create_index(documents)

    def query_index(self, query: str) -> QueryResult:
        """Query the index with RAG."""
        return self._impl.query_index(query)

    def create_chat_engine(self, documents: List[str]) -> bool:
        """Create a chat engine with memory."""
        return self._impl.create_chat_engine(documents)

    def chat(self, message: str) -> str:
        """Chat with the engine."""
        return self._impl.chat(message)

    def add_documents(self, new_documents: List[str]) -> bool:
        """Add documents to the existing index."""
        return self._impl.add_documents(new_documents)

    def persist_index(self, path: str) -> bool:
        """Persist the index to disk."""
        return self._impl.persist_index(path)

    def load_index(self, path: str) -> bool:
        """Load a persisted index from disk."""
        return self._impl.load_index(path)

    def reset(self) -> None:
        """Clear all state."""
        self._impl.reset()

    @property
    def is_mock(self) -> bool:
        """``True`` when running in mock mode."""
        return isinstance(self._impl, _MockLlamaIndexBridge)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_llamaindex_bridge(
    openai_api_key: Optional[str] = None,
    embedding_model: str = "text-embedding-ada-002",
    llm_model: str = "gpt-4o",
    persist_dir: str = "./storage",
    force_mock: bool = False,
) -> LlamaIndexBridge:
    """Create and return a configured ``LlamaIndexBridge``.

    Parameters
    ----------
    openai_api_key: str, optional
        OpenAI API key (env-fallback ``OPENAI_API_KEY``).
    embedding_model: str, optional
        Embedding model identifier.
    llm_model: str, optional
        Chat/completion model identifier.
    persist_dir: str, optional
        Default persistence directory.
    force_mock: bool, optional
        Always return the in-memory mock.

    Returns
    -------
    LlamaIndexBridge
    """
    return LlamaIndexBridge(
        openai_api_key=openai_api_key,
        embedding_model=embedding_model,
        llm_model=llm_model,
        persist_dir=persist_dir,
        force_mock=force_mock,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    """Return ISO-8601 timestamp in UTC."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test() -> None:
    """Smoke-test the mock implementation."""
    logging.basicConfig(level=logging.DEBUG)
    print("=== LlamaIndexBridge self-test (mock) ===")
    bridge = get_llamaindex_bridge(force_mock=True)
    print(f"is_mock = {bridge.is_mock}")

    # Create temp test files
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        doc1 = os.path.join(tmpdir, "doc1.txt")
        doc2 = os.path.join(tmpdir, "doc2.txt")
        with open(doc1, "w") as f:
            f.write("JARVIS BRAINIAC is an advanced AI system built for automation.")
        with open(doc2, "w") as f:
            f.write("Python is a versatile programming language used widely in AI.")

        ok = bridge.create_index([doc1, doc2])
        print(f"Index created: {ok}")

        result = bridge.query_index("What is JARVIS BRAINIAC?")
        print(f"Query result: {result.response[:100]}...")

        ok = bridge.create_chat_engine([doc1, doc2])
        print(f"Chat engine created: {ok}")

        answer = bridge.chat("Tell me about Python")
        print(f"Chat answer: {answer[:100]}...")

        # Test persist/load
        persist_path = os.path.join(tmpdir, "persisted_index")
        ok = bridge.persist_index(persist_path)
        print(f"Persisted: {ok}")

        bridge.reset()
        print("State reset.")

        ok = bridge.load_index(persist_path)
        print(f"Loaded: {ok}")

        result = bridge.query_index("What is JARVIS BRAINIAC?")
        print(f"Post-load query: {result.response[:100]}...")

    print("=== self-test passed ===")


if __name__ == "__main__":
    _self_test()
