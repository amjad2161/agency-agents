"""Local OS bridge (Tier 5).

Trust-gated wrappers around mouse/keyboard/file/process operations. Every
side-effecting call routes through :class:`LocalOS.guard` which consults
the existing :mod:`agency.trust` policy. By default everything runs in a
deterministic dry-run mode so tests don't touch the host machine.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..trust import TrustMode, current as _current_trust


@dataclass
class OSAction:
    kind: str
    detail: dict[str, Any] = field(default_factory=dict)
    allowed: bool = False
    executed: bool = False
    result: Any = None


class LocalOS:
    """OS automation surface that respects the trust policy."""

    def __init__(self, *, dry_run: bool | None = None) -> None:
        # Default to dry-run unless trust mode explicitly allows side effects.
        self.dry_run = (
            dry_run if dry_run is not None
            else _current_trust() is TrustMode.OFF
        )

    # ------------------------------------------------------------------
    def guard(self, kind: str, **detail: Any) -> OSAction:
        action = OSAction(kind=kind, detail=detail)
        action.allowed = (
            _current_trust() in (TrustMode.ON_MY_MACHINE, TrustMode.YOLO)
            and not self.dry_run
        )
        return action

    # ------------------------------------------------------------------ files
    def list_dir(self, path: str | Path) -> list[str]:
        p = Path(path).expanduser()
        if not p.exists() or not p.is_dir():
            return []
        return sorted(child.name for child in p.iterdir())

    def read_file(self, path: str | Path, *, max_bytes: int = 65_536) -> str:
        p = Path(path).expanduser()
        return p.read_text(encoding="utf-8", errors="replace")[:max_bytes]

    def write_file(self, path: str | Path, content: str) -> OSAction:
        action = self.guard("write_file", path=str(path), bytes=len(content))
        if action.allowed:
            p = Path(path).expanduser()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            action.executed = True
            action.result = str(p)
        return action

    # ------------------------------------------------------------------ process
    def run(self, argv: list[str], *, timeout: float = 15.0) -> OSAction:
        action = self.guard("run", argv=list(argv))
        if not action.allowed:
            return action
        try:
            proc = subprocess.run(  # noqa: S603 — gated by trust policy
                argv, capture_output=True, text=True, timeout=timeout, check=False,
            )
            action.executed = True
            action.result = {
                "returncode": proc.returncode,
                "stdout": proc.stdout[:4096],
                "stderr": proc.stderr[:4096],
            }
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            action.result = {"error": f"{type(exc).__name__}: {exc}"}
        return action

    # ------------------------------------------------------------------ mouse / keyboard (mocked)
    def mouse(self, *, x: int, y: int, button: str = "left") -> OSAction:
        return self.guard("mouse", x=x, y=y, button=button)

    def keyboard(self, text: str) -> OSAction:
        return self.guard("keyboard", chars=len(text))

    # ------------------------------------------------------------------ env
    def health(self) -> dict[str, Any]:
        return {
            "trust_mode": _current_trust().value,
            "dry_run": self.dry_run,
            "shell": shutil.which(os.environ.get("SHELL", "bash") or "bash") or "n/a",
        }
