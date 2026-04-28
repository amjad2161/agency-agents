"""Process supervisor for the runtime.

Wraps `subprocess.Popen` with two real failure modes the agent's
self-heal loop cares about:

  - **timeout**: the subprocess runs longer than `timeout_s` (or hard-cap
    `AGENCY_PROCESS_HARD_TIMEOUT`, default 600s). We send SIGTERM, give
    it 2 seconds to clean up, then SIGKILL. The supervised result
    captures *what was on stdout/stderr at the moment we killed it* so
    the agent can read the partial output as a "crash dump."

  - **memory**: the subprocess RSS exceeds `mem_limit_mb`. Same
    SIGTERM → SIGKILL escalation.

The output of `run_supervised()` is always a `SupervisedResult` —
never a raised exception. The agent's executor reads `.killed_reason`
in the next turn and decides whether to retry, rewrite, or give up.
This is the "kernel-level self-heal" loop the user asked for: surface
*why* the process died, not just that it did.

Pure stdlib. Works on Linux, macOS, Windows (the memory monitor
degrades gracefully on platforms without psutil).
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Optional: psutil gives us per-process memory + CPU. Without it we
# still enforce the timeout and capture output, but mem_limit is silently
# ignored. The runtime's `[computer]` extra installs psutil; recommend
# users install it explicitly if they want the full picture.
try:
    import psutil  # type: ignore
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

HARD_TIMEOUT = float(os.environ.get("AGENCY_PROCESS_HARD_TIMEOUT", "600"))


@dataclass
class SupervisedResult:
    """Outcome of a supervised subprocess run.

    Always returned, never raised. `killed_reason` is None on a clean
    exit; otherwise one of: "timeout", "memory", "external_signal".
    """
    returncode: int
    stdout: str
    stderr: str
    elapsed_s: float
    killed_reason: str | None = None
    peak_rss_mb: float = 0.0
    crash_dump: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and self.killed_reason is None

    def as_dict(self) -> dict[str, Any]:
        return {
            "returncode": self.returncode,
            "stdout_tail": self.stdout[-2000:] if self.stdout else "",
            "stderr_tail": self.stderr[-2000:] if self.stderr else "",
            "elapsed_s": round(self.elapsed_s, 3),
            "killed_reason": self.killed_reason,
            "peak_rss_mb": round(self.peak_rss_mb, 1),
        }


def run_supervised(
    args: list[str] | str,
    *,
    timeout_s: float = 60.0,
    mem_limit_mb: float | None = None,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    shell: bool = False,
    stdin_text: str | None = None,
) -> SupervisedResult:
    """Spawn `args`, supervise it, return its outcome.

    Hard-caps `timeout_s` to `AGENCY_PROCESS_HARD_TIMEOUT` (default 600s)
    so a runaway agent can't accidentally pin a worker forever.

    `mem_limit_mb`: if set, the supervisor checks RSS every 0.5s and
    kills the process if it exceeds. Requires psutil.

    Output is captured into memory. If you expect more than ~100MB
    of output, redirect to a file in the command itself.
    """
    timeout = min(timeout_s, HARD_TIMEOUT)

    start = time.monotonic()
    proc = subprocess.Popen(
        args,
        cwd=cwd, env=env, shell=shell,
        stdin=subprocess.PIPE if stdin_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    # Send stdin (if any) right away so the subprocess can start producing.
    if stdin_text is not None and proc.stdin is not None:
        try:
            proc.stdin.write(stdin_text)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    # Streaming buffers — we don't wait for full output, we read as it
    # comes so even on a kill we have something to show the agent.
    stdout_buf: list[str] = []
    stderr_buf: list[str] = []

    def _drain(stream: Any, buf: list[str]) -> None:
        if stream is None:
            return
        try:
            for line in iter(stream.readline, ""):
                buf.append(line)
        except (ValueError, OSError):
            pass

    t_out = threading.Thread(target=_drain, args=(proc.stdout, stdout_buf), daemon=True)
    t_err = threading.Thread(target=_drain, args=(proc.stderr, stderr_buf), daemon=True)
    t_out.start(); t_err.start()

    # Memory probe (psutil)
    peak_rss = 0.0
    pu_proc = None
    if HAS_PSUTIL:
        try:
            pu_proc = psutil.Process(proc.pid)
        except Exception:  # noqa: BLE001 - process may have already exited
            pu_proc = None

    killed_reason: str | None = None
    while True:
        rc = proc.poll()
        if rc is not None:
            break
        elapsed = time.monotonic() - start

        if elapsed > timeout:
            killed_reason = "timeout"
            _terminate(proc)
            break

        if mem_limit_mb is not None and pu_proc is not None:
            try:
                rss_mb = pu_proc.memory_info().rss / (1024 * 1024)
                if rss_mb > peak_rss:
                    peak_rss = rss_mb
                if rss_mb > mem_limit_mb:
                    killed_reason = "memory"
                    _terminate(proc)
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pu_proc = None

        time.sleep(0.05)

    t_out.join(timeout=2.0)
    t_err.join(timeout=2.0)
    elapsed = time.monotonic() - start
    rc = proc.returncode if proc.returncode is not None else -1

    stdout = "".join(stdout_buf)
    stderr = "".join(stderr_buf)

    crash_dump = ""
    if killed_reason:
        crash_dump = (
            f"=== process killed by supervisor: {killed_reason} ===\n"
            f"command: {args!r}\n"
            f"elapsed: {elapsed:.2f}s (limit: {timeout:.2f}s)\n"
            f"peak rss: {peak_rss:.1f} MB"
            + (f" (limit: {mem_limit_mb:.1f} MB)" if mem_limit_mb else "")
            + "\n--- stdout tail (last 2 KB) ---\n"
            + stdout[-2000:]
            + "\n--- stderr tail (last 2 KB) ---\n"
            + stderr[-2000:]
        )

    return SupervisedResult(
        returncode=rc,
        stdout=stdout,
        stderr=stderr,
        elapsed_s=elapsed,
        killed_reason=killed_reason,
        peak_rss_mb=peak_rss,
        crash_dump=crash_dump,
    )


def _terminate(proc: subprocess.Popen) -> None:
    """SIGTERM, wait 2s, SIGKILL. Cross-platform."""
    try:
        if os.name == "nt":
            proc.terminate()
        else:
            proc.send_signal(signal.SIGTERM)
    except (ProcessLookupError, OSError):
        return
    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except (ProcessLookupError, OSError):
            return
        try:
            proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            pass


# ----- helpers for the agent's self-heal loop ----------------------

def crash_message(result: SupervisedResult, original_command: str) -> str:
    """Format a SupervisedResult as a tool-result message that the
    next LLM turn can read and reason about."""
    if result.ok:
        return result.stdout + (
            ("\n[stderr]\n" + result.stderr) if result.stderr else ""
        )
    if result.killed_reason:
        return result.crash_dump
    # Non-zero exit, not killed → just include exit + tails.
    return (
        f"=== command failed: exit {result.returncode} ===\n"
        f"command: {original_command}\n"
        f"elapsed: {result.elapsed_s:.2f}s\n"
        f"--- stdout tail ---\n{result.stdout[-2000:]}\n"
        f"--- stderr tail ---\n{result.stderr[-2000:]}\n"
    )
