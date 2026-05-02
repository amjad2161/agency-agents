"""Smoke tests for the top-level `jarvis_os/` package.

These don't exercise Tk / pystray / keyboard at runtime — they just ensure
each module parses and (for the platform-agnostic ones) imports cleanly so
regressions surface in CI even without a display, tray, or keyboard hook.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
JARVIS_OS = REPO_ROOT / "jarvis_os"

MODULES = [
    "native_chat.py",
    "tray.py",
    "hotkey_listener.py",
    "__init__.py",
]


@pytest.mark.parametrize("name", MODULES)
def test_jarvis_os_module_parses(name: str) -> None:
    """Each jarvis_os module must be syntactically valid Python."""
    path = JARVIS_OS / name
    assert path.exists(), f"missing {path}"
    src = path.read_text(encoding="utf-8")
    ast.parse(src, filename=str(path))


def test_jarvis_os_package_importable() -> None:
    """The package itself must import without optional GUI/system deps."""
    sys.path.insert(0, str(REPO_ROOT))
    try:
        if "jarvis_os" in sys.modules:
            del sys.modules["jarvis_os"]
        import jarvis_os  # noqa: F401
    finally:
        sys.path.remove(str(REPO_ROOT))
