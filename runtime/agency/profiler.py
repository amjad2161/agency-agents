"""Request profiler: context manager, wall-time recording, percentile stats."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from types import TracebackType
from typing import Any


_DEFAULT_PATH = Path.home() / ".agency" / "profile_data.jsonl"


class Profiler:
    """Context manager that records wall-clock time for a named operation.

    Usage::

        with Profiler("task_name") as p:
            do_work()
        print(p.elapsed_s)

    Results are appended to *data_path* (default ~/.agency/profile_data.jsonl).
    Use the module-level ``get_stats`` / ``report`` functions to analyse them.
    """

    def __init__(
        self,
        name: str,
        data_path: Path | None = None,
    ) -> None:
        self.name = name
        self._path = Path(data_path) if data_path else _DEFAULT_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self.elapsed_s: float = 0.0
        self._start: float = 0.0

    def __enter__(self) -> "Profiler":
        self._start = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.elapsed_s = time.perf_counter() - self._start
        self._append()

    def _append(self) -> None:
        record = {"name": self.name, "elapsed_s": self.elapsed_s, "ts": time.time()}
        try:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except OSError:
            pass  # non-fatal


# ---------------------------------------------------------------------------
# Module-level analysis helpers
# ---------------------------------------------------------------------------

def _load_records(data_path: Path | None = None) -> list[dict[str, Any]]:
    path = Path(data_path) if data_path else _DEFAULT_PATH
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    records = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return records


def _percentile(data: list[float], pct: float) -> float:
    """Return the *pct*-th percentile of *data* (0–100)."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * pct / 100.0
    lo, hi = int(k), min(int(k) + 1, len(sorted_data) - 1)
    frac = k - lo
    return sorted_data[lo] * (1 - frac) + sorted_data[hi] * frac


def get_stats(name: str, data_path: Path | None = None) -> dict:
    """Return mean / p50 / p95 / p99 for the named operation (in seconds)."""
    records = _load_records(data_path)
    samples = [r["elapsed_s"] for r in records if r.get("name") == name]
    if not samples:
        return {"name": name, "count": 0, "mean": 0.0,
                "p50": 0.0, "p95": 0.0, "p99": 0.0}
    return {
        "name": name,
        "count": len(samples),
        "mean": statistics.mean(samples),
        "p50": _percentile(samples, 50),
        "p95": _percentile(samples, 95),
        "p99": _percentile(samples, 99),
    }


def report(data_path: Path | None = None) -> str:
    """Return a human-readable profiler report for all recorded operations."""
    records = _load_records(data_path)
    if not records:
        return "No profiler data recorded yet."

    names = sorted({r["name"] for r in records})
    header = f"{'Operation':<30} {'Count':>6} {'Mean ms':>9} {'p50 ms':>9} {'p95 ms':>9} {'p99 ms':>9}"
    sep = "-" * len(header)
    lines = [header, sep]
    for name in names:
        s = get_stats(name, data_path)
        lines.append(
            f"{name:<30} {s['count']:>6} "
            f"{s['mean']*1000:>9.2f} "
            f"{s['p50']*1000:>9.2f} "
            f"{s['p95']*1000:>9.2f} "
            f"{s['p99']*1000:>9.2f}"
        )
    return "\n".join(lines)
