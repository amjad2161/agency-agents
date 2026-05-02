"""Request tracing for the agency runtime.

Every significant operation (LLM call, skill route, shell execution) can be
wrapped in a ``Span``.  Completed spans are appended to a daily JSONL file at
``~/.agency/traces/YYYY-MM-DD.jsonl`` so they survive across process restarts
and can be tail-inspected or piped to jq.

Quick usage
-----------
    from agency.tracing import get_tracer

    tracer = get_tracer()
    with tracer.span("llm.call", tags={"model": "claude-opus-4-7"}) as span:
        result = call_llm(...)
        span.tags["tokens"] = result.usage.input_tokens

The ``agency traces`` CLI command reads and pretty-prints spans.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Iterator


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Span:
    """A single timed unit of work within a trace."""

    trace_id: str                      # UUID shared by all spans in one request
    span_id: str                       # UUID unique to this span
    name: str                          # human-readable operation name
    start_ms: float                    # epoch-ms at span start
    end_ms: float | None = None        # epoch-ms at span end (None if open)
    tags: dict[str, Any] = field(default_factory=dict)
    error: str | None = None           # exception message if the span errored

    @property
    def duration_ms(self) -> float | None:
        if self.end_ms is None:
            return None
        return round(self.end_ms - self.start_ms, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "name": self.name,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "duration_ms": self.duration_ms,
            "tags": self.tags,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def _traces_dir() -> Path:
    d = Path.home() / ".agency" / "traces"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _trace_file(date: str | None = None) -> Path:
    if date is None:
        date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    return _traces_dir() / f"{date}.jsonl"


_write_lock = threading.Lock()


def _append_span(span: Span) -> None:
    """Persist a completed span to today's JSONL file."""
    line = json.dumps(span.to_dict(), default=str)
    path = _trace_file()
    with _write_lock:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------

class Tracer:
    """Lightweight span factory.

    A ``Tracer`` instance carries a ``trace_id`` that is shared across all
    spans it creates, forming a logical request trace.

    Usage::

        tracer = Tracer()            # new trace_id per instance
        # or
        tracer = Tracer(trace_id="…existing…")

        with tracer.span("llm.call", tags={"model": "x"}) as span:
            ...
    """

    def __init__(self, trace_id: str | None = None) -> None:
        self.trace_id: str = trace_id or str(uuid.uuid4())

    @contextmanager
    def span(
        self,
        name: str,
        tags: dict[str, Any] | None = None,
    ) -> Generator[Span, None, None]:
        """Context manager that creates, yields, and persists a ``Span``.

        The span's ``tags`` dict is mutable inside the block so callers can
        attach result metadata before the block exits::

            with tracer.span("tool.run", tags={"tool": "read_file"}) as sp:
                result = run_tool(...)
                sp.tags["is_error"] = result.is_error
        """
        span = Span(
            trace_id=self.trace_id,
            span_id=str(uuid.uuid4()),
            name=name,
            start_ms=_now_ms(),
            tags=dict(tags or {}),
        )
        try:
            yield span
        except Exception as exc:  # noqa: BLE001
            span.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            span.end_ms = _now_ms()
            try:
                _append_span(span)
            except Exception:  # noqa: BLE001
                pass  # tracing must never crash the hot path


# ---------------------------------------------------------------------------
# Module-level default tracer (process-scoped)
# ---------------------------------------------------------------------------

_default_tracer: Tracer | None = None
_tracer_lock = threading.Lock()


def get_tracer(trace_id: str | None = None) -> Tracer:
    """Return the module-level default ``Tracer``, creating it if needed.

    Pass ``trace_id`` to start a new named trace (replaces the default).
    """
    global _default_tracer
    with _tracer_lock:
        if trace_id is not None or _default_tracer is None:
            _default_tracer = Tracer(trace_id=trace_id)
        return _default_tracer


def new_tracer(trace_id: str | None = None) -> Tracer:
    """Always create a fresh ``Tracer`` (useful per-request)."""
    return Tracer(trace_id=trace_id)


# ---------------------------------------------------------------------------
# Reading / querying spans
# ---------------------------------------------------------------------------

def load_spans(
    date: str | None = None,
    *,
    limit: int | None = None,
) -> list[Span]:
    """Load spans from a JSONL file.

    Parameters
    ----------
    date:
        ``YYYY-MM-DD`` string; defaults to today.
    limit:
        If given, return only the last *limit* spans.
    """
    path = _trace_file(date)
    if not path.exists():
        return []
    spans: list[Span] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                spans.append(Span(
                    trace_id=d.get("trace_id", ""),
                    span_id=d.get("span_id", ""),
                    name=d.get("name", ""),
                    start_ms=float(d.get("start_ms", 0)),
                    end_ms=float(d["end_ms"]) if d.get("end_ms") is not None else None,
                    tags=d.get("tags", {}),
                    error=d.get("error"),
                ))
            except (KeyError, ValueError, json.JSONDecodeError):
                continue
    except OSError:
        return []
    if limit is not None:
        spans = spans[-limit:]
    return spans


def list_trace_dates() -> list[str]:
    """Return available trace dates (YYYY-MM-DD), newest first."""
    d = _traces_dir()
    dates = sorted(
        (f.stem for f in d.glob("*.jsonl") if f.stem),
        reverse=True,
    )
    return dates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_ms() -> float:
    return time.time() * 1000
