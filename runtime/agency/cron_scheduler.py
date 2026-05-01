"""Simple cron-like background scheduler using threading."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional


class CronScheduler:
    """Thread-based scheduler that runs jobs at fixed intervals."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------

    def add_job(self, name: str, interval_seconds: int, fn: Callable) -> None:
        """Register a named job. Overwrites an existing job with the same name."""
        with self._lock:
            self._jobs[name] = {
                "interval_s": interval_seconds,
                "fn": fn,
                "last_run": None,
                "enabled": True,
            }

    def remove_job(self, name: str) -> bool:
        """Remove a job by name. Returns True if it existed."""
        with self._lock:
            if name in self._jobs:
                del self._jobs[name]
                return True
            return False

    def list_jobs(self) -> list[dict]:
        """Return job metadata (without the callable)."""
        with self._lock:
            return [
                {
                    "name": name,
                    "interval_s": info["interval_s"],
                    "last_run": info["last_run"],
                    "enabled": info["enabled"],
                }
                for name, info in self._jobs.items()
            ]

    def run_now(self, name: str) -> bool:
        """Force immediate execution of a named job. Returns False if not found."""
        with self._lock:
            job = self._jobs.get(name)
        if job is None:
            return False
        try:
            job["fn"]()
            with self._lock:
                if name in self._jobs:
                    self._jobs[name]["last_run"] = time.time()
        except Exception:
            pass
        return True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background scheduler thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="cron-scheduler")
        self._thread.start()

    def stop(self) -> None:
        """Stop the scheduler and wait for the thread to exit."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while self._running:
            now = time.time()
            with self._lock:
                jobs_snapshot = list(self._jobs.items())
            for name, job in jobs_snapshot:
                if not job["enabled"]:
                    continue
                last = job["last_run"]
                if last is None or (now - last) >= job["interval_s"]:
                    try:
                        job["fn"]()
                    except Exception:
                        pass
                    with self._lock:
                        if name in self._jobs:
                            self._jobs[name]["last_run"] = time.time()
            time.sleep(0.1)
