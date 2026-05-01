"""Auto-update checker: compare installed version against PyPI once per day."""

from __future__ import annotations

import json
import time
from pathlib import Path


_CACHE_PATH = Path.home() / ".agency" / "update_check.json"
_PYPI_URL = "https://pypi.org/pypi/agency-runtime/json"
_ONE_DAY = 86_400  # seconds


def get_current_version() -> str:
    """Read the package version from pyproject.toml or fall back to __version__."""
    # Walk up from this file to find pyproject.toml
    here = Path(__file__).resolve()
    for parent in [here.parent, here.parent.parent, here.parent.parent.parent]:
        candidate = parent / "pyproject.toml"
        if candidate.exists():
            text = candidate.read_text(encoding="utf-8")
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("version"):
                    # version = "0.1.0"  or  version="0.1.0"
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        return parts[1].strip().strip('"').strip("'")
    # Fallback: use the package __version__
    try:
        from . import __version__
        return __version__
    except (ImportError, AttributeError):
        return "0.0.0"


def check_for_updates(cache_path: Path | None = None) -> dict:
    """Check PyPI for the latest version of *agency-runtime*.

    Caches result for 24 hours to avoid hammering PyPI.
    Returns a dict with keys: current, latest, update_available, message.
    """
    path = Path(cache_path) if cache_path else _CACHE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    current = get_current_version()

    # Try to load cached result
    cached = _load_cache(path)
    if cached and (time.time() - cached.get("checked_at", 0)) < _ONE_DAY:
        return _build_result(current, cached["latest"])

    # Fetch from PyPI
    latest = _fetch_latest_pypi()
    _save_cache(path, latest)
    return _build_result(current, latest)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_latest_pypi() -> str:
    """Fetch latest version string from PyPI; return current on failure."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(_PYPI_URL, timeout=5) as resp:  # noqa: S310
            data = json.loads(resp.read())
            return data["info"]["version"]
    except (urllib.error.URLError, KeyError, json.JSONDecodeError, OSError):
        return get_current_version()


def _load_cache(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_cache(path: Path, latest: str) -> None:
    try:
        path.write_text(
            json.dumps({"latest": latest, "checked_at": time.time()}),
            encoding="utf-8",
        )
    except OSError:
        pass


def _build_result(current: str, latest: str) -> dict:
    update_available = _version_gt(latest, current)
    message = "🚀 גרסה חדשה זמינה!" if update_available else "You are up to date."
    return {
        "current": current,
        "latest": latest,
        "update_available": update_available,
        "message": message,
    }


def _version_gt(v1: str, v2: str) -> bool:
    """Return True if v1 is strictly greater than v2 using tuple comparison."""
    def _parts(v: str) -> tuple[int, ...]:
        try:
            return tuple(int(x) for x in v.split(".")[:3])
        except ValueError:
            return (0,)

    return _parts(v1) > _parts(v2)
