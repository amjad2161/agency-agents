"""Terminal renderer: markdown, tables, code blocks — rich first, ANSI fallback."""

from __future__ import annotations

import re


def _rich_available() -> bool:
    try:
        import rich  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def render_markdown(text: str) -> str:
    """Render *text* as Markdown in the terminal.

    Uses ``rich`` when installed; falls back to a lightweight ANSI pass
    that handles headings, bold, italic, inline code, and code fences.
    """
    if _rich_available():
        from io import StringIO
        from rich.console import Console
        from rich.markdown import Markdown

        buf = StringIO()
        console = Console(file=buf, highlight=False)
        console.print(Markdown(text))
        return buf.getvalue()

    return _ansi_markdown(text)


def _ansi_markdown(text: str) -> str:
    """Minimal ANSI-escape Markdown renderer (no external deps)."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    ITALIC = "\033[3m"
    CODE_BG = "\033[7m"  # reverse video for inline code
    DIM = "\033[2m"

    lines = text.splitlines()
    out: list[str] = []
    in_fence = False

    for line in lines:
        # Code fence toggle
        if line.strip().startswith("```"):
            in_fence = not in_fence
            out.append(f"{DIM}{line}{RESET}")
            continue
        if in_fence:
            out.append(f"{DIM}{line}{RESET}")
            continue

        # ATX headings
        heading_match = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2)
            prefix = "#" * level + " "
            out.append(f"{BOLD}{prefix}{title}{RESET}")
            continue

        # Inline transforms
        line = re.sub(r"\*\*(.+?)\*\*", rf"{BOLD}\1{RESET}", line)
        line = re.sub(r"__(.+?)__", rf"{BOLD}\1{RESET}", line)
        line = re.sub(r"\*(.+?)\*", rf"{ITALIC}\1{RESET}", line)
        line = re.sub(r"_(.+?)_", rf"{ITALIC}\1{RESET}", line)
        line = re.sub(r"`(.+?)`", rf"{CODE_BG}\1{RESET}", line)

        out.append(line)

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def render_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a table.  Uses ``rich`` when available, else ASCII art."""
    if _rich_available():
        from io import StringIO
        from rich.console import Console
        from rich.table import Table

        buf = StringIO()
        console = Console(file=buf, highlight=False)
        table = Table(*headers, show_header=True, header_style="bold")
        for row in rows:
            table.add_row(*[str(c) for c in row])
        console.print(table)
        return buf.getvalue()

    return _ascii_table(headers, rows)


def _ascii_table(headers: list[str], rows: list[list[str]]) -> str:
    all_rows = [headers] + [[str(c) for c in row] for row in rows]
    col_widths = [
        max(len(str(r[i])) for r in all_rows if i < len(r))
        for i in range(len(headers))
    ]
    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"

    def _fmt_row(row: list[str]) -> str:
        cells = [f" {str(c).ljust(col_widths[i])} " for i, c in enumerate(row)]
        return "|" + "|".join(cells) + "|"

    lines = [sep, _fmt_row(headers), sep]
    for row in rows:
        lines.append(_fmt_row(row))
    lines.append(sep)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Code blocks
# ---------------------------------------------------------------------------

def render_code(code: str, language: str = "python") -> str:
    """Render a code block with syntax highlighting if rich is available."""
    if _rich_available():
        from io import StringIO
        from rich.console import Console
        from rich.syntax import Syntax

        buf = StringIO()
        console = Console(file=buf, highlight=False)
        syntax = Syntax(code, language, theme="monokai", line_numbers=False)
        console.print(syntax)
        return buf.getvalue()

    DIM = "\033[2m"
    RESET = "\033[0m"
    return f"{DIM}```{language}\n{code}\n```{RESET}"
