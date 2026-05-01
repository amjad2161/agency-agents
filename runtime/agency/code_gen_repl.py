"""Code generation and safe execution REPL.

Generates Python code from plain-English descriptions using simple
template-based rules (no LLM required), then executes it in an isolated
subprocess with a configurable timeout.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any


class CodeGenREPL:
    """Generate and safely execute Python code snippets."""

    def __init__(self, sandbox: bool = True) -> None:
        self.sandbox = sandbox
        self._history: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Code generation
    # ------------------------------------------------------------------

    def generate(self, description: str) -> str:
        """Generate Python code from a plain-English description.

        Recognises the following patterns (case-insensitive):
        - "print <text>"         → print statement
        - "calculate <expr>"     → arithmetic eval + print
        - "list files in <path>" → os.listdir snippet
        - "fibonacci <n>"        → iterative Fibonacci
        Returns a Python code string that can be passed to execute().
        """
        desc = description.strip()
        lower = desc.lower()

        # --- print ---
        m = re.match(r"print\s+(.+)", desc, re.IGNORECASE)
        if m:
            text = m.group(1).strip().strip("\"'")
            return f'print("{text}")\n'

        # --- calculate ---
        m = re.match(r"calculate\s+(.+)", desc, re.IGNORECASE)
        if m:
            expr = m.group(1).strip()
            return (
                f"result = {expr}\n"
                f"print(result)\n"
            )

        # --- list files ---
        m = re.match(r"list\s+files\s+in\s+(.+)", desc, re.IGNORECASE)
        if m:
            path = m.group(1).strip().strip("\"'")
            return (
                f"import os\n"
                f"files = os.listdir({path!r})\n"
                f"for f in sorted(files):\n"
                f"    print(f)\n"
            )

        # --- fibonacci ---
        m = re.match(r"fibonacci\s+(\d+)", desc, re.IGNORECASE)
        if m:
            n = int(m.group(1))
            return (
                f"def fibonacci(n):\n"
                f"    a, b = 0, 1\n"
                f"    for _ in range(n):\n"
                f"        a, b = b, a + b\n"
                f"    return a\n"
                f"\n"
                f"print(fibonacci({n}))\n"
            )

        # --- fallback: wrap as comment + identity print ---
        safe_desc = desc.replace('"', '\\"')
        return f'# {safe_desc}\nprint("Generated: {safe_desc}")\n'

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, code: str, timeout_s: int = 5) -> dict[str, Any]:
        """Execute *code* in a subprocess and return a result dict.

        Never uses exec() — always spawns a fresh Python interpreter for
        isolation.  Returns::

            {stdout, stderr, returncode, elapsed_s}
        """
        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            elapsed = time.monotonic() - t0
            return {
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "returncode": proc.returncode,
                "elapsed_s": elapsed,
            }
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - t0
            return {
                "stdout": "",
                "stderr": f"TimeoutExpired: execution exceeded {timeout_s}s",
                "returncode": -1,
                "elapsed_s": elapsed,
            }
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - t0
            return {
                "stdout": "",
                "stderr": str(exc),
                "returncode": -2,
                "elapsed_s": elapsed,
            }

    # ------------------------------------------------------------------
    # Combined
    # ------------------------------------------------------------------

    def generate_and_run(self, description: str, timeout_s: int = 5) -> dict[str, Any]:
        """Generate code from *description*, execute it, return combined dict."""
        code = self.generate(description)
        result = self.execute(code, timeout_s=timeout_s)
        entry = {
            "description": description,
            "code": code,
            "result": result,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self._history.append(entry)
        return entry

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def history(self, n: int = 10) -> list[dict[str, Any]]:
        """Return the last *n* history entries (newest first)."""
        return list(reversed(self._history[-n:]))

    def clear_history(self) -> None:
        """Erase all history entries."""
        self._history.clear()
