"""Token-bucket rate limiter, thread-safe, persisted to ~/.agency/rate_limit.json."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path


_DEFAULT_PATH = Path.home() / ".agency" / "rate_limit.json"
_WARN_THRESHOLD = 0.80  # warn when >80% of tokens consumed


class RateLimiter:
    """Token-bucket rate limiter.

    Tokens refill at *requests_per_minute* per 60-second window.
    State is persisted to *state_path* so restarts don't reset the bucket.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        state_path: Path | None = None,
    ) -> None:
        if requests_per_minute < 1:
            raise ValueError("requests_per_minute must be >= 1")
        self.capacity = float(requests_per_minute)
        self.refill_rate = self.capacity / 60.0  # tokens per second
        self._path = Path(state_path) if state_path else _DEFAULT_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._tokens, self._last_refill = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self) -> bool:
        """Consume one token and return True, or return False if bucket empty.

        Prints a Hebrew warning when >80 % of tokens have been consumed.
        """
        with self._lock:
            self._refill()
            if self._tokens < 1.0:
                return False
            self._tokens -= 1.0
            self._save()
            used_fraction = 1.0 - (self._tokens / self.capacity) if self.capacity > 0 else 1.0
            if used_fraction > _WARN_THRESHOLD:
                print("⚠️ מתקרב למגבלת הבקשות")  # noqa: T201
            return True

    def status(self) -> dict:
        """Return current bucket status."""
        with self._lock:
            self._refill()
            remaining = max(0.0, self._tokens)
            # seconds until next full refill from current level
            deficit = self.capacity - remaining
            reset_in_s = deficit / self.refill_rate if self.refill_rate > 0 else 0.0
            reset_at = time.time() + reset_in_s
        return {
            "tokens_remaining": int(remaining),
            "capacity": int(self.capacity),
            "reset_at": reset_at,
            "reset_in_seconds": round(reset_in_s, 1),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refill(self) -> None:
        now = time.time()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
        self._last_refill = now

    def _load(self) -> tuple[float, float]:
        """Load persisted state; fall back to a full bucket if absent/corrupt."""
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            tokens = float(data.get("tokens", self.capacity))
            last_refill = float(data.get("last_refill", time.time()))
            return tokens, last_refill
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            return self.capacity, time.time()

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps({"tokens": self._tokens, "last_refill": self._last_refill}),
                encoding="utf-8",
            )
        except OSError:
            pass  # non-fatal: in-memory state still works
