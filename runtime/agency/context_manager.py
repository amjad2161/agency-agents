"""
context_manager.py — JARVIS Pass 24
Thread-local context stack with automatic JARVIS context fields.
"""

from __future__ import annotations

import contextlib
import threading
import uuid
from copy import deepcopy
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


class ContextManager:
    """Thread-local context stack with scope() context-manager protocol."""

    def __init__(self, tracer: Any = None):
        self._tracer = tracer or Tracer()
        self._turn_counter = 0
        self._lock = threading.Lock()

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


_default_context_manager: ContextManager | None = None


def get_context_manager() -> ContextManager:
    global _default_context_manager
    if _default_context_manager is None:
        _default_context_manager = ContextManager()
    return _default_context_manager

# === ContextEntry — added by SUPER_DRIVER (Pass 25 hotfix) ===
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

@dataclass
class ContextEntry:
    """Single entry in the agent's working context."""
    content: str
    kind: str = "message"
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"content": self.content, "kind": self.kind, "ts": self.ts,
                "tags": list(self.tags), "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: dict) -> "ContextEntry":
        return cls(content=data.get("content",""), kind=data.get("kind","message"),
                   ts=data.get("ts", datetime.now(timezone.utc).isoformat()),
                   tags=list(data.get("tags",[])), metadata=dict(data.get("metadata",{})))
