"""Auto-update checker for the agency runtime.

Checks PyPI once per day; prints a Hebrew notice when a newer version exists.
Tracked in ~/.agency/update_check.json.
"""
from __future__ import annotations

import json
import pathlib
import time
import urllib.request
import urllib.error
from typing import Optional

_UPDATE_CHECK_FILE = pathlib.Path.home() / ".agency" / "update_check.json"
_PYPI_URL = "https://pypi.org/pypi/agency/json"
_PACKAGE_NAME = "agency"
_CHECK_INTERVAL = 86400  # 1 day in seconds

try:
    from importlib.metadata import version as _pkg_version
    CURRENT_VERSION: str = _pkg_version(_PACKAGE_NAME)
except Exception:
    CURRENT_VERSION = "0.0.0"


def _parse_version(v: str) -> tuple:
    """Convert 'X.Y.Z' to (X, Y, Z) tuple for comparison."""
    try:
        return tuple(int(x) for x in str(v).split(".")[:3])
    except Exception:
        return (0, 0, 0)


def fetch_latest_version(timeout: float = 2.0) -> Optional[str]:
    """Query PyPI for the latest published version. Returns None on any error."""
    try:
        req = urllib.request.Request(
            _PYPI_URL,
            headers={"User-Agent": "agency-updater/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["info"]["version"]
    except Exception:
        return None


def check_update(force: bool = False) -> Optional[str]:
    """Return a newer version string if available, else None.

    Respects the 24-hour cooldown unless *force* is True.
    """
    now = time.time()
    state: dict = {}

    if _UPDATE_CHECK_FILE.exists():
        try:
            state = json.loads(_UPDATE_CHECK_FILE.read_text(encoding="utf-8"))
        except Exception:
            state = {}

    last_check: float = float(state.get("last_check", 0))

    if not force and (now - last_check) < _CHECK_INTERVAL:
        # Use cached result
        cached = state.get("latest")
        if cached and _parse_version(cached) > _parse_version(CURRENT_VERSION):
            return str(cached)
        return None

    # Fetch fresh
    latest = fetch_latest_version()
    try:
        _UPDATE_CHECK_FILE.parent.mkdir(parents=True, exist_ok=True)
        _UPDATE_CHECK_FILE.write_text(
            json.dumps({"last_check": now, "latest": latest}),
            encoding="utf-8",
        )
    except Exception:
        pass

    if latest and _parse_version(latest) > _parse_version(CURRENT_VERSION):
        return str(latest)
    return None


def print_update_notice(version: str) -> None:
    """Print a Hebrew update notice to stdout."""
    print(
        f"\n\033[33m⚠️  גרסה חדשה זמינה: {version}"
        f" — הפעל `pip install --upgrade agency`\033[0m\n"
    )


def get_changelog_url() -> str:
    return "https://github.com/amjad/agency/blob/main/CHANGELOG.md"
