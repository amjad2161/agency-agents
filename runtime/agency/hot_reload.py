"""
hot_reload.py — JARVIS Pass 24
Watches source files for changes and reloads modules automatically.
Uses watchdog if available, falls back to mtime polling.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import shutil
import sys
import threading
import time
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Optional watchdog
# ---------------------------------------------------------------------------
try:
    from watchdog.observers import Observer  # type: ignore
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent  # type: ignore
    _HAS_WATCHDOG = True
except ImportError:
    _HAS_WATCHDOG = False
    Observer = None  # type: ignore
    FileSystemEventHandler = object  # type: ignore


# ---------------------------------------------------------------------------
# PollingWatcher — 2-second mtime check
# ---------------------------------------------------------------------------

class _PollingWatcher:
    def __init__(self, paths: list[str], callback: Callable[[str], None]):
        self._paths = paths
        self._callback = callback
        self._mtimes: dict[str, float] = {}
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="HotReload-Poll")

    def start(self) -> None:
        self._snapshot()
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=5)

    def _snapshot(self) -> None:
        for root_path in self._paths:
            for filepath in self._iter_py_files(root_path):
                try:
                    self._mtimes[filepath] = os.path.getmtime(filepath)
                except OSError:
                    pass

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=2.0)
            if self._stop_event.is_set():
                break
            self._check()

    def _check(self) -> None:
        for root_path in self._paths:
            for filepath in self._iter_py_files(root_path):
                try:
                    mtime = os.path.getmtime(filepath)
                except OSError:
                    continue
                old = self._mtimes.get(filepath)
                if old is None or mtime > old:
                    self._mtimes[filepath] = mtime
                    try:
                        self._callback(filepath)
                    except Exception:
                        pass

    @staticmethod
    def _iter_py_files(root: str):
        if os.path.isfile(root):
            if root.endswith(".py"):
                yield root
            return
        for dirpath, _dirs, files in os.walk(root):
            for fname in files:
                if fname.endswith(".py"):
                    yield os.path.join(dirpath, fname)


# ---------------------------------------------------------------------------
# WatchdogWatcher — wraps watchdog Observer
# ---------------------------------------------------------------------------

if _HAS_WATCHDOG:
    class _WatchdogHandler(FileSystemEventHandler):  # type: ignore[misc]
        def __init__(self, callback: Callable[[str], None]):
            super().__init__()
            self._callback = callback

        def on_modified(self, event):  # type: ignore[override]
            if not event.is_directory and event.src_path.endswith(".py"):
                try:
                    self._callback(event.src_path)
                except Exception:
                    pass

    class _WatchdogWatcher:
        def __init__(self, paths: list[str], callback: Callable[[str], None]):
            self._handler = _WatchdogHandler(callback)
            self._observer = Observer()
            for p in paths:
                watch_dir = p if os.path.isdir(p) else os.path.dirname(p)
                self._observer.schedule(self._handler, watch_dir, recursive=True)

        def start(self) -> None:
            self._observer.start()

        def stop(self) -> None:
            if self._observer.is_alive():
                self._observer.stop()
                self._observer.join(timeout=5)

else:
    _WatchdogWatcher = None  # type: ignore


# ---------------------------------------------------------------------------
# MockWatcher — no-op (for tests / when no FS watching is desired)
# ---------------------------------------------------------------------------

class MockWatcher:
    def __init__(self, paths: list[str] = (), callback: Callable | None = None):
        pass

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


# ---------------------------------------------------------------------------
# HotReloader
# ---------------------------------------------------------------------------

class HotReloader:
    """
    Watches a list of file/directory paths for changes.
    On change: invalidates __pycache__, reloads via importlib, calls callback.
    """

    def __init__(self, *, use_mock: bool = False):
        self._watcher = None
        self._callback: Optional[Callable[[str], None]] = None
        self._use_mock = use_mock
        self._running = False

    # ------------------------------------------------------------------
    def watch(self, paths: list[str], callback: Callable[[str], None]) -> None:
        """Start watching. Idempotent — stops previous watcher first."""
        self.stop()
        self._callback = callback

        if self._use_mock:
            self._watcher = MockWatcher(paths, callback)
        elif _HAS_WATCHDOG and _WatchdogWatcher is not None:
            self._watcher = _WatchdogWatcher(paths, self._on_change)
        else:
            self._watcher = _PollingWatcher(paths, self._on_change)

        self._watcher.start()
        self._running = True

    def stop(self) -> None:
        """Stop watching.  Safe to call multiple times."""
        if self._watcher is not None:
            try:
                self._watcher.stop()
            except Exception:
                pass
            self._watcher = None
        self._running = False

    def reload_module(self, module_name: str) -> bool:
        """
        Reload a module by dotted name.
        Returns True on success, False on failure.
        """
        try:
            self._invalidate_pycache(module_name)
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
            else:
                importlib.import_module(module_name)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_change(self, changed_path: str) -> None:
        """Called by the watcher backend when a file changes."""
        # Derive module name from path
        module_name = self._path_to_module(changed_path)
        if module_name:
            self.reload_module(module_name)

        # Notify caller
        if self._callback is not None:
            try:
                self._callback(changed_path)
            except Exception:
                pass

    @staticmethod
    def _path_to_module(path: str) -> str:
        """Convert a file path to a dotted module name (best-effort)."""
        path = os.path.abspath(path)
        # Try to find in sys.path
        for sp in sorted(sys.path, key=len, reverse=True):
            if path.startswith(sp + os.sep):
                rel = path[len(sp) + 1:]
                module = rel.replace(os.sep, ".").removesuffix(".py")
                return module
        return ""

    @staticmethod
    def _invalidate_pycache(module_name: str) -> None:
        """Remove compiled .pyc for a module if it exists."""
        try:
            spec = importlib.util.find_spec(module_name)
            if spec and spec.origin:
                src = spec.origin
                cache = importlib.util.cache_from_source(src)
                if os.path.exists(cache):
                    os.remove(cache)
                # Also try removing the __pycache__ dir for the module
                cache_dir = os.path.dirname(cache)
                stem = os.path.splitext(os.path.basename(src))[0]
                for fname in os.listdir(cache_dir):
                    if fname.startswith(stem + "."):
                        try:
                            os.remove(os.path.join(cache_dir, fname))
                        except OSError:
                            pass
        except Exception:
            pass
