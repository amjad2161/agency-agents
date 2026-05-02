"""Smoke-tests for the offline example scripts (no API key required).

These don't validate output deeply — they just confirm the scripts import
cleanly, that import paths haven't drifted, and that the offline-safe ones
exit 0 on a real registry.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

RUNTIME_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = RUNTIME_ROOT / "examples"


def _example_env() -> dict[str, str]:
    """Build subprocess env with `agency` package importable from runtime/."""
    import os

    existing = os.environ.get("PYTHONPATH", "")
    pypath = str(RUNTIME_ROOT) + (os.pathsep + existing if existing else "")
    return {
        **os.environ,
        "PYTHONPATH": pypath,
        "ANTHROPIC_API_KEY": "",  # ensure no key path
    }


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(EXAMPLES / script), *args],
        capture_output=True, text=True, check=False, timeout=30,
        env=_example_env(),
    )


@pytest.mark.parametrize("script", [
    "01_list_skills.py",
    "02_route_a_request.py",
])
def test_offline_examples_exit_zero(script):
    """01 and 02 do not need an API key. They should exit 0 on the real registry."""
    proc = subprocess.run(
        [sys.executable, str(EXAMPLES / script)],
        capture_output=True, text=True, check=False, timeout=30,
        env=_example_env(),
    )
    assert proc.returncode == 0, (
        f"{script} exited {proc.returncode}\n"
        f"stdout: {proc.stdout[:400]}\nstderr: {proc.stderr[:400]}"
    )


def test_offline_examples_have_expected_output():
    """Spot-check that the offline scripts actually print the kind of thing they claim to."""
    proc = subprocess.run(
        [sys.executable, str(EXAMPLES / "01_list_skills.py")],
        capture_output=True, text=True, check=False, timeout=30,
        env=_example_env(),
    )
    assert "Loaded" in proc.stdout
    assert "skills across" in proc.stdout

    proc = subprocess.run(
        [sys.executable, str(EXAMPLES / "02_route_a_request.py"), "build a frontend"],
        capture_output=True, text=True, check=False, timeout=30,
        env=_example_env(),
    )
    # Planner falls back to keyword match; output should mention reason / shortlist.
    assert "reason:" in proc.stdout
