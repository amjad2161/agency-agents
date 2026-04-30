"""Pass-24 thread-local context manager.

Lightweight scope-based context — every coroutine/thread can push and pop
a context dictionary; child scopes inherit by lookup. Used by the API
gateway so the chosen skill, decision confidence, request id, and trace
id are visible to inner subsystems without being threaded through the
call chain explicitly.
"""

from __future__ import annotations

import contextlib
import threading
import uuid
from typing import Any, Iterator

_LOCAL = threading.local()


def _stack() -> list[dict[str, Any]]:
    if not hasattr(_LOCAL, "stack"):
        _LOCAL.stack = [{"request_id": uuid.uuid4().hex}]
    return _LOCAL.stack


def get(key: str, default: Any = None) -> Any:
    """Look up *key* in the nearest enclosing scope."""
    for scope in reversed(_stack()):
        if key in scope:
            return scope[key]
    return default


def set_value(key: str, value: Any) -> None:
    """Set *key* in the innermost scope."""
    _stack()[-1][key] = value


def snapshot() -> dict[str, Any]:
    """Flatten the entire stack into a single dict (innermost wins)."""
    flat: dict[str, Any] = {}
    for scope in _stack():
        flat.update(scope)
    return flat


@contextlib.contextmanager
def scope(**values: Any) -> Iterator[dict[str, Any]]:
    """Push a new scope with *values*; pop on exit."""
    new_scope: dict[str, Any] = dict(values)
    new_scope.setdefault("trace_id", uuid.uuid4().hex)
    _stack().append(new_scope)
    try:
        yield new_scope
    finally:
        if _stack() and _stack()[-1] is new_scope:
            _stack().pop()


def reset() -> None:
    """Reset to a fresh root scope (used in tests)."""
    if hasattr(_LOCAL, "stack"):
        del _LOCAL.stack
