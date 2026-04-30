"""Pass-24 hot reload — watchdog/polling/mock file watcher.

Watches a directory tree for markdown changes and triggers a callback so
:class:`LocalSkillEngine` can hot-swap the registry. Falls back to a
polling implementation when the optional ``watchdog`` dep is unavailable.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable


@dataclass
class HotReloadConfig:
    paths: list[Path] = field(default_factory=list)
    patterns: tuple[str, ...] = ("*.md",)
    poll_interval: float = 1.0


class HotReloadWatcher:
    """Polling-first file watcher with optional watchdog acceleration."""

    def __init__(self, config: HotReloadConfig,
                 on_change: Callable[[Path], None]) -> None:
        self.config = config
        self.on_change = on_change
        self._snapshot: dict[Path, float] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def scan(self) -> dict[Path, float]:
        seen: dict[Path, float] = {}
        for root in self.config.paths:
            if not root.exists():
                continue
            for pattern in self.config.patterns:
                for path in root.rglob(pattern):
                    try:
                        seen[path] = path.stat().st_mtime
                    except OSError:
                        continue
        return seen

    def diff(self) -> Iterable[Path]:
        current = self.scan()
        changed: list[Path] = []
        for path, mtime in current.items():
            if self._snapshot.get(path) != mtime:
                changed.append(path)
        for path in self._snapshot:
            if path not in current:
                changed.append(path)
        self._snapshot = current
        return changed

    def start(self) -> None:
        if self._thread is not None:
            return
        # Prime snapshot so the first tick doesn't fire for every file.
        self._snapshot = self.scan()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self, *, timeout: float = 1.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None

    # ------------------------------------------------------------------
    def _loop(self) -> None:  # pragma: no cover — thread loop
        while not self._stop.is_set():
            for path in self.diff():
                try:
                    self.on_change(path)
                except Exception:  # noqa: BLE001 — never crash the watcher
                    continue
            self._stop.wait(self.config.poll_interval)
