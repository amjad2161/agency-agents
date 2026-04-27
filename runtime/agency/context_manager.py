"""Persistent cross-session context manager for JARVIS.

Stores and retrieves structured context entries keyed by domain / session.
Backend: JSON file at ~/.jarvis/context_store.json (atomic write via tmp file).
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .logging import get_logger

DEFAULT_CONTEXT_PATH = Path.home() / ".jarvis" / "context_store.json"

log = get_logger()


@dataclass
class ContextEntry:
    """One unit of stored context."""

    key: str
    value: Any
    domain: str = "general"
    session_id: str = ""
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    ttl_seconds: float = 0.0          # 0 = no expiry
    tags: list[str] = field(default_factory=list)

    def is_expired(self) -> bool:
        if self.ttl_seconds <= 0:
            return False
        return time.time() - self.created_at > self.ttl_seconds

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ContextEntry":
        return cls(**d)


class ContextManager:
    """Persistent context store with TTL, tagging, and domain namespacing.

    Usage::

        cm = ContextManager()
        cm.store("user_goal", "build a rate limiter", domain="engineering")
        val = cm.recall("user_goal", domain="engineering")
        recent = cm.recall_recent(domain="engineering", n=5)
    """

    def __init__(self, store_path: Path | None = None) -> None:
        self._path = store_path or DEFAULT_CONTEXT_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._cache: dict[str, ContextEntry] = {}
        self._load()

    # ── public API ────────────────────────────────────────────────────────────

    def store(
        self,
        key: str,
        value: Any,
        domain: str = "general",
        session_id: str = "",
        ttl_seconds: float = 0.0,
        tags: list[str] | None = None,
    ) -> ContextEntry:
        """Store a value under *key* in *domain* namespace."""
        full_key = self._full_key(domain, key)
        entry = ContextEntry(
            key=key,
            value=value,
            domain=domain,
            session_id=session_id,
            ttl_seconds=ttl_seconds,
            tags=tags or [],
        )
        with self._lock:
            self._cache[full_key] = entry
            self._persist()
        log.debug("context_manager: stored '%s' in domain '%s'", key, domain)
        return entry

    def recall(self, key: str, domain: str = "general") -> Any | None:
        """Retrieve value for *key* in *domain*. Returns None if missing/expired."""
        full_key = self._full_key(domain, key)
        with self._lock:
            entry = self._cache.get(full_key)
            if entry is None:
                return None
            if entry.is_expired():
                del self._cache[full_key]
                self._persist()
                return None
            entry.accessed_at = time.time()
            return entry.value

    def recall_recent(self, domain: str | None = None, n: int = 10) -> list[ContextEntry]:
        """Return last *n* non-expired entries, optionally filtered by *domain*."""
        with self._lock:
            entries = [
                e for e in self._cache.values()
                if not e.is_expired() and (domain is None or e.domain == domain)
            ]
        entries.sort(key=lambda e: e.accessed_at, reverse=True)
        return entries[:n]

    def search_by_tag(self, tag: str) -> list[ContextEntry]:
        """Return all non-expired entries that carry *tag*."""
        with self._lock:
            return [
                e for e in self._cache.values()
                if tag in e.tags and not e.is_expired()
            ]

    def forget(self, key: str, domain: str = "general") -> bool:
        """Delete an entry. Returns True if it existed."""
        full_key = self._full_key(domain, key)
        with self._lock:
            existed = full_key in self._cache
            self._cache.pop(full_key, None)
            if existed:
                self._persist()
        return existed

    def purge_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        with self._lock:
            expired = [k for k, e in self._cache.items() if e.is_expired()]
            for k in expired:
                del self._cache[k]
            if expired:
                self._persist()
        return len(expired)

    def dump_domain(self, domain: str) -> dict[str, Any]:
        """Return {key: value} snapshot for *domain* (non-expired)."""
        with self._lock:
            return {
                e.key: e.value
                for e in self._cache.values()
                if e.domain == domain and not e.is_expired()
            }

    def clear_domain(self, domain: str) -> int:
        """Delete all entries in *domain*. Returns count."""
        with self._lock:
            keys = [k for k, e in self._cache.items() if e.domain == domain]
            for k in keys:
                del self._cache[k]
            if keys:
                self._persist()
        return len(keys)

    def all_domains(self) -> list[str]:
        """List distinct domain names that have live entries."""
        with self._lock:
            return list({e.domain for e in self._cache.values() if not e.is_expired()})

    # ── internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _full_key(domain: str, key: str) -> str:
        return f"{domain}::{key}"

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            for full_key, d in raw.items():
                try:
                    self._cache[full_key] = ContextEntry.from_dict(d)
                except Exception:
                    pass
        except Exception as exc:
            log.warning("context_manager: failed to load store: %s", exc)

    def _persist(self) -> None:
        """Atomic write to avoid corruption on crash."""
        data = {k: e.to_dict() for k, e in self._cache.items()}
        tmp = self._path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(tmp, self._path)
        except Exception as exc:
            log.warning("context_manager: failed to persist: %s", exc)
