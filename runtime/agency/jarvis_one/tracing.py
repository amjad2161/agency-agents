"""Tracing — inspired by Langfuse + OpenTelemetry.

Pure-Python span tree with parent/child relations, attributes, and JSON
export. Compatible-shaped with the OTEL Tracer API at the surface; the
in-memory exporter is the default.
"""

from __future__ import annotations

import contextlib
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class Span:
    name: str
    span_id: str
    parent_id: str | None
    started_at: float
    ended_at: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def add_event(self, name: str, **attrs: Any) -> None:
        self.events.append({"name": name, "ts": time.time(), "attrs": attrs})

    def set(self, **attrs: Any) -> None:
        self.attributes.update(attrs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration": (self.ended_at or time.time()) - self.started_at,
            "attributes": self.attributes,
            "events": list(self.events),
        }


class Tracer:
    """Lightweight tracer with a thread-local active-span stack."""

    def __init__(self) -> None:
        self._spans: list[Span] = []
        self._lock = threading.Lock()
        self._local = threading.local()

    def _stack(self) -> list[str]:
        if not hasattr(self._local, "stack"):
            self._local.stack = []
        return self._local.stack

    @contextlib.contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[Span]:
        parent = self._stack()[-1] if self._stack() else None
        span = Span(name=name, span_id=uuid.uuid4().hex,
                    parent_id=parent, started_at=time.time(),
                    attributes=dict(attrs))
        with self._lock:
            self._spans.append(span)
        self._stack().append(span.span_id)
        try:
            yield span
        finally:
            span.ended_at = time.time()
            if self._stack() and self._stack()[-1] == span.span_id:
                self._stack().pop()

    def export(self) -> list[dict[str, Any]]:
        with self._lock:
            return [s.to_dict() for s in self._spans]

    def clear(self) -> None:
        with self._lock:
            self._spans.clear()
        if hasattr(self._local, "stack"):
            self._local.stack.clear()


_DEFAULT_TRACER = Tracer()


def tracer() -> Tracer:
    return _DEFAULT_TRACER
