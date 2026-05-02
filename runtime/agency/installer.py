"""JARVIS One-click capability installer — Pass 20.

Detects which optional dependencies are installed and provides
``pip install`` helpers for each capability group.

Capabilities
------------
    robotics   — pybullet, mujoco
    vision     — ultralytics (YOLO), opencv-python
    voice      — openai-whisper, sounddevice, pyttsx3
    rl         — stable-baselines3, gymnasium
    browser    — playwright
    core       — anthropic, fastapi, flask, click (always required)

CLI
---
    agency install [--all] [--robotics] [--vision] [--voice] [--rl]
    agency capabilities   — table of what's available vs missing
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Capability descriptors
# ---------------------------------------------------------------------------

@dataclass
class Capability:
    """Describes one optional capability and its required packages."""
    name: str
    description: str
    packages: List[str]
    check_imports: List[str] = field(default_factory=list)
    installed: Optional[bool] = None     # populated by detect()

    def detect(self) -> bool:
        """Return True if *all* check_imports can be imported."""
        for mod in self.check_imports:
            try:
                __import__(mod)
            except ImportError:
                self.installed = False
                return False
        self.installed = True
        return True


# Registry of known capabilities
CAPABILITIES: Dict[str, Capability] = {
    "core": Capability(
        name="core",
        description="Core runtime (Anthropic SDK, FastAPI, Flask, Click)",
        packages=["anthropic", "fastapi", "flask", "click", "uvicorn"],
        check_imports=["anthropic", "fastapi", "flask", "click"],
    ),
    "robotics": Capability(
        name="robotics",
        description="Physics simulation (PyBullet / MuJoCo)",
        packages=["pybullet", "mujoco"],
        check_imports=["pybullet"],
    ),
    "vision": Capability(
        name="vision",
        description="YOLO object detection (Ultralytics) + OpenCV",
        packages=["ultralytics", "opencv-python"],
        check_imports=["ultralytics", "cv2"],
    ),
    "voice": Capability(
        name="voice",
        description="Speech recognition (Whisper) + TTS (pyttsx3)",
        packages=["openai-whisper", "sounddevice", "pyttsx3"],
        check_imports=["whisper", "pyttsx3"],
    ),
    "rl": Capability(
        name="rl",
        description="Reinforcement learning (Stable-Baselines3 + Gymnasium)",
        packages=["stable-baselines3", "gymnasium"],
        check_imports=["stable_baselines3", "gymnasium"],
    ),
    "browser": Capability(
        name="browser",
        description="Browser automation (Playwright)",
        packages=["playwright"],
        check_imports=["playwright"],
    ),
    "torch": Capability(
        name="torch",
        description="PyTorch deep-learning framework",
        packages=["torch"],
        check_imports=["torch"],
    ),
}


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_capabilities() -> Dict[str, bool]:
    """Return a dict mapping capability name → installed bool."""
    return {name: cap.detect() for name, cap in CAPABILITIES.items()}


def detect_windows_capabilities() -> Dict[str, bool]:
    """Alias kept for Windows-specific naming in spec."""
    return detect_capabilities()


def capability_table() -> List[Dict[str, str]]:
    """Return a list of rows for display, with status emoji."""
    rows = []
    for name, cap in CAPABILITIES.items():
        installed = cap.detect()
        rows.append({
            "name": name,
            "description": cap.description,
            "status": "✅  installed" if installed else "❌  missing",
            "packages": ", ".join(cap.packages),
        })
    return rows


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------

def install_capability(name: str, quiet: bool = False) -> bool:
    """Install packages for *name* via pip.  Returns True on success."""
    if name not in CAPABILITIES:
        print(f"Unknown capability: {name!r}. "
              f"Available: {', '.join(CAPABILITIES)}")
        return False

    cap = CAPABILITIES[name]

    # Skip if already installed
    if cap.detect():
        if not quiet:
            print(f"[JARVIS] ✅  {name} already installed — skipping")
        return True

    if not quiet:
        print(f"[JARVIS] Installing {name}: {', '.join(cap.packages)}")

    cmd = [sys.executable, "-m", "pip", "install"] + cap.packages
    if quiet:
        cmd += ["-q"]

    result = subprocess.run(cmd, capture_output=quiet)
    success = result.returncode == 0

    if not quiet:
        if success:
            print(f"[JARVIS] ✅  {name} installed successfully")
        else:
            print(f"[JARVIS] ❌  {name} installation failed")
            if result.stderr:
                print(result.stderr.decode(errors="ignore")[:300])

    return success


def install_all(quiet: bool = False) -> Dict[str, bool]:
    """Install every capability.  Returns map of name → success."""
    results = {}
    for name in CAPABILITIES:
        results[name] = install_capability(name, quiet=quiet)
    return results


# ---------------------------------------------------------------------------
# Pretty-print helpers
# ---------------------------------------------------------------------------

def print_capability_table() -> None:
    """Print a formatted table of capability status."""
    rows = capability_table()
    name_w  = max(len(r["name"]) for r in rows) + 2
    desc_w  = max(len(r["description"]) for r in rows) + 2
    stat_w  = 16

    header = (f"{'Capability':<{name_w}}  "
              f"{'Description':<{desc_w}}  "
              f"{'Status':<{stat_w}}")
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)
    for r in rows:
        print(f"{r['name']:<{name_w}}  "
              f"{r['description']:<{desc_w}}  "
              f"{r['status']:<{stat_w}}")
    print(sep)
