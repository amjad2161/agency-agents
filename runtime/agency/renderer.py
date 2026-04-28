"""Markdown renderer for terminal output.

Uses ``rich`` when available; falls back to a regex-based ANSI renderer.
"""
from __future__ import annotations

import importlib.util
import re


def _ansi(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m"


def _fallback_render(text: str) -> str:
    """Basic regex ANSI renderer — no external deps."""
    lines = text.split("\n")
    out: list[str] = []
    in_code = False
    for line in lines:
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            out.append("    " + line)
            continue
        # Headers
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            level = len(m.group(1))
            title = m.group(2)
            if level == 1:
                out.append(_ansi("1;4", title))
            elif level == 2:
                out.append(_ansi("1", title))
            else:
                out.append(_ansi("4", title))
            continue
        # Bold **text**
        line = re.sub(r"\*\*(.+?)\*\*", lambda mo: _ansi("1", mo.group(1)), line)
        # Italic *text*
        line = re.sub(r"\*(.+?)\*", lambda mo: _ansi("3", mo.group(1)), line)
        # Inline code `text`
        line = re.sub(r"`(.+?)`", lambda mo: _ansi("7", mo.group(1)), line)
        out.append(line)
    return "\n".join(out)


def render_markdown(text: str) -> str:
    """Render *text* as markdown to a terminal string.

    Prefers ``rich`` when installed; falls back to the regex renderer.
    """
    if importlib.util.find_spec("rich") is not None:
        try:
            import io
            from rich.console import Console
            from rich.markdown import Markdown

            buf = io.StringIO()
            console = Console(file=buf, highlight=False, markup=False, width=120)
            console.print(Markdown(text))
            result = buf.getvalue()
            # Strip trailing blank lines added by rich
            return result.rstrip("\n") + "\n"
        except Exception:
            pass
    return _fallback_render(text)
