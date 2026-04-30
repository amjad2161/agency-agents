"""Terminal UI — inspired by Rich.

ANSI-coloured tables, panels, and progress hints. Pure-Python; no Rich
dependency. Used by the JARVIS One CLI for the ``agency map``,
``agency singularity --check``, and dashboard banner output.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from typing import Iterable


def _stdout_isatty() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


# Disable colour entirely when output is piped or NO_COLOR is set.
_NO_COLOR = bool(os.environ.get("NO_COLOR")) or not _stdout_isatty()


_COLORS = {
    "reset":   "\033[0m",
    "bold":    "\033[1m",
    "dim":     "\033[2m",
    "red":     "\033[31m",
    "green":   "\033[32m",
    "yellow":  "\033[33m",
    "blue":    "\033[34m",
    "magenta": "\033[35m",
    "cyan":    "\033[36m",
    "white":   "\033[37m",
}


def style(text: str, *, fg: str | None = None, bold: bool = False,
          dim: bool = False) -> str:
    """Wrap *text* with ANSI escape codes (no-op when output is piped)."""
    if _NO_COLOR or (not fg and not bold and not dim):
        return text
    parts: list[str] = []
    if bold:
        parts.append(_COLORS["bold"])
    if dim:
        parts.append(_COLORS["dim"])
    if fg and fg in _COLORS:
        parts.append(_COLORS[fg])
    return f"{''.join(parts)}{text}{_COLORS['reset']}"


@dataclass
class Table:
    title: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)

    def add_row(self, *cells: str) -> None:
        self.rows.append([str(c) for c in cells])

    def render(self) -> str:
        widths = [
            max(len(self.columns[i]) if i < len(self.columns) else 0,
                *(len(row[i]) for row in self.rows if i < len(row)))
            for i in range(len(self.columns) or
                           (max((len(r) for r in self.rows), default=0)))
        ]
        sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
        out: list[str] = []
        if self.title:
            out.append(style(self.title, bold=True))
        out.append(sep)
        if self.columns:
            header = "| " + " | ".join(
                style(c.ljust(widths[i]), bold=True)
                for i, c in enumerate(self.columns)
            ) + " |"
            out.append(header)
            out.append(sep)
        for row in self.rows:
            cells = [str(c) for c in row]
            cells += [""] * (len(widths) - len(cells))
            out.append(
                "| " + " | ".join(c.ljust(widths[i]) for i, c in enumerate(cells))
                + " |"
            )
        out.append(sep)
        return "\n".join(out)


def panel(text: str, *, title: str = "", fg: str = "cyan") -> str:
    width = min(shutil.get_terminal_size((80, 20)).columns, 100)
    border = style("=" * width, fg=fg)
    out: list[str] = [border]
    if title:
        out.append(style(f"  {title}", fg=fg, bold=True))
        out.append(border)
    for line in text.splitlines():
        out.append(line)
    out.append(border)
    return "\n".join(out)


def render_categories(by_category: dict[str, int]) -> str:
    table = Table(title="JARVIS Skill Map", columns=["Category", "Count"])
    total = 0
    for cat, count in sorted(by_category.items()):
        table.add_row(cat, str(count))
        total += count
    table.add_row("TOTAL", str(total))
    return table.render()


def render_personas(catalog: Iterable[dict]) -> str:
    table = Table(
        title="Senior Expert Personas",
        columns=["Slug", "Name", "Role", "Lang", "Domains"],
    )
    for p in catalog:
        table.add_row(p["slug"], p["display_name"], p["role"],
                      p["language"], str(p["domain_count"]))
    return table.render()
