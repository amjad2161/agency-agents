"""Token usage tracking for the agency runtime.

Every call to AnthropicLLM.messages_create() that returns a `usage`
field will update ~/.agency/stats.json with cumulative counts.

The `agency stats` CLI command reads and displays those totals.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def stats_path() -> Path:
    d = Path.home() / ".agency"
    d.mkdir(parents=True, exist_ok=True)
    return d / "stats.json"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

_LOCK = threading.Lock()

_ZERO_STATS: dict[str, Any] = {
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0,
    "total_calls": 0,
    "first_call": None,
    "last_call": None,
}


def _load_raw() -> dict[str, Any]:
    p = stats_path()
    if not p.exists():
        return dict(_ZERO_STATS)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return dict(_ZERO_STATS)
        # Ensure all keys present
        for k, v in _ZERO_STATS.items():
            data.setdefault(k, v)
        return data
    except (json.JSONDecodeError, OSError):
        return dict(_ZERO_STATS)


def _save_raw(data: dict[str, Any]) -> None:
    stats_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def record_usage(usage: Any) -> None:
    """Accumulate token usage from an Anthropic API response usage object.

    *usage* may be an SDK object with attributes or a plain dict.
    Fields: input_tokens, output_tokens, cache_creation_input_tokens,
            cache_read_input_tokens.
    """

    def _get(key: str) -> int:
        if isinstance(usage, dict):
            return int(usage.get(key) or 0)
        return int(getattr(usage, key, None) or 0)

    with _LOCK:
        data = _load_raw()
        data["input_tokens"] += _get("input_tokens")
        data["output_tokens"] += _get("output_tokens")
        data["cache_creation_input_tokens"] += _get("cache_creation_input_tokens")
        data["cache_read_input_tokens"] += _get("cache_read_input_tokens")
        data["total_calls"] += 1
        now = datetime.now(timezone.utc).isoformat()
        if data["first_call"] is None:
            data["first_call"] = now
        data["last_call"] = now
        _save_raw(data)


def get_stats() -> dict[str, Any]:
    """Return current cumulative stats as a plain dict."""
    with _LOCK:
        return _load_raw()


def reset_stats() -> None:
    """Zero out all stats (useful for testing)."""
    with _LOCK:
        _save_raw(dict(_ZERO_STATS))


def format_stats(data: dict[str, Any]) -> str:
    """Return a human-readable summary of *data*."""
    total_in = data.get("input_tokens", 0)
    total_out = data.get("output_tokens", 0)
    cache_w = data.get("cache_creation_input_tokens", 0)
    cache_r = data.get("cache_read_input_tokens", 0)
    calls = data.get("total_calls", 0)
    first = data.get("first_call") or "—"
    last = data.get("last_call") or "—"

    lines = [
        "=== Agency Token Stats ===",
        f"  total API calls    : {calls}",
        f"  input tokens       : {total_in:,}",
        f"  output tokens      : {total_out:,}",
        f"  cache write tokens : {cache_w:,}",
        f"  cache read tokens  : {cache_r:,}",
        f"  total tokens       : {total_in + total_out:,}",
        f"  first call         : {first}",
        f"  last call          : {last}",
    ]
    return "\n".join(lines)
