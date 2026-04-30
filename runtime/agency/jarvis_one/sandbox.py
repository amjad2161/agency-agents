"""Sandbox — inspired by E2B.

Trust-gated subprocess sandbox for running short snippets of Python /
Bash / Node code. By default the sandbox is *dry-run only* — the trust
mode must be ``on-my-machine`` or ``yolo`` to actually execute. Output
is truncated to keep memory bounded.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..trust import TrustMode, current as _current_trust


SUPPORTED_LANGUAGES: tuple[str, ...] = ("python", "bash", "node")


@dataclass
class SandboxResult:
    language: str
    code: str
    executed: bool = False
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class Sandbox:
    """Disposable subprocess sandbox with trust gating + output caps."""

    def __init__(self, *, dry_run: bool | None = None,
                 timeout: float = 5.0, max_output: int = 8192) -> None:
        self.dry_run = (
            dry_run if dry_run is not None
            else _current_trust() is TrustMode.OFF
        )
        self.timeout = timeout
        self.max_output = max_output

    def run(self, language: str, code: str) -> SandboxResult:
        lang = language.lower()
        if lang not in SUPPORTED_LANGUAGES:
            return SandboxResult(
                language=lang, code=code,
                error=f"unsupported language: {lang!r}",
            )
        if self.dry_run:
            return SandboxResult(
                language=lang, code=code,
                error="sandbox is in dry-run mode (trust=off)",
            )
        return self._exec(lang, code)

    def _exec(self, lang: str, code: str) -> SandboxResult:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"snippet.{lang}"
            path.write_text(code, encoding="utf-8")
            argv = self._argv_for(lang, path)
            try:
                proc = subprocess.run(  # noqa: S603 — gated by trust
                    argv, capture_output=True, text=True,
                    timeout=self.timeout, check=False,
                    cwd=tmp, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                )
                return SandboxResult(
                    language=lang, code=code, executed=True,
                    returncode=proc.returncode,
                    stdout=proc.stdout[:self.max_output],
                    stderr=proc.stderr[:self.max_output],
                )
            except FileNotFoundError as exc:
                return SandboxResult(language=lang, code=code,
                                     error=f"interpreter missing: {exc}")
            except subprocess.TimeoutExpired:
                return SandboxResult(language=lang, code=code, executed=True,
                                     error=f"timeout after {self.timeout}s")

    @staticmethod
    def _argv_for(lang: str, path: Path) -> list[str]:
        if lang == "python":
            import sys
            return [sys.executable, str(path)]
        if lang == "bash":
            return ["/bin/bash", str(path)]
        if lang == "node":
            return ["node", str(path)]
        raise ValueError(lang)
