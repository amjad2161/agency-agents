"""
mem0_bridge.py — Mem0 Memory Integration for JARVIS BRAINIAC
===========================================================

Provides a unified bridge to the Mem0 memory platform with automatic mock
fallback when the ``mem0ai`` package is not installed.

Public API
----------
* ``Mem0Bridge``        – Main client wrapper (real or mock).
* ``get_mem0_bridge``   – Factory that returns a configured ``Mem0Bridge``.
* ``is_mem0_available`` – Runtime probe for mem0ai availability.

Typical usage::

    from jarvis.runtime.agency.mem0_bridge import get_mem0_bridge

    mem = get_mem0_bridge(api_key="<KEY>", user_id="tony")
    mem.add_memory("Jarvis, remember that I prefer dark mode.")
    results = mem.get_memory("dark mode preference")
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("jarvis.runtime.agency.mem0_bridge")
logger.addHandler(logging.NullHandler())

# ---------------------------------------------------------------------------
# Dependency probe
# ---------------------------------------------------------------------------

_MEM0_AVAILABLE: Optional[bool] = None

def is_mem0_available() -> bool:
    """Return ``True`` if ``mem0ai`` is importable."""
    global _MEM0_AVAILABLE
    if _MEM0_AVAILABLE is not None:
        return _MEM0_AVAILABLE
    try:
        import mem0ai  # noqa: F401
        _MEM0_AVAILABLE = True
    except Exception:
        _MEM0_AVAILABLE = False
    return _MEM0_AVAILABLE


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class MemoryEntry:
    """Represents a single memory record returned by Mem0."""
    id: str
    content: str
    user_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the entry to a plain dict."""
        return {
            "id": self.id,
            "content": self.content,
            "user_id": self.user_id,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        """Reconstruct a ``MemoryEntry`` from a dict."""
        return cls(
            id=data.get("id", ""),
            content=data.get("content", ""),
            user_id=data.get("user_id", "jarvis"),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            score=data.get("score", 0.0),
        )


@dataclass
class MemoryResult:
    """Container for paginated memory search results."""
    memories: List[MemoryEntry]
    total: int = 0
    query: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memories": [m.to_dict() for m in self.memories],
            "total": self.total,
            "query": self.query,
        }


# ---------------------------------------------------------------------------
# Abstract base / protocol
# ---------------------------------------------------------------------------

class _BaseMem0Bridge:
    """Shared interface implemented by both real and mock adapters."""

    def add_memory(self, message: str, user_id: str = "jarvis", metadata: Optional[Dict[str, Any]] = None) -> str:
        raise NotImplementedError

    def get_memory(self, query: str, user_id: str = "jarvis", limit: int = 10) -> MemoryResult:
        raise NotImplementedError

    def update_memory(self, memory_id: str, new_message: str) -> bool:
        raise NotImplementedError

    def delete_memory(self, memory_id: str) -> bool:
        raise NotImplementedError

    def get_all_memories(self, user_id: str = "jarvis") -> MemoryResult:
        raise NotImplementedError

    def process_and_store(self, message: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Real implementation — backed by mem0ai
# ---------------------------------------------------------------------------

class _RealMem0Bridge(_BaseMem0Bridge):
    """Production bridge that talks to the Mem0 API via ``mem0ai``."""

    def __init__(self, api_key: str, user_id: str = "jarvis", host: Optional[str] = None, org_id: Optional[str] = None, project_id: Optional[str] = None) -> None:
        self.api_key = api_key
        self.user_id = user_id
        self.host = host
        self.org_id = org_id
        self.project_id = project_id

        from mem0ai import Mem0Client

        kwargs: Dict[str, Any] = {"api_key": api_key}
        if host:
            kwargs["host"] = host
        if org_id:
            kwargs["org_id"] = org_id
        if project_id:
            kwargs["project_id"] = project_id

        self._client = Mem0Client(**kwargs)
        logger.info("Real Mem0Bridge initialised (user_id=%s).", user_id)

    # ---- public API -------------------------------------------------------

    def add_memory(self, message: str, user_id: str = "jarvis", metadata: Optional[Dict[str, Any]] = None) -> str:
        """Add a new memory entry for *user_id*.

        Parameters
        ----------
        message: str
            Free-text memory to store.
        user_id: str, optional
            Identifier for the owner of the memory (default ``"jarvis"``).
        metadata: dict, optional
            Arbitrary key/value pairs to attach.

        Returns
        -------
        str
            The unique memory ID returned by Mem0.
        """
        meta = metadata or {}
        try:
            response = self._client.add(messages=message, user_id=user_id, metadata=meta)
            memory_id = response.get("id", "")
            logger.debug("Added memory id=%s for user=%s", memory_id, user_id)
            return memory_id
        except Exception as exc:
            logger.error("Failed to add memory: %s", exc)
            return ""

    def get_memory(self, query: str, user_id: str = "jarvis", limit: int = 10) -> MemoryResult:
        """Search stored memories semantically.

        Parameters
        ----------
        query: str
            Natural-language search string.
        user_id: str, optional
            Filter to this user.
        limit: int
            Maximum number of results.

        Returns
        -------
        MemoryResult
            Paginated results wrapper.
        """
        try:
            raw = self._client.search(query=query, user_id=user_id, limit=limit)
            entries = [_normalize_entry(r) for r in raw]
            return MemoryResult(memories=entries, total=len(entries), query=query)
        except Exception as exc:
            logger.error("Memory search failed: %s", exc)
            return MemoryResult(memories=[], total=0, query=query)

    def update_memory(self, memory_id: str, new_message: str) -> bool:
        """Update an existing memory by ID.

        Parameters
        ----------
        memory_id: str
            UUID of the target memory.
        new_message: str
            Replacement text.

        Returns
        -------
        bool
            ``True`` on success.
        """
        try:
            self._client.update(memory_id=memory_id, data=new_message)
            logger.debug("Updated memory id=%s", memory_id)
            return True
        except Exception as exc:
            logger.error("Failed to update memory %s: %s", memory_id, exc)
            return False

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a single memory entry.

        Parameters
        ----------
        memory_id: str
            UUID of the memory to remove.

        Returns
        -------
        bool
            ``True`` on success.
        """
        try:
            self._client.delete(memory_id=memory_id)
            logger.debug("Deleted memory id=%s", memory_id)
            return True
        except Exception as exc:
            logger.error("Failed to delete memory %s: %s", memory_id, exc)
            return False

    def get_all_memories(self, user_id: str = "jarvis") -> MemoryResult:
        """List every memory belonging to *user_id*.

        Returns
        -------
        MemoryResult
        """
        try:
            raw = self._client.get_all(user_id=user_id)
            entries = [_normalize_entry(r) for r in raw]
            return MemoryResult(memories=entries, total=len(entries), query="__all__")
        except Exception as exc:
            logger.error("Failed to list memories: %s", exc)
            return MemoryResult(memories=[], total=0, query="__all__")

    def process_and_store(self, message: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Pre-process *message* (extract facts, deduplicate) then store.

        Parameters
        ----------
        message: str
            Raw conversational message.
        metadata: dict, optional
            Extra context to persist.

        Returns
        -------
        str
            The primary memory ID that was stored.
        """
        meta = metadata or {}
        meta["processed"] = True
        meta["processed_at"] = _utc_now()
        return self.add_memory(message, user_id=self.user_id, metadata=meta)


# ---------------------------------------------------------------------------
# Mock implementation — in-memory fallback
# ---------------------------------------------------------------------------

class _MockMem0Bridge(_BaseMem0Bridge):
    """In-memory fallback used when ``mem0ai`` is unavailable.

    All data lives in ``self._store``: ``Dict[user_id, List[MemoryEntry]]``.
    """

    def __init__(self, user_id: str = "jarvis") -> None:
        self.user_id = user_id
        self._store: Dict[str, List[MemoryEntry]] = {}
        logger.info("Mock Mem0Bridge initialised (user_id=%s).", user_id)

    # ---- public API -------------------------------------------------------

    def add_memory(self, message: str, user_id: str = "jarvis", metadata: Optional[Dict[str, Any]] = None) -> str:
        """Add a memory entry to the local dict store."""
        memory_id = str(uuid.uuid4())
        entry = MemoryEntry(
            id=memory_id,
            content=message,
            user_id=user_id,
            metadata=metadata or {},
            created_at=_utc_now(),
            updated_at=_utc_now(),
            score=1.0,
        )
        self._store.setdefault(user_id, []).append(entry)
        logger.debug("[MOCK] Added memory id=%s for user=%s", memory_id, user_id)
        return memory_id

    def get_memory(self, query: str, user_id: str = "jarvis", limit: int = 10) -> MemoryResult:
        """Naïve keyword search over local store."""
        candidates = self._store.get(user_id, [])
        tokens = query.lower().split()
        scored: List[Tuple[float, MemoryEntry]] = []
        for entry in candidates:
            text = entry.content.lower()
            score = sum(1 for t in tokens if t in text)
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [e for _, e in scored[:limit]]
        return MemoryResult(memories=results, total=len(results), query=query)

    def update_memory(self, memory_id: str, new_message: str) -> bool:
        """Find and update by ID."""
        for uid, entries in self._store.items():
            for entry in entries:
                if entry.id == memory_id:
                    entry.content = new_message
                    entry.updated_at = _utc_now()
                    logger.debug("[MOCK] Updated memory id=%s", memory_id)
                    return True
        logger.warning("[MOCK] Memory id=%s not found for update.", memory_id)
        return False

    def delete_memory(self, memory_id: str) -> bool:
        """Remove a memory by ID."""
        for uid, entries in self._store.items():
            for idx, entry in enumerate(entries):
                if entry.id == memory_id:
                    entries.pop(idx)
                    logger.debug("[MOCK] Deleted memory id=%s", memory_id)
                    return True
        logger.warning("[MOCK] Memory id=%s not found for deletion.", memory_id)
        return False

    def get_all_memories(self, user_id: str = "jarvis") -> MemoryResult:
        """Return every entry for *user_id*."""
        entries = list(self._store.get(user_id, []))
        return MemoryResult(memories=entries, total=len(entries), query="__all__")

    def process_and_store(self, message: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Store with a ``processed`` flag."""
        meta = metadata or {}
        meta["processed"] = True
        meta["processed_at"] = _utc_now()
        return self.add_memory(message, user_id=self.user_id, metadata=meta)


# ---------------------------------------------------------------------------
# Public wrapper
# ---------------------------------------------------------------------------

class Mem0Bridge(_BaseMem0Bridge):
    """Unified Mem0 client for JARVIS BRAINIAC.

    Automatically selects the real implementation when ``mem0ai`` is installed,
    otherwise falls back to an in-memory mock.

    Parameters
    ----------
    api_key: str, optional
        Mem0 API key. Falls back to ``MEM0_API_KEY`` env var.
    user_id: str, optional
        Default user identity (default ``"jarvis"``).
    host: str, optional
        Custom Mem0 host URL.
    org_id: str, optional
        Organisation ID for multi-tenant setups.
    project_id: str, optional
        Project scoping.
    force_mock: bool, optional
        If ``True``, always use the mock implementation.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        user_id: str = "jarvis",
        host: Optional[str] = None,
        org_id: Optional[str] = None,
        project_id: Optional[str] = None,
        force_mock: bool = False,
    ) -> None:
        resolved_key = api_key or os.environ.get("MEM0_API_KEY", "")
        self.user_id = user_id

        if not force_mock and is_mem0_available() and resolved_key:
            self._impl: _BaseMem0Bridge = _RealMem0Bridge(
                api_key=resolved_key,
                user_id=user_id,
                host=host,
                org_id=org_id,
                project_id=project_id,
            )
        else:
            if not force_mock and not is_mem0_available():
                logger.warning("mem0ai not installed — falling back to mock.")
            elif not force_mock and not resolved_key:
                logger.warning("MEM0_API_KEY not set — falling back to mock.")
            self._impl = _MockMem0Bridge(user_id=user_id)

    # ---- delegated public API ---------------------------------------------

    def add_memory(self, message: str, user_id: str = "jarvis", metadata: Optional[Dict[str, Any]] = None) -> str:
        """Add a memory entry."""
        return self._impl.add_memory(message, user_id=user_id, metadata=metadata)

    def get_memory(self, query: str, user_id: str = "jarvis", limit: int = 10) -> MemoryResult:
        """Search memories."""
        return self._impl.get_memory(query, user_id=user_id, limit=limit)

    def update_memory(self, memory_id: str, new_message: str) -> bool:
        """Update a memory."""
        return self._impl.update_memory(memory_id, new_message)

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory."""
        return self._impl.delete_memory(memory_id)

    def get_all_memories(self, user_id: str = "jarvis") -> MemoryResult:
        """List all memories for a user."""
        return self._impl.get_all_memories(user_id)

    def process_and_store(self, message: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Process and store a memory."""
        return self._impl.process_and_store(message, metadata=metadata)

    @property
    def is_mock(self) -> bool:
        """Return ``True`` when running in mock mode."""
        return isinstance(self._impl, _MockMem0Bridge)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_mem0_bridge(
    api_key: Optional[str] = None,
    user_id: str = "jarvis",
    host: Optional[str] = None,
    org_id: Optional[str] = None,
    project_id: Optional[str] = None,
    force_mock: bool = False,
) -> Mem0Bridge:
    """Create and return a configured ``Mem0Bridge``.

    Parameters
    ----------
    api_key: str, optional
        Mem0 API key (env-fallback to ``MEM0_API_KEY``).
    user_id: str, optional
        Default user identity.
    host: str, optional
        Custom Mem0 host URL.
    org_id: str, optional
        Organisation identifier.
    project_id: str, optional
        Project identifier.
    force_mock: bool, optional
        Always return the in-memory mock.

    Returns
    -------
    Mem0Bridge
    """
    return Mem0Bridge(
        api_key=api_key,
        user_id=user_id,
        host=host,
        org_id=org_id,
        project_id=project_id,
        force_mock=force_mock,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    """Return ISO-8601 timestamp in UTC."""
    return datetime.now(timezone.utc).isoformat()


def _normalize_entry(raw: Dict[str, Any]) -> MemoryEntry:
    """Coerce a raw Mem0 result dict into a ``MemoryEntry``."""
    return MemoryEntry(
        id=raw.get("id", ""),
        content=raw.get("memory", raw.get("content", "")),
        user_id=raw.get("user_id", "jarvis"),
        metadata=raw.get("metadata", {}),
        created_at=raw.get("created_at", ""),
        updated_at=raw.get("updated_at", ""),
        score=raw.get("score", 0.0),
    )


# ---------------------------------------------------------------------------
# Standalone health-check / demo
# ---------------------------------------------------------------------------

def _self_test() -> None:
    """Quick smoke test for the mock implementation."""
    logging.basicConfig(level=logging.DEBUG)
    print("=== Mem0Bridge self-test (mock) ===")
    bridge = get_mem0_bridge(force_mock=True)
    print(f"is_mock = {bridge.is_mock}")

    mid1 = bridge.add_memory("I prefer dark mode on all interfaces.", user_id="tony")
    mid2 = bridge.add_memory("My favourite colour is red.", user_id="tony")
    print(f"Added memories: {mid1}, {mid2}")

    result = bridge.get_memory("dark mode", user_id="tony")
    print(f"Search 'dark mode' → {len(result.memories)} result(s)")

    all_mem = bridge.get_all_memories("tony")
    print(f"All memories for tony: {all_mem.total}")

    ok = bridge.update_memory(mid1, "I prefer dark mode everywhere.")
    print(f"Update OK: {ok}")

    ok = bridge.delete_memory(mid2)
    print(f"Delete OK: {ok}")

    all_mem = bridge.get_all_memories("tony")
    print(f"Remaining memories: {all_mem.total}")
    print("=== self-test passed ===")


if __name__ == "__main__":
    _self_test()
