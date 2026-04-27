"""Observability tracing — Span / Tracer with pluggable backends.

Inspired by Langfuse + OpenTelemetry. External SDKs (langfuse,
opentelemetry) are optional. Default backend is "log" — writes spans
to the agency logger. "none" disables tracing entirely.
"""

from __future__ import annotations

import contextlib
import functools
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterator

from .logging import get_logger

log = get_logger()


@dataclass
class Span:
    """One traced operation."""

    span_id: str
    name: str
    start_time: float
    end_time: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "running"  # running | ok | error
    parent_id: str | None = None
    trace_id: str | None = None

    @property
    def duration_ms(self) -> float | None:
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["duration_ms"] = self.duration_ms
        return d


class Tracer:
    """Tracer with pluggable backends.

    backends:
      - log: writes spans to logger (default, no deps)
      - langfuse: pushes to Langfuse (requires `langfuse` package)
      - otel: pushes to OpenTelemetry (requires `opentelemetry-api`)
      - none: disabled
    """

    def __init__(self, backend: str = "log") -> None:
        self.backend = backend
        self.spans: dict[str, Span] = {}
        self.traces: dict[str, list[str]] = {}  # trace_id -> [span_ids]
        self._stack: list[str] = []  # current span stack
        self._langfuse_client = None
        self._otel_tracer = None
        self._init_backend()

    def _init_backend(self) -> None:
        if self.backend == "langfuse":
            try:
                from langfuse import Langfuse  # type: ignore

                self._langfuse_client = Langfuse()
            except Exception as e:  # pragma: no cover
                log.warning("langfuse unavailable, falling back to log: %s", e)
                self.backend = "log"
        elif self.backend == "otel":
            try:
                from opentelemetry import trace as otel_trace  # type: ignore

                self._otel_tracer = otel_trace.get_tracer("agency")
            except Exception as e:  # pragma: no cover
                log.warning("opentelemetry unavailable, falling back to log: %s", e)
                self.backend = "log"

    def start_span(
        self,
        name: str,
        metadata: dict[str, Any] | None = None,
        parent_id: str | None = None,
    ) -> Span:
        span_id = uuid.uuid4().hex
        if parent_id is None and self._stack:
            parent_id = self._stack[-1]
        trace_id = (
            self.spans[parent_id].trace_id if parent_id and parent_id in self.spans
            else span_id
        )
        span = Span(
            span_id=span_id,
            name=name,
            start_time=time.time(),
            metadata=dict(metadata or {}),
            parent_id=parent_id,
            trace_id=trace_id,
        )
        self.spans[span_id] = span
        self.traces.setdefault(trace_id, []).append(span_id)
        self._stack.append(span_id)
        if self.backend == "log":
            log.debug("span.start name=%s id=%s parent=%s", name, span_id, parent_id)
        return span

    def end_span(self, span_id: str, status: str = "ok") -> Span | None:
        span = self.spans.get(span_id)
        if span is None:
            return None
        span.end_time = time.time()
        span.status = status
        if self._stack and self._stack[-1] == span_id:
            self._stack.pop()
        else:
            # Out-of-order close — drop from anywhere in stack
            self._stack = [s for s in self._stack if s != span_id]
        if self.backend == "log":
            log.info(
                "span.end name=%s id=%s status=%s duration_ms=%.2f",
                span.name,
                span.span_id,
                span.status,
                span.duration_ms or 0.0,
            )
        elif self.backend == "langfuse" and self._langfuse_client:
            try:  # pragma: no cover
                self._langfuse_client.trace(
                    name=span.name,
                    metadata=span.metadata,
                )
            except Exception as e:
                log.warning("langfuse push failed: %s", e)
        return span

    @contextlib.contextmanager
    def span(
        self, name: str, metadata: dict[str, Any] | None = None
    ) -> Iterator[Span]:
        s = self.start_span(name, metadata)
        try:
            yield s
            self.end_span(s.span_id, "ok")
        except Exception as e:
            s.metadata["error"] = repr(e)
            self.end_span(s.span_id, "error")
            raise

    def trace(self, name: str | None = None) -> Callable:
        """Decorator that wraps a function in a span."""

        def decorator(fn: Callable) -> Callable:
            span_name = name or fn.__name__

            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                with self.span(span_name, {"args_count": len(args)}):
                    return fn(*args, **kwargs)

            return wrapper

        return decorator

    def get_trace(self, span_id: str) -> list[Span]:
        """Return all spans sharing the same trace as `span_id`."""
        span = self.spans.get(span_id)
        if span is None:
            return []
        ids = self.traces.get(span.trace_id or span_id, [])
        return [self.spans[i] for i in ids if i in self.spans]

    def get_span(self, span_id: str) -> Span | None:
        return self.spans.get(span_id)

    def all_spans(self) -> list[Span]:
        return list(self.spans.values())

    def clear(self) -> None:
        self.spans.clear()
        self.traces.clear()
        self._stack.clear()


_tracer: Tracer | None = None


def get_tracer(backend: str = "log") -> Tracer:
    global _tracer
    if _tracer is None:
        _tracer = Tracer(backend=backend)
    return _tracer


def reset_tracer() -> None:
    """Test helper — drops the singleton."""
    global _tracer
    _tracer = None


__all__ = ["Span", "Tracer", "get_tracer", "reset_tracer"]
