"""Code execution sandbox.

Local subprocess backend with timeout + env sanitization. E2B cloud
backend is optional. This is intentionally a thin layer — the kernel
isolation, network policy, and FS scoping must come from the runtime
deploying the sandbox (container, micro-VM, etc.).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .logging import get_logger

log = get_logger()


# Env vars stripped before invoking sandboxed code. Keep API keys, AWS
# creds, GitHub tokens, etc. out of the child process.
_SENSITIVE_ENV_PREFIXES = (
    "AWS_",
    "AZURE_",
    "GCP_",
    "GOOGLE_",
    "GITHUB_",
    "GH_",
    "ANTHROPIC_",
    "OPENAI_",
    "HUGGINGFACE_",
    "HF_",
    "STRIPE_",
    "TWILIO_",
    "SENDGRID_",
    "DATABASE_",
    "DB_",
    "REDIS_",
    "POSTGRES_",
    "MYSQL_",
    "MONGO_",
    "SUPABASE_",
    "VERCEL_",
    "DOCKER_",
    "NPM_",
    "PYPI_",
)
_SENSITIVE_ENV_NAMES = {
    "API_KEY",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "TOKEN",
    "PRIVATE_KEY",
}


def _sanitized_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in os.environ.items():
        ku = k.upper()
        if any(ku.startswith(p) for p in _SENSITIVE_ENV_PREFIXES):
            continue
        if any(s in ku for s in _SENSITIVE_ENV_NAMES):
            continue
        out[k] = v
    return out


@dataclass
class SandboxResult:
    """Result of one sandboxed run."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_time: float = 0.0
    success: bool = False
    timed_out: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Sandbox:
    """Base class. Subclasses implement `_run`."""

    def execute_python(self, code: str, timeout: float = 30.0) -> SandboxResult:
        return self._run([sys.executable, "-c", code], timeout=timeout)

    def execute_bash(self, code: str, timeout: float = 30.0) -> SandboxResult:
        shell = shutil.which("bash") or shutil.which("sh")
        if shell is None:
            return SandboxResult(
                stderr="no shell available", exit_code=127, success=False
            )
        return self._run([shell, "-c", code], timeout=timeout)

    def execute_node(self, code: str, timeout: float = 30.0) -> SandboxResult:
        node = shutil.which("node")
        if node is None:
            return SandboxResult(
                stderr="node not installed", exit_code=127, success=False
            )
        return self._run([node, "-e", code], timeout=timeout)

    def execute_file(self, path: str, timeout: float = 30.0) -> SandboxResult:
        p = Path(path)
        if not p.exists():
            return SandboxResult(
                stderr=f"file not found: {path}", exit_code=2, success=False
            )
        suffix = p.suffix.lower()
        if suffix == ".py":
            return self._run([sys.executable, str(p)], timeout=timeout)
        if suffix in (".sh", ".bash"):
            shell = shutil.which("bash") or shutil.which("sh") or "/bin/sh"
            return self._run([shell, str(p)], timeout=timeout)
        if suffix == ".js":
            node = shutil.which("node") or "node"
            return self._run([node, str(p)], timeout=timeout)
        return SandboxResult(
            stderr=f"unsupported file type: {suffix}", exit_code=1, success=False
        )

    def _run(
        self, argv: list[str], timeout: float = 30.0, cwd: str | None = None
    ) -> SandboxResult:
        raise NotImplementedError


class SubprocessSandbox(Sandbox):
    """Local subprocess execution. NOT a true isolation boundary —
    relies on the host for kernel-level isolation."""

    def __init__(self, allow_network: bool = True, work_dir: str | None = None) -> None:
        self.allow_network = allow_network
        self.work_dir = work_dir

    def _run(
        self, argv: list[str], timeout: float = 30.0, cwd: str | None = None
    ) -> SandboxResult:
        env = _sanitized_env()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        if not self.allow_network:
            env["NO_NETWORK"] = "1"
        run_cwd = cwd or self.work_dir
        if run_cwd is None:
            run_cwd = tempfile.gettempdir()
        start = time.time()
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=run_cwd,
                check=False,
            )
            elapsed = time.time() - start
            return SandboxResult(
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                exit_code=proc.returncode,
                execution_time=elapsed,
                success=proc.returncode == 0,
                timed_out=False,
            )
        except subprocess.TimeoutExpired as e:
            return SandboxResult(
                stdout=e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or ""),
                stderr=(e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or ""))
                + f"\n[timeout after {timeout}s]",
                exit_code=124,
                execution_time=timeout,
                success=False,
                timed_out=True,
            )
        except FileNotFoundError as e:
            return SandboxResult(
                stderr=f"executable not found: {e}",
                exit_code=127,
                execution_time=time.time() - start,
                success=False,
            )
        except Exception as e:
            return SandboxResult(
                stderr=f"sandbox error: {e}",
                exit_code=1,
                execution_time=time.time() - start,
                success=False,
            )


class E2BSandbox(Sandbox):
    """E2B cloud micro-VM. Optional, requires `e2b` package."""

    def __init__(self, template: str | None = None) -> None:  # pragma: no cover
        try:
            from e2b import Sandbox as _E2BSandbox  # type: ignore

            self._sandbox = _E2BSandbox(template=template) if template else _E2BSandbox()
        except ImportError as e:
            raise RuntimeError(f"e2b not installed: {e}")

    def _run(
        self, argv: list[str], timeout: float = 30.0, cwd: str | None = None
    ) -> SandboxResult:  # pragma: no cover
        start = time.time()
        try:
            cmd = " ".join(argv)
            result = self._sandbox.commands.run(cmd, timeout=timeout, cwd=cwd)
            elapsed = time.time() - start
            return SandboxResult(
                stdout=getattr(result, "stdout", "") or "",
                stderr=getattr(result, "stderr", "") or "",
                exit_code=int(getattr(result, "exit_code", 0) or 0),
                execution_time=elapsed,
                success=int(getattr(result, "exit_code", 0) or 0) == 0,
            )
        except Exception as e:
            return SandboxResult(
                stderr=f"e2b error: {e}",
                exit_code=1,
                execution_time=time.time() - start,
                success=False,
            )


def get_sandbox(backend: str = "subprocess", **kwargs) -> Sandbox:
    """Factory. backend ∈ {subprocess, e2b}."""
    if backend == "subprocess":
        return SubprocessSandbox(**kwargs)
    if backend == "e2b":
        return E2BSandbox(**kwargs)  # pragma: no cover
    raise ValueError(f"unknown backend: {backend}")


__all__ = [
    "SandboxResult",
    "Sandbox",
    "SubprocessSandbox",
    "E2BSandbox",
    "get_sandbox",
]
