"""Client-side token-bucket rate limiter for the Agency runtime.

Self-imposes 60 requests/minute so we don't hammer the Anthropic API.
Bucket state is persisted to ~/.agency/rate_state.json so the limit
is respected across multiple CLI invocations in the same minute.
"""

from __future__ import annotations

import json
import time
import threading
from pathlib import Path


# ---------------------------------------------------------------------------
# Path helper
# ---------------------------------------------------------------------------

def rate_state_path() -> Path:
    d = Path.home() / ".agency"
    d.mkdir(parents=True, exist_ok=True)
    return d / "rate_state.json"


# ---------------------------------------------------------------------------
# TokenBucket
# ---------------------------------------------------------------------------

class TokenBucket:
    """Thread-safe token-bucket rate limiter with file-backed persistence.

    Parameters
    ----------
    max_tokens:
        Maximum bucket capacity (and initial fill level).  Default 60.
    refill_rate:
        Tokens added per second.  Default 1.0 (60 tokens/minute).
    state_path:
        Where to persist bucket state between process invocations.
        Defaults to ~/.agency/rate_state.json.
    """

    def __init__(
        self,
        max_tokens: float = 60.0,
        refill_rate: float = 1.0,
        state_path: Path | None = None,
    ) -> None:
        self.max_tokens = float(max_tokens)
        self.refill_rate = float(refill_rate)
        self._path = state_path or rate_state_path()
        self._lock = threading.Lock()
        self._tokens, self._last_refill = self._load_state()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> tuple[float, float]:
        """Load (tokens, last_refill_timestamp) from disk; fill to max if absent."""
        try:
            if self._path.exists():
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                tokens = float(raw.get("tokens", self.max_tokens))
                last_refill = float(raw.get("last_refill", time.monotonic()))
                # Clamp to valid range
                tokens = max(0.0, min(self.max_tokens, tokens))
                return tokens, last_refill
        except (json.JSONDecodeError, OSError, ValueError, KeyError):
            pass
        return self.max_tokens, time.monotonic()

    def _save_state(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps({"tokens": self._tokens, "last_refill": self._last_refill},
                           indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Core mechanics
    # ------------------------------------------------------------------

    def _refill(self) -> None:
        """Refill tokens based on elapsed wall-clock time (call with lock held)."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed > 0:
            gained = elapsed * self.refill_rate
            self._tokens = min(self.max_tokens, self._tokens + gained)
            self._last_refill = now

    def get_level(self) -> float:
        """Return current token count after refill (does NOT consume)."""
        with self._lock:
            self._refill()
            self._save_state()
            return self._tokens

    def consume(self, tokens: float = 1.0) -> bool:
        """Try to consume *tokens* from the bucket.

        Returns True if successful, False if the bucket is empty.
        Does NOT block — use wait_for_token() for blocking behaviour.
        """
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                self._save_state()
                return True
            return False

    def wait_for_token(self, tokens: float = 1.0) -> None:
        """Block until *tokens* are available, then consume them.

        Prints a Hebrew warning when it has to wait so the operator
        knows the self-imposed limit is being hit.
        """
        warned = False
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    self._save_state()
                    return
                wait_secs = (tokens - self._tokens) / self.refill_rate
            if not warned:
                print(
                    f"⚠️  מגבלת קצב: ממתין {wait_secs:.1f} שניות לפני הבקשה הבאה…",
                    flush=True,
                )
                warned = True
            time.sleep(min(0.1, wait_secs))

    def reset(self) -> None:
        """Fill the bucket to max and save state (useful for testing)."""
        with self._lock:
            self._tokens = self.max_tokens
            self._last_refill = time.monotonic()
            self._save_state()


# ---------------------------------------------------------------------------
# Module-level singleton (used by CLI)
# ---------------------------------------------------------------------------

_bucket: TokenBucket | None = None


def get_bucket() -> TokenBucket:
    """Return the shared module-level TokenBucket instance."""
    global _bucket
    if _bucket is None:
        _bucket = TokenBucket()
    return _bucket


def reset_bucket() -> None:
    """Reset the module-level singleton (testing helper)."""
    global _bucket
    _bucket = TokenBucket()
    _bucket.reset()
