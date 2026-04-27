"""Working-context manager.

Domain-scoped key/value store with TTL semantics. Used by the CLI
`context` command and by long-running reasoning loops to remember
intermediate state without bloating the LLM prompt.

Design notes:
  - Domains are flat namespaces (one level). Cross-domain keys are
    independent — `store("token", x, "gh")` and `store("token", y, "aws")`
    don't collide.
  - TTL is *evaluated lazily*: an expired entry is still in memory
    until you try to read or list it. We don't run a background sweep
    because the runtime tries to avoid daemons.
  - Storage is in-memory only. Tasks that need durability should reach
    for `self_learner_engine` or `knowledge_expansion`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterator


_DEFAULT_TTL_SECONDS = 3600  # 1h


@dataclass(frozen=True)
class ContextEntry:
    """One stored value. Immutable — overwriting creates a new entry."""

    key: str
    value: Any
    domain: str
    created_at: float
    ttl_seconds: int

    def is_expired(self, *, now: float | None = None) -> bool:
        if self.ttl_seconds <= 0:
            return False  # 0 / negative ttl means "never expire"
        if now is None:
            now = time.time()
        return (now - self.created_at) > self.ttl_seconds

    def age_seconds(self, *, now: float | None = None) -> float:
        if now is None:
            now = time.time()
        return max(0.0, now - self.created_at)


class ContextManager:
    """Domain-scoped, TTL-aware in-memory key/value store."""

    def __init__(self) -> None:
        # {domain: {key: ContextEntry}}
        self._store: dict[str, dict[str, ContextEntry]] = {}
        # Insertion order for recall_recent — Python dicts preserve it,
        # but we materialize it into a list per-domain so an overwrite
        # bumps the entry to the back of the queue.
        self._order: dict[str, list[str]] = {}

    # ----- write side -----

    def store(
        self,
        key: str,
        value: Any,
        *,
        domain: str = "default",
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> ContextEntry:
        if not key:
            raise ValueError("key must not be empty")
        if not domain:
            raise ValueError("domain must not be empty")
        entry = ContextEntry(
            key=key,
            value=value,
            domain=domain,
            created_at=time.time(),
            ttl_seconds=ttl_seconds,
        )
        d = self._store.setdefault(domain, {})
        d[key] = entry
        order = self._order.setdefault(domain, [])
        # Promote / append.
        if key in order:
            order.remove(key)
        order.append(key)
        return entry

    def forget(self, key: str, *, domain: str = "default") -> bool:
        d = self._store.get(domain)
        if not d or key not in d:
            return False
        del d[key]
        if domain in self._order and key in self._order[domain]:
            self._order[domain].remove(key)
        return True

    def clear_domain(self, domain: str) -> int:
        d = self._store.pop(domain, {})
        self._order.pop(domain, None)
        return len(d)

    # ----- read side -----

    def recall(self, key: str, *, domain: str = "default") -> Any | None:
        """Return the value or None if missing/expired. Expired entries
        are evicted as a side-effect of recall."""
        d = self._store.get(domain)
        if not d:
            return None
        entry = d.get(key)
        if entry is None:
            return None
        if entry.is_expired():
            self.forget(key, domain=domain)
            return None
        return entry.value

    def recall_entry(
        self, key: str, *, domain: str = "default"
    ) -> ContextEntry | None:
        d = self._store.get(domain)
        if not d:
            return None
        entry = d.get(key)
        if entry is None or entry.is_expired():
            if entry is not None:
                self.forget(key, domain=domain)
            return None
        return entry

    def recall_recent(
        self, *, domain: str = "default", n: int = 5
    ) -> list[ContextEntry]:
        """Return the `n` most recent live entries from `domain`,
        newest first. Expired entries are evicted on the way."""
        order = self._order.get(domain, [])
        d = self._store.get(domain, {})
        out: list[ContextEntry] = []
        for key in reversed(order):
            entry = d.get(key)
            if entry is None:
                continue
            if entry.is_expired():
                self.forget(key, domain=domain)
                continue
            out.append(entry)
            if len(out) >= n:
                break
        return out

    def all_domains(self) -> list[str]:
        return [d for d, m in self._store.items() if m]

    def dump_domain(self, domain: str) -> dict[str, Any]:
        """Plain `{key: value}` mapping for `domain`, expired entries
        evicted. Mostly useful for CLI listings and tests."""
        d = self._store.get(domain, {})
        out: dict[str, Any] = {}
        # Iterate over a snapshot since we may mutate during expiry.
        for key in list(d.keys()):
            entry = d[key]
            if entry.is_expired():
                self.forget(key, domain=domain)
                continue
            out[key] = entry.value
        return out

    def __iter__(self) -> Iterator[str]:
        return iter(self.all_domains())

    def __len__(self) -> int:
        return sum(len(self.dump_domain(d)) for d in list(self._store.keys()))
