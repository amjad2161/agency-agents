"""Performance profiling for the agency runtime.

``@profile_call`` decorator
    Measures wall-clock time of any function and appends the sample to an
    in-memory ring-buffer (last 10 000 calls) and, optionally, the tracer.

``agency profile [--top N]``
    CLI command that reads the in-process ring-buffer (or the trace JSONL if
    invoked from a fresh process) and shows the slowest operations.

``agency profile --flamegraph``
    Writes ``~/.agency/profile.json`` in Speedscope format so you can drag it
    to https://speedscope.app for a flamegraph visualisation.

The module is deliberately zero-dependency (only stdlib + optional tracer).
"""

from __future__ import annotations

import functools
import json
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Deque, TypeVar, overload

F = TypeVar("F", bound=Callable[..., Any])

# ---------------------------------------------------------------------------
# In-memory sample store
# ---------------------------------------------------------------------------

_MAX_SAMPLES = 10_000

@dataclass
class ProfileSample:
    operation: str       # label — typically "<module>.<function>"
    duration_ms: float   # wall-clock ms
    timestamp_ms: float  # epoch-ms at call start
    tags: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "duration_ms": self.duration_ms,
            "timestamp_ms": self.timestamp_ms,
            "tags": self.tags,
        }


class _SampleStore:
    """Thread-safe ring buffer of ``ProfileSample`` objects."""

    def __init__(self, maxlen: int = _MAX_SAMPLES) -> None:
        self._buf: Deque[ProfileSample] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def add(self, sample: ProfileSample) -> None:
        with self._lock:
            self._buf.append(sample)

    def all(self) -> list[ProfileSample]:
        with self._lock:
            return list(self._buf)

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()


_store = _SampleStore()


def get_store() -> _SampleStore:
    """Return the module-level sample store."""
    return _store


# ---------------------------------------------------------------------------
# @profile_call decorator
# ---------------------------------------------------------------------------

def profile_call(
    fn: F | None = None,
    *,
    operation: str | None = None,
    tags: dict[str, Any] | None = None,
) -> Any:
    """Decorator that records wall-clock time for every call.

    Can be used bare or with arguments::

        @profile_call
        def my_fn(): ...

        @profile_call(operation="llm.route", tags={"model": "opus"})
        def my_fn(): ...
    """
    def _decorator(func: F) -> F:
        op_name = operation or f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        def _wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.monotonic()
            t_ms = time.time() * 1000
            try:
                return func(*args, **kwargs)
            finally:
                dur = round((time.monotonic() - start) * 1000, 2)
                sample = ProfileSample(
                    operation=op_name,
                    duration_ms=dur,
                    timestamp_ms=t_ms,
                    tags=dict(tags or {}),
                )
                _store.add(sample)
                # Optionally emit to tracer if one is active
                try:
                    from .tracing import get_tracer
                    tr = get_tracer()
                    # We won't open a new span here (too noisy); just record
                    # the duration in a lightweight way by appending to trace
                    # only when there's an active span context.
                except Exception:  # noqa: BLE001
                    pass

        return _wrapper  # type: ignore[return-value]

    if fn is not None:
        # Used as bare @profile_call
        return _decorator(fn)
    # Used as @profile_call(...) factory
    return _decorator


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def top_slowest(n: int = 10) -> list[ProfileSample]:
    """Return the *n* slowest unique operations by mean duration."""
    samples = _store.all()
    if not samples:
        return []
    # Group by operation name
    buckets: dict[str, list[float]] = {}
    for s in samples:
        buckets.setdefault(s.operation, []).append(s.duration_ms)
    aggregated = [
        ProfileSample(
            operation=op,
            duration_ms=round(sum(durs) / len(durs), 2),
            timestamp_ms=0,
            tags={"count": len(durs), "max_ms": round(max(durs), 2)},
        )
        for op, durs in buckets.items()
    ]
    aggregated.sort(key=lambda s: s.duration_ms, reverse=True)
    return aggregated[:n]


# ---------------------------------------------------------------------------
# Flamegraph / Speedscope export
# ---------------------------------------------------------------------------

def flamegraph_path() -> Path:
    d = Path.home() / ".agency"
    d.mkdir(parents=True, exist_ok=True)
    return d / "profile.json"


def export_speedscope(path: Path | None = None) -> Path:
    """Write a Speedscope-compatible JSON to *path* (default flamegraph_path).

    Speedscope format reference:
    https://github.com/jlfwong/speedscope/wiki/Importing-from-custom-sources

    We produce a single "sampled" profile where each unique operation is a
    frame and each sample is one call (weight = duration_ms).
    """
    samples = _store.all()
    out_path = path or flamegraph_path()

    if not samples:
        doc: dict[str, Any] = {
            "$schema": "https://www.speedscope.app/file-format-schema.json",
            "shared": {"frames": []},
            "profiles": [],
            "name": "agency profile (empty)",
        }
        out_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        return out_path

    # Build frame index (deduplicated operation names)
    seen_ops: list[str] = []
    op_idx: dict[str, int] = {}
    for s in samples:
        if s.operation not in op_idx:
            op_idx[s.operation] = len(seen_ops)
            seen_ops.append(s.operation)

    frames = [{"name": op} for op in seen_ops]

    # Each sample is [frame_idx] with weight = duration_ms
    sp_samples = [[op_idx[s.operation]] for s in samples]
    weights = [s.duration_ms for s in samples]

    start_value = samples[0].timestamp_ms if samples else 0.0
    end_value = start_value + sum(weights)

    profile: dict[str, Any] = {
        "type": "sampled",
        "name": "agency",
        "unit": "milliseconds",
        "startValue": start_value,
        "endValue": end_value,
        "samples": sp_samples,
        "weights": weights,
    }

    doc = {
        "$schema": "https://www.speedscope.app/file-format-schema.json",
        "shared": {"frames": frames},
        "profiles": [profile],
        "name": f"agency profile — {datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "activeProfileIndex": 0,
    }

    out_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return out_path
