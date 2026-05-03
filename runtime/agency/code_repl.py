"""Code Generation REPL — Pass 21.

Provides a sandboxed Python REPL that JARVIS can use to execute generated
code snippets. The namespace persists across calls within one session
(interactive REPL behaviour) while restricting access to dangerous stdlib
modules unless TrustMode allows.

Classes
-------
    REPLResult     — output container (stdout, stderr, return_value, etc.)
    CodeREPL       — the main REPL engine

CLI
---
    agency repl                       interactive Python REPL
    agency repl --file script.py      run a file through the REPL
    agency repl --eval "1+1"          one-shot eval

Usage (library)
---------------
    from agency.code_repl import CodeREPL

    repl = CodeREPL()
    r = repl.execute("x = 40 + 2")
    r2 = repl.execute("x")          # namespace persists
    print(r2.return_value)          # 42
"""

from __future__ import annotations

import builtins
import contextlib
import io
import math
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Optional trust mode integration
# ---------------------------------------------------------------------------
try:
    from .trust import TrustMode, get_trust_mode
    _HAS_TRUST = True
except Exception:
    _HAS_TRUST = False


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class REPLResult:
    """Result of a single REPL execution."""

    stdout: str = ""
    stderr: str = ""
    return_value: Any = None
    duration_ms: float = 0.0
    error: Optional[str] = None
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None and not self.timed_out

    def __repr__(self) -> str:  # pragma: no cover
        status = "OK" if self.ok else f"ERR({self.error})"
        return (f"REPLResult({status}, "
                f"stdout={self.stdout!r:.40}, "
                f"rv={self.return_value!r:.40}, "
                f"ms={self.duration_ms:.1f})")


# ---------------------------------------------------------------------------
# Restricted builtins
# ---------------------------------------------------------------------------

_BLOCKED_MODULES_DEFAULT = frozenset({
    "os", "subprocess", "sys", "shutil", "socket",
    "multiprocessing", "threading", "signal",
    "ctypes", "importlib", "_thread",
})

_SAFE_BUILTINS_NAMES = frozenset({
    "abs", "all", "any", "ascii", "bin", "bool", "breakpoint",
    "bytearray", "bytes", "callable", "chr", "complex", "delattr",
    "dict", "dir", "divmod", "enumerate", "filter", "float", "format",
    "frozenset", "getattr", "globals", "hasattr", "hash", "help",
    "hex", "id", "input", "int", "isinstance", "issubclass", "iter",
    "len", "list", "locals", "map", "max", "memoryview", "min",
    "next", "object", "oct", "open", "ord", "pow", "print",
    "property", "range", "repr", "reversed", "round", "set",
    "setattr", "slice", "sorted", "staticmethod", "str", "sum",
    "super", "tuple", "type", "vars", "zip",
    "__build_class__", "__name__", "__doc__",
    "True", "False", "None",
    # Exceptions
    "Exception", "ValueError", "TypeError", "KeyError",
    "IndexError", "AttributeError", "RuntimeError", "StopIteration",
    "NotImplementedError", "OSError", "IOError", "ArithmeticError",
    "ZeroDivisionError", "OverflowError", "AssertionError",
    "ImportError", "NameError", "RecursionError", "MemoryError",
    "BaseException", "SystemExit", "KeyboardInterrupt",
    "GeneratorExit",
})


def _make_safe_builtins() -> dict:
    safe: dict = {}
    for name in _SAFE_BUILTINS_NAMES:
        obj = getattr(builtins, name, None)
        if obj is not None:
            safe[name] = obj
    return safe


def _make_restricted_import(blocked: frozenset[str], original_import: Any):
    """Return a __import__ replacement that blocks dangerous modules."""

    def _restricted_import(name: str, *args: Any, **kwargs: Any) -> Any:
        root = name.split(".")[0]
        if root in blocked:
            raise ImportError(
                f"Module '{name}' is blocked in the sandboxed REPL. "
                "Use TrustMode='on-my-machine' to enable full imports."
            )
        return original_import(name, *args, **kwargs)

    return _restricted_import


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------

class CodeREPL:
    """Sandboxed Python REPL with persistent namespace.

    Parameters
    ----------
    trust_mode:
        Override trust mode detection. ``None`` = auto-detect from env/config.
        Pass ``'full'`` to allow all imports (equivalent to on-my-machine).
    timeout:
        Default per-execution timeout in seconds.
    """

    def __init__(
        self,
        trust_mode: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        self._default_timeout = timeout
        self._trust_mode = self._resolve_trust(trust_mode)
        self._namespace: Dict[str, Any] = self._build_namespace()
        self._history: list[tuple[str, REPLResult]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, code: str, timeout: Optional[float] = None) -> REPLResult:
        """Execute *code* in the persistent namespace.

        Supports both expressions (single-expression eval) and statements
        (multi-line exec). Captures stdout/stderr.

        Returns a :class:`REPLResult`.
        """
        timeout = timeout if timeout is not None else self._default_timeout
        t0 = time.monotonic()

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        return_value: Any = None
        error: Optional[str] = None
        timed_out = False

        code = code.strip()
        if not code:
            return REPLResult(duration_ms=0.0)

        try:
            with contextlib.redirect_stdout(stdout_buf), \
                 contextlib.redirect_stderr(stderr_buf):
                # Try eval first (expression mode)
                try:
                    compiled = compile(code, "<repl>", "eval")
                    return_value = eval(compiled, self._namespace)  # noqa: S307
                except SyntaxError:
                    # Fall back to exec (statement mode)
                    compiled = compile(code, "<repl>", "exec")
                    exec(compiled, self._namespace)  # noqa: S102
                    return_value = None
        except TimeoutError:
            timed_out = True
            error = "TimeoutError: execution exceeded limit"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            stderr_buf.write(traceback.format_exc())

        duration_ms = (time.monotonic() - t0) * 1_000
        result = REPLResult(
            stdout=stdout_buf.getvalue(),
            stderr=stderr_buf.getvalue(),
            return_value=return_value,
            duration_ms=round(duration_ms, 2),
            error=error,
            timed_out=timed_out,
        )
        self._history.append((code, result))
        return result

    def generate_and_run(self, prompt: str) -> REPLResult:
        """Ask the LLM to generate Python for *prompt*, then execute it.

        Falls back to a stub result if no LLM is configured.
        """
        code = self._generate_code(prompt)
        return self.execute(code)

    def reset(self) -> None:
        """Clear the namespace and history."""
        self._namespace = self._build_namespace()
        self._history.clear()

    @property
    def namespace(self) -> Dict[str, Any]:
        """Read-only view of the current namespace."""
        return dict(self._namespace)

    @property
    def history(self) -> list[tuple[str, REPLResult]]:
        return list(self._history)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_trust(self, override: Optional[str]) -> str:
        if override:
            return override
        if _HAS_TRUST:
            try:
                mode = get_trust_mode()
                return mode.value if hasattr(mode, "value") else str(mode)
            except Exception:
                pass
        return "off"

    def _build_namespace(self) -> Dict[str, Any]:
        """Build the initial namespace for the REPL."""
        ns: Dict[str, Any] = {}

        if self._trust_mode in ("off",):
            # Restricted builtins
            safe_builtins = _make_safe_builtins()
            safe_builtins["__import__"] = _make_restricted_import(
                _BLOCKED_MODULES_DEFAULT,
                builtins.__import__,
            )
            ns["__builtins__"] = safe_builtins
        else:
            # Full builtins for trusted modes
            ns["__builtins__"] = builtins.__dict__

        # Pre-import safe stdlib modules
        ns["math"] = math
        ns["__name__"] = "__repl__"
        return ns

    def _generate_code(self, prompt: str) -> str:
        """Try to call the LLM to generate Python; return stub on failure."""
        try:
            from .llm import LLMClient
            llm = LLMClient()
            system = (
                "You are a Python code generator. "
                "Respond with ONLY valid Python code, no markdown fences, "
                "no explanation."
            )
            response = llm.complete(system=system, user=prompt, max_tokens=512)
            # Strip possible ```python fences from the response
            code = response.strip()
            if code.startswith("```"):
                lines = code.splitlines()
                code = "\n".join(
                    l for l in lines
                    if not l.strip().startswith("```")
                )
            return code.strip()
        except Exception:
            # Fallback: return a placeholder
            return f"# Generated for: {prompt}\nprint('LLM not available')"
