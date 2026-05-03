"""
ragflow_bridge.py — RAGFlow Integration for JARVIS BRAINIAC
===========================================================

Provides a unified bridge to the RAGFlow platform (https://ragflow.io) with
automatic mock fallback when ``requests`` is unavailable.

Public API
----------
* ``RAGFlowBridge``         – Main client wrapper (real or mock).
* ``get_ragflow_bridge``    – Factory returning a configured bridge.
* ``is_ragflow_available``  – Runtime probe for basic connectivity.

Typical usage::

    from jarvis.runtime.agency.ragflow_bridge import get_ragflow_bridge

    rag = get_ragflow_bridge(api_key="<KEY>", base_url="http://localhost:9380")
    ds = rag.create_dataset("my_docs")
    rag.upload_document(ds["id"], "/path/to/file.pdf")
    rag.parse_documents(ds["id"])
    chat = rag.create_chat("QABot", [ds["id"]])
    answer = rag.ask(chat["id"], "What is the refund policy?")
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("jarvis.runtime.agency.ragflow_bridge")
logger.addHandler(logging.NullHandler())

# ---------------------------------------------------------------------------
# Dependency probe
# ---------------------------------------------------------------------------

_REQUESTS_AVAILABLE: Optional[bool] = None

def is_ragflow_available(base_url: str = "http://localhost:9380") -> bool:
    """Return ``True`` if ``requests`` is importable *and* RAGFlow responds.

    Parameters
    ----------
    base_url: str
        The root URL of the RAGFlow API.
    """
    global _REQUESTS_AVAILABLE
    try:
        import requests
        _REQUESTS_AVAILABLE = True
    except Exception:
        _REQUESTS_AVAILABLE = False
        return False

    try:
        resp = requests.get(f"{base_url}/health", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class DatasetInfo:
    """Represents a RAGFlow dataset / knowledge base."""
    id: str
    name: str
    description: str = ""
    document_count: int = 0
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "document_count": self.document_count,
            "created_at": self.created_at,
        }


@dataclass
class DocumentInfo:
    """Represents an uploaded document inside a dataset."""
    id: str
    name: str
    dataset_id: str
    status: str = "pending"
    chunk_count: int = 0
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "dataset_id": self.dataset_id,
            "status": self.status,
            "chunk_count": self.chunk_count,
            "created_at": self.created_at,
        }


@dataclass
class ChatInfo:
    """Represents a chat assistant."""
    id: str
    name: str
    dataset_ids: List[str] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "dataset_ids": self.dataset_ids,
            "created_at": self.created_at,
        }


@dataclass
class ChatMessage:
    """Single turn in a chat conversation."""
    role: str
    content: str

    def to_dict(self) -> Dict[str, Any]:
        return {"role": self.role, "content": self.content}


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class _BaseRAGFlowBridge:
    """Shared interface for real and mock RAGFlow adapters."""

    def create_dataset(self, name: str, description: str = "") -> Dict[str, Any]:
        raise NotImplementedError

    def upload_document(self, dataset_id: str, file_path: str) -> Dict[str, Any]:
        raise NotImplementedError

    def parse_documents(self, dataset_id: str) -> bool:
        raise NotImplementedError

    def create_chat(self, name: str, dataset_ids: List[str]) -> Dict[str, Any]:
        raise NotImplementedError

    def ask(self, chat_id: str, question: str) -> str:
        raise NotImplementedError

    def list_chats(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def list_datasets(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def list_documents(self, dataset_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Real implementation — HTTP API
# ---------------------------------------------------------------------------

class _RealRAGFlowBridge(_BaseRAGFlowBridge):
    """Production bridge that communicates with RAGFlow over REST."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:9380",
        timeout: int = 30,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        logger.info("Real RAGFlowBridge initialised (base_url=%s).", self.base_url)

    # ---- HTTP helpers ----------------------------------------------------

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        import requests
        url = f"{self.base_url}{path}"
        resp = requests.get(url, headers=self._headers, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json_data: Optional[Dict[str, Any]] = None, files: Optional[Dict[str, Any]] = None) -> Any:
        import requests
        url = f"{self.base_url}{path}"
        if files:
            headers = {k: v for k, v in self._headers.items() if k.lower() != "content-type"}
            resp = requests.post(url, headers=headers, files=files, timeout=self.timeout)
        else:
            resp = requests.post(url, headers=self._headers, json=json_data, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path: str) -> Any:
        import requests
        url = f"{self.base_url}{path}"
        resp = requests.delete(url, headers=self._headers, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # ---- public API -------------------------------------------------------

    def create_dataset(self, name: str, description: str = "") -> Dict[str, Any]:
        """Create a new dataset (knowledge base).

        Parameters
        ----------
        name: str
            Human-readable dataset name.
        description: str, optional
            Longer explanation of the dataset purpose.

        Returns
        -------
        dict
            Serialized ``DatasetInfo`` with at least an ``"id"`` key.
        """
        try:
            payload = {"name": name, "description": description}
            data = self._post("/api/datasets", json_data=payload)
            ds = DatasetInfo(
                id=data.get("data", {}).get("id", ""),
                name=name,
                description=description,
                created_at=_utc_now(),
            )
            logger.info("Created dataset '%s' id=%s", name, ds.id)
            return ds.to_dict()
        except Exception as exc:
            logger.error("Failed to create dataset: %s", exc)
            return {"id": "", "error": str(exc)}

    def upload_document(self, dataset_id: str, file_path: str) -> Dict[str, Any]:
        """Upload a file into a dataset.

        Parameters
        ----------
        dataset_id: str
            Target dataset UUID.
        file_path: str
            Local filesystem path to the document.

        Returns
        -------
        dict
            Serialized ``DocumentInfo``.
        """
        try:
            import requests
            url = f"{self.base_url}/api/datasets/{dataset_id}/documents"
            headers = {k: v for k, v in self._headers.items() if k.lower() != "content-type"}
            with open(file_path, "rb") as fh:
                files = {"file": (os.path.basename(file_path), fh)}
                resp = requests.post(url, headers=headers, files=files, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            doc = DocumentInfo(
                id=data.get("data", {}).get("id", ""),
                name=os.path.basename(file_path),
                dataset_id=dataset_id,
                status="uploaded",
                created_at=_utc_now(),
            )
            logger.info("Uploaded '%s' to dataset %s doc_id=%s", file_path, dataset_id, doc.id)
            return doc.to_dict()
        except Exception as exc:
            logger.error("Failed to upload document: %s", exc)
            return {"id": "", "error": str(exc)}

    def parse_documents(self, dataset_id: str) -> bool:
        """Trigger parsing / chunking for all pending documents in a dataset.

        Parameters
        ----------
        dataset_id: str
            Dataset to parse.

        Returns
        -------
        bool
            ``True`` if the parse job was accepted.
        """
        try:
            self._post(f"/api/datasets/{dataset_id}/documents/parse")
            logger.info("Parse job started for dataset %s", dataset_id)
            return True
        except Exception as exc:
            logger.error("Failed to start parsing: %s", exc)
            return False

    def create_chat(self, name: str, dataset_ids: List[str]) -> Dict[str, Any]:
        """Create a chat assistant linked to one or more datasets.

        Parameters
        ----------
        name: str
            Assistant display name.
        dataset_ids: list[str]
            Datasets the assistant can retrieve from.

        Returns
        -------
        dict
            Serialized ``ChatInfo``.
        """
        try:
            payload = {"name": name, "dataset_ids": dataset_ids}
            data = self._post("/api/chats", json_data=payload)
            chat = ChatInfo(
                id=data.get("data", {}).get("id", ""),
                name=name,
                dataset_ids=dataset_ids,
                created_at=_utc_now(),
            )
            logger.info("Created chat '%s' id=%s", name, chat.id)
            return chat.to_dict()
        except Exception as exc:
            logger.error("Failed to create chat: %s", exc)
            return {"id": "", "error": str(exc)}

    def ask(self, chat_id: str, question: str) -> str:
        """Send a question to a chat assistant and return the answer text.

        Parameters
        ----------
        chat_id: str
            Target assistant UUID.
        question: str
            User query.

        Returns
        -------
        str
            Assistant answer text.
        """
        try:
            payload = {"question": question}
            data = self._post(f"/api/chats/{chat_id}/completions", json_data=payload)
            answer = data.get("data", {}).get("answer", "")
            logger.debug("Chat %s answered with %d chars", chat_id, len(answer))
            return answer
        except Exception as exc:
            logger.error("Chat query failed: %s", exc)
            return f"[RAGFlow Error] {exc}"

    def list_chats(self) -> List[Dict[str, Any]]:
        """Return all chat assistants."""
        try:
            data = self._get("/api/chats")
            chats = data.get("data", [])
            logger.debug("Listed %d chats.", len(chats))
            return chats
        except Exception as exc:
            logger.error("Failed to list chats: %s", exc)
            return []

    def list_datasets(self) -> List[Dict[str, Any]]:
        """Return all datasets."""
        try:
            data = self._get("/api/datasets")
            datasets = data.get("data", [])
            logger.debug("Listed %d datasets.", len(datasets))
            return datasets
        except Exception as exc:
            logger.error("Failed to list datasets: %s", exc)
            return []

    def list_documents(self, dataset_id: str) -> List[Dict[str, Any]]:
        """Return all documents inside a dataset."""
        try:
            data = self._get(f"/api/datasets/{dataset_id}/documents")
            docs = data.get("data", [])
            logger.debug("Listed %d docs in dataset %s.", len(docs), dataset_id)
            return docs
        except Exception as exc:
            logger.error("Failed to list documents: %s", exc)
            return []


# ---------------------------------------------------------------------------
# Mock implementation — in-memory fallback
# ---------------------------------------------------------------------------

class _MockRAGFlowBridge(_BaseRAGFlowBridge):
    """In-memory fallback used when ``requests`` is unavailable or forced."""

    def __init__(self) -> None:
        self._datasets: Dict[str, Dict[str, Any]] = {}
        self._documents: Dict[str, List[Dict[str, Any]]] = {}
        self._chats: Dict[str, Dict[str, Any]] = {}
        logger.info("Mock RAGFlowBridge initialised.")

    # ---- public API -------------------------------------------------------

    def create_dataset(self, name: str, description: str = "") -> Dict[str, Any]:
        """Create a mock dataset."""
        ds_id = str(uuid.uuid4())
        ds = DatasetInfo(
            id=ds_id,
            name=name,
            description=description,
            created_at=_utc_now(),
        )
        self._datasets[ds_id] = ds.to_dict()
        self._documents[ds_id] = []
        logger.info("[MOCK] Created dataset '%s' id=%s", name, ds_id)
        return ds.to_dict()

    def upload_document(self, dataset_id: str, file_path: str) -> Dict[str, Any]:
        """Simulate uploading a document."""
        if dataset_id not in self._datasets:
            return {"id": "", "error": f"Dataset {dataset_id} not found"}
        doc_id = str(uuid.uuid4())
        doc = DocumentInfo(
            id=doc_id,
            name=os.path.basename(file_path),
            dataset_id=dataset_id,
            status="parsed",
            chunk_count=42,
            created_at=_utc_now(),
        )
        self._documents[dataset_id].append(doc.to_dict())
        self._datasets[dataset_id]["document_count"] = len(self._documents[dataset_id])
        logger.info("[MOCK] Uploaded '%s' doc_id=%s", file_path, doc_id)
        return doc.to_dict()

    def parse_documents(self, dataset_id: str) -> bool:
        """No-op for mock — documents are auto-parsed on upload."""
        if dataset_id not in self._datasets:
            return False
        for doc in self._documents.get(dataset_id, []):
            doc["status"] = "parsed"
        logger.info("[MOCK] Parsed all docs in dataset %s", dataset_id)
        return True

    def create_chat(self, name: str, dataset_ids: List[str]) -> Dict[str, Any]:
        """Create a mock chat assistant."""
        chat_id = str(uuid.uuid4())
        chat = ChatInfo(
            id=chat_id,
            name=name,
            dataset_ids=dataset_ids,
            created_at=_utc_now(),
        )
        self._chats[chat_id] = chat.to_dict()
        logger.info("[MOCK] Created chat '%s' id=%s", name, chat_id)
        return chat.to_dict()

    def ask(self, chat_id: str, question: str) -> str:
        """Return a canned answer."""
        if chat_id not in self._chats:
            return "[Mock Error] Chat not found."
        chat = self._chats[chat_id]
        logger.debug("[MOCK] Chat %s asked: %s", chat_id, question)
        return (
            f"[Mock RAGFlow Answer from '{chat['name']}']\n"
            f"Based on the retrieved documents, here is the information about: {question}\n"
            f"- Key point one related to your query.\n"
            f"- Key point two with supporting details.\n"
            f"- Key point three with additional context.\n\n"
            f"Sources: {len(chat['dataset_ids'])} dataset(s) consulted."
        )

    def list_chats(self) -> List[Dict[str, Any]]:
        """Return all mock chats."""
        return list(self._chats.values())

    def list_datasets(self) -> List[Dict[str, Any]]:
        """Return all mock datasets."""
        return list(self._datasets.values())

    def list_documents(self, dataset_id: str) -> List[Dict[str, Any]]:
        """Return documents for a dataset."""
        return list(self._documents.get(dataset_id, []))


# ---------------------------------------------------------------------------
# Public wrapper
# ---------------------------------------------------------------------------

class RAGFlowBridge(_BaseRAGFlowBridge):
    """Unified RAGFlow client for JARVIS BRAINIAC.

    Automatically selects the real HTTP implementation when ``requests`` is
    installed and the API key is provided, otherwise falls back to an in-memory
    mock.

    Parameters
    ----------
    api_key: str, optional
        RAGFlow API key. Falls back to ``RAGFLOW_API_KEY`` env var.
    base_url: str, optional
        Root URL of the RAGFlow API (default ``http://localhost:9380``).
    timeout: int, optional
        HTTP request timeout in seconds.
    force_mock: bool, optional
        If ``True``, always use the mock implementation.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "http://localhost:9380",
        timeout: int = 30,
        force_mock: bool = False,
    ) -> None:
        resolved_key = api_key or os.environ.get("RAGFLOW_API_KEY", "")

        if not force_mock:
            try:
                import requests  # noqa: F401
                has_requests = True
            except Exception:
                has_requests = False
        else:
            has_requests = False

        if not force_mock and has_requests and resolved_key:
            self._impl: _BaseRAGFlowBridge = _RealRAGFlowBridge(
                api_key=resolved_key,
                base_url=base_url,
                timeout=timeout,
            )
        else:
            if force_mock:
                logger.info("RAGFlowBridge forced to mock mode.")
            elif not has_requests:
                logger.warning("requests not installed — falling back to mock RAGFlow.")
            elif not resolved_key:
                logger.warning("RAGFLOW_API_KEY not set — falling back to mock.")
            self._impl = _MockRAGFlowBridge()

    # ---- delegated public API ---------------------------------------------

    def create_dataset(self, name: str, description: str = "") -> Dict[str, Any]:
        """Create a new dataset."""
        return self._impl.create_dataset(name, description=description)

    def upload_document(self, dataset_id: str, file_path: str) -> Dict[str, Any]:
        """Upload a document to a dataset."""
        return self._impl.upload_document(dataset_id, file_path)

    def parse_documents(self, dataset_id: str) -> bool:
        """Trigger document parsing."""
        return self._impl.parse_documents(dataset_id)

    def create_chat(self, name: str, dataset_ids: List[str]) -> Dict[str, Any]:
        """Create a chat assistant."""
        return self._impl.create_chat(name, dataset_ids)

    def ask(self, chat_id: str, question: str) -> str:
        """Ask a chat assistant a question."""
        return self._impl.ask(chat_id, question)

    def list_chats(self) -> List[Dict[str, Any]]:
        """List all chat assistants."""
        return self._impl.list_chats()

    def list_datasets(self) -> List[Dict[str, Any]]:
        """List all datasets."""
        return self._impl.list_datasets()

    def list_documents(self, dataset_id: str) -> List[Dict[str, Any]]:
        """List documents in a dataset."""
        return self._impl.list_documents(dataset_id)

    @property
    def is_mock(self) -> bool:
        """``True`` when running in mock mode."""
        return isinstance(self._impl, _MockRAGFlowBridge)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_ragflow_bridge(
    api_key: Optional[str] = None,
    base_url: str = "http://localhost:9380",
    timeout: int = 30,
    force_mock: bool = False,
) -> RAGFlowBridge:
    """Create and return a configured ``RAGFlowBridge``.

    Parameters
    ----------
    api_key: str, optional
        RAGFlow API key (env-fallback ``RAGFLOW_API_KEY``).
    base_url: str, optional
        Root API URL.
    timeout: int, optional
        Request timeout.
    force_mock: bool, optional
        Always return the in-memory mock.

    Returns
    -------
    RAGFlowBridge
    """
    return RAGFlowBridge(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
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
    print("=== RAGFlowBridge self-test (mock) ===")
    rag = get_ragflow_bridge(force_mock=True)
    print(f"is_mock = {rag.is_mock}")

    ds = rag.create_dataset("test_kb", "Test knowledge base")
    print(f"Created dataset: {ds['id']}")

    doc = rag.upload_document(ds["id"], "/tmp/mock_doc.pdf")
    print(f"Uploaded doc: {doc['id']}")

    ok = rag.parse_documents(ds["id"])
    print(f"Parse triggered: {ok}")

    chat = rag.create_chat("TestBot", [ds["id"]])
    print(f"Created chat: {chat['id']}")

    answer = rag.ask(chat["id"], "What is the meaning of life?")
    print(f"Answer: {answer[:120]}...")

    print(f"Datasets: {len(rag.list_datasets())}")
    print(f"Chats: {len(rag.list_chats())}")
    print("=== self-test passed ===")


if __name__ == "__main__":
    _self_test()
