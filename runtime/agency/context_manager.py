"""context_manager.py — JARVIS Pass 24 + persistent KV extension.

Two coexisting APIs on a single ContextManager class:

1. Thread-local context stack (Pass 24) — push/pop/get/scope/reset/...
2. Persistent KV store with TTL, tags, domains — store/recall/forget/...

The two APIs share no state. Persistent-store methods operate on
`self._entries`; stack methods operate on the module-level thread-local
`_local.stack`.
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

try:
    from runtime.agency.tracer import Tracer  # type: ignore
except ImportError:
    class Tracer:  # type: ignore
        def push_context(self, **kw: Any) -> None: pass
        def pop_context(self) -> None: pass


_DEFAULTS: dict[str, Any] = {
    "session_id":   lambda: str(uuid.uuid4())[:8],
    "user_id":      lambda: "anonymous",
    "turn_number":  lambda: 0,
    "emotion":      lambda: "neutral",
    "active_skill": lambda: "",
    "robot_mode":   lambda: False,
}

_local = threading.local()


def _get_stack() -> list[dict]:
    if not hasattr(_local, "stack"):
        _local.stack = []
    return _local.stack


def _current_frame() -> dict:
    stack = _get_stack()
    return stack[-1] if stack else {}


DEFAULT_CONTEXT_PATH = Path.home() / ".jarvis" / "context.json"


@dataclass
class ContextEntry:
    """Single entry in the persistent KV store."""

    key: str = ""
    value: Any = None
    domain: str = "default"
    tags: list[str] = field(default_factory=list)
    ttl_seconds: float | None = None
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        if self.ttl_seconds is None or self.ttl_seconds == 0:
            return False
        return time.time() - self.created_at > self.ttl_seconds

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "domain": self.domain,
            "tags": list(self.tags),
            "ttl_seconds": self.ttl_seconds,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContextEntry":
        return cls(
            key=data.get("key", ""),
            value=data.get("value"),
            domain=data.get("domain", "default"),
            tags=list(data.get("tags", [])),
            ttl_seconds=data.get("ttl_seconds"),
            created_at=float(data.get("created_at", time.time())),
        )


class ContextManager:
    """Thread-local stack + persistent KV store."""

    def __init__(
        self,
        store_path: str | Path | None = None,
        tracer: Any = None,
    ):
        self._tracer = tracer or Tracer()
        self._turn_counter = 0
        self._lock = threading.Lock()

        # Persistent KV state
        self._store_path: Path | None = Path(store_path) if store_path else None
        self._entries: dict[str, dict[str, ContextEntry]] = {}
        if self._store_path is not None:
            self._load()

    # ─── Thread-local stack API (Pass 24) ─────────────────────────────────────

    def push(self, key: str, value: Any) -> None:
        stack = _get_stack()
        if not stack:
            stack.append(self._make_initial_frame())
        stack[-1][key] = value
        try:
            self._tracer.push_context(**{key: value})
        except Exception:
            pass

    def pop(self, key: str) -> Any:
        return _current_frame().pop(key, None)

    def get(self, key: str, default: Any = None) -> Any:
        return _current_frame().get(key, default)

    def snapshot(self) -> dict:
        return deepcopy(_current_frame())

    def restore(self, snapshot: dict) -> None:
        stack = _get_stack()
        if not stack:
            stack.append({})
        stack[-1] = deepcopy(snapshot)

    def clear(self) -> None:
        _current_frame().clear()

    def reset(self) -> None:
        _local.stack = []

    @contextlib.contextmanager
    def scope(self, **kwargs: Any) -> Iterator[None]:
        snap = self.snapshot()
        if "turn_number" not in kwargs:
            with self._lock:
                self._turn_counter += 1
                kwargs["turn_number"] = self._turn_counter
        for k, v in kwargs.items():
            self.push(k, v)
        try:
            yield
        finally:
            self.restore(snap)

    def increment_turn(self) -> int:
        with self._lock:
            self._turn_counter += 1
            turn = self._turn_counter
        self.push("turn_number", turn)
        return turn

    def set_robot_mode(self, active: bool) -> None:
        self.push("robot_mode", active)

    def set_skill(self, name: str) -> None:
        self.push("active_skill", name)

    def all(self) -> dict:
        return dict(_current_frame())

    def _make_initial_frame(self) -> dict:
        return {k: v() for k, v in _DEFAULTS.items()}

    # ─── Persistent KV API ────────────────────────────────────────────────────

    def store(
        self,
        key: str,
        value: Any,
        domain: str = "default",
        tags: list[str] | None = None,
        ttl_seconds: float | None = None,
    ) -> ContextEntry:
        entry = ContextEntry(
            key=key,
            value=value,
            domain=domain,
            tags=list(tags or []),
            ttl_seconds=ttl_seconds,
            created_at=time.time(),
        )
        self._entries.setdefault(domain, {})[key] = entry
        self._save()
        return entry

    def recall(self, key: str, domain: str = "default") -> Any:
        entry = self._entries.get(domain, {}).get(key)
        if entry is None:
            return None
        if entry.is_expired():
            self._entries[domain].pop(key, None)
            self._save()
            return None
        return entry.value

    def recall_recent(
        self,
        domain: str | None = None,
        n: int = 10,
    ) -> list[ContextEntry]:
        live: list[ContextEntry] = []
        for d, items in self._entries.items():
            if domain is not None and d != domain:
                continue
            for entry in items.values():
                if not entry.is_expired():
                    live.append(entry)
        live.sort(key=lambda e: e.created_at, reverse=True)
        return live[:n]

    def search_by_tag(self, tag: str) -> list[ContextEntry]:
        out: list[ContextEntry] = []
        for items in self._entries.values():
            for entry in items.values():
                if not entry.is_expired() and tag in entry.tags:
                    out.append(entry)
        return out

    def forget(self, key: str, domain: str = "default") -> bool:
        bucket = self._entries.get(domain)
        if bucket is None or key not in bucket:
            return False
        bucket.pop(key)
        self._save()
        return True

    def purge_expired(self) -> int:
        removed = 0
        for d, items in list(self._entries.items()):
            for k in list(items.keys()):
                if items[k].is_expired():
                    items.pop(k)
                    removed += 1
        if removed:
            self._save()
        return removed

    def dump_domain(self, domain: str) -> dict[str, Any]:
        bucket = self._entries.get(domain, {})
        return {
            k: e.value
            for k, e in bucket.items()
            if not e.is_expired()
        }

    def clear_domain(self, domain: str) -> int:
        bucket = self._entries.pop(domain, {})
        if bucket:
            self._save()
        return len(bucket)

    def all_domains(self) -> list[str]:
        return list(self._entries.keys())

    # ─── Persistence helpers ──────────────────────────────────────────────────

    def _save(self) -> None:
        if self._store_path is None:
            return
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                d: {k: e.to_dict() for k, e in items.items()}
                for d, items in self._entries.items()
            }
            self._store_path.write_text(
                json.dumps(payload, indent=2, default=str),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _load(self) -> None:
        if self._store_path is None or not self._store_path.exists():
            return
        try:
            data = json.loads(self._store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for d, items in data.items():
            self._entries[d] = {
                k: ContextEntry.from_dict(v) for k, v in items.items()
            }


_default_context_manager: ContextManager | None = None


def get_context_manager() -> ContextManager:
    global _default_context_manager
    if _default_context_manager is None:
        _default_context_manager = ContextManager()
    return _default_context_manager
