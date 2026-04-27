"""Terminal UI — JarvisConsole with Rich-when-available, plain fallback.

If `rich` is importable, the console renders spinners, colored status
lines, formatted tables, and live token streams. Otherwise it falls
back to plain prints so behavior is identical in CI and headless runs.
"""

from __future__ import annotations

import contextlib
import io
import logging
import sys
import time
from typing import Any, Iterable, Iterator

try:
    from rich.console import Console as _RichConsole  # type: ignore
    from rich.live import Live as _RichLive  # type: ignore
    from rich.spinner import Spinner as _RichSpinner  # type: ignore
    from rich.table import Table as _RichTable  # type: ignore
    from rich.text import Text as _RichText  # type: ignore

    _HAS_RICH = True
except ImportError:  # pragma: no cover
    _HAS_RICH = False
    _RichConsole = None  # type: ignore
    _RichLive = None  # type: ignore
    _RichSpinner = None  # type: ignore
    _RichTable = None  # type: ignore
    _RichText = None  # type: ignore


class JarvisConsole:
    """Console wrapper. Pass `force_plain=True` to bypass Rich for tests."""

    def __init__(
        self,
        force_plain: bool = False,
        file=None,
    ) -> None:
        self.force_plain = force_plain
        self._file = file or sys.stdout
        self._rich = None
        if not force_plain and _HAS_RICH:
            self._rich = _RichConsole(file=self._file, force_terminal=False)

    @property
    def has_rich(self) -> bool:
        return self._rich is not None

    def _write(self, msg: str) -> None:
        try:
            self._file.write(msg + "\n")
            self._file.flush()
        except Exception:
            pass

    @contextlib.contextmanager
    def thinking(self, message: str = "thinking") -> Iterator[None]:
        if self._rich is not None:
            spinner = _RichSpinner("dots", text=message)
            with _RichLive(spinner, console=self._rich, refresh_per_second=10, transient=True):
                yield
            return
        self._write(f"… {message}")
        try:
            yield
        finally:
            self._write(f"✓ {message}")

    def success(self, message: str) -> None:
        if self._rich is not None:
            self._rich.print(f"[bold green]✓[/bold green] {message}")
        else:
            self._write(f"[OK] {message}")

    def error(self, message: str) -> None:
        if self._rich is not None:
            self._rich.print(f"[bold red]✗[/bold red] {message}")
        else:
            self._write(f"[ERR] {message}")

    def warn(self, message: str) -> None:
        if self._rich is not None:
            self._rich.print(f"[bold yellow]![/bold yellow] {message}")
        else:
            self._write(f"[WARN] {message}")

    def info(self, message: str) -> None:
        if self._rich is not None:
            self._rich.print(f"[cyan]·[/cyan] {message}")
        else:
            self._write(f"[INFO] {message}")

    def print_plan(self, steps: Iterable[str]) -> None:
        steps_list = list(steps)
        if self._rich is not None:
            from rich.markdown import Markdown  # type: ignore

            md = "## Plan\n\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(steps_list, 1))
            self._rich.print(Markdown(md))
        else:
            self._write("Plan:")
            for i, s in enumerate(steps_list, 1):
                self._write(f"  {i}. {s}")

    def agent_status_table(self, agents: list[dict[str, Any]]) -> str:
        """Render an agent status table. Returns the rendered string."""
        if self._rich is not None:
            table = _RichTable(title="Agents")
            cols = ["name", "status", "queue", "last"]
            if agents:
                for c in agents[0].keys():
                    if c not in cols:
                        cols.append(c)
            for c in cols:
                table.add_column(c)
            for a in agents:
                table.add_row(*[str(a.get(c, "")) for c in cols])
            buf = io.StringIO()
            tmp = _RichConsole(file=buf, force_terminal=False, width=120)
            tmp.print(table)
            out = buf.getvalue()
            self._rich.print(table)
            return out
        # plain fallback
        if not agents:
            self._write("(no agents)")
            return "(no agents)\n"
        cols = list(agents[0].keys())
        rows = [" | ".join(cols)]
        rows.append("-" * len(rows[0]))
        for a in agents:
            rows.append(" | ".join(str(a.get(c, "")) for c in cols))
        rendered = "\n".join(rows)
        self._write(rendered)
        return rendered + "\n"

    def stream_tokens(self, token_iterator: Iterable[str]) -> str:
        """Print tokens as they arrive. Returns the assembled string."""
        parts: list[str] = []
        if self._rich is not None:
            with _RichLive("", console=self._rich, refresh_per_second=20, transient=False) as live:
                for tok in token_iterator:
                    parts.append(tok)
                    live.update(_RichText("".join(parts)))
            return "".join(parts)
        for tok in token_iterator:
            parts.append(tok)
            try:
                self._file.write(tok)
                self._file.flush()
            except Exception:
                pass
        try:
            self._file.write("\n")
            self._file.flush()
        except Exception:
            pass
        return "".join(parts)


class RichLoggingHandler(logging.Handler):
    """Logging handler that writes through a JarvisConsole."""

    def __init__(self, console: JarvisConsole | None = None) -> None:
        super().__init__()
        self.console = console or JarvisConsole()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()
        if record.levelno >= logging.ERROR:
            self.console.error(msg)
        elif record.levelno >= logging.WARNING:
            self.console.warn(msg)
        elif record.levelno >= logging.INFO:
            self.console.info(msg)
        else:
            self.console._write(msg)


_console: JarvisConsole | None = None


def get_console(force_plain: bool = False) -> JarvisConsole:
    global _console
    if _console is None:
        _console = JarvisConsole(force_plain=force_plain)
    return _console


def reset_console() -> None:
    """Test helper."""
    global _console
    _console = None


__all__ = [
    "JarvisConsole",
    "RichLoggingHandler",
    "get_console",
    "reset_console",
]
