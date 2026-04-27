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

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(EXAMPLES / script), *args],
        capture_output=True, text=True, check=False, timeout=30,
        env={"PATH": ""},  # we want the script to use its installed agency package
    )


@pytest.mark.parametrize("script", [
    "01_list_skills.py",
    "02_route_a_request.py",
])
def test_offline_examples_exit_zero(script):
    """01 and 02 do not need an API key. They should exit 0 on the real registry."""
    import os

    # Inherit PATH/PYTHONPATH so the installed `agency` package is importable.
    proc = subprocess.run(
        [sys.executable, str(EXAMPLES / script)],
        capture_output=True, text=True, check=False, timeout=30,
        env={**os.environ, "ANTHROPIC_API_KEY": ""},  # ensure no key path
    )
    assert proc.returncode == 0, (
        f"{script} exited {proc.returncode}\n"
        f"stdout: {proc.stdout[:400]}\nstderr: {proc.stderr[:400]}"
    )


def test_offline_examples_have_expected_output():
    """Spot-check that the offline scripts actually print the kind of thing they claim to."""
    import os

    proc = subprocess.run(
        [sys.executable, str(EXAMPLES / "01_list_skills.py")],
        capture_output=True, text=True, check=False, timeout=30,
        env={**os.environ, "ANTHROPIC_API_KEY": ""},
    )
    assert "Loaded" in proc.stdout
    assert "skills across" in proc.stdout

    proc = subprocess.run(
        [sys.executable, str(EXAMPLES / "02_route_a_request.py"), "build a frontend"],
        capture_output=True, text=True, check=False, timeout=30,
        env={**os.environ, "ANTHROPIC_API_KEY": ""},
    )
    # Planner falls back to keyword match; output should mention reason / shortlist.
    assert "reason:" in proc.stdout
