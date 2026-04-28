"""Export chat sessions to Markdown, HTML, or JSON.

Usage:
    agency export                     # export most recent session as MD
    agency export <session_id>        # export specific session
    agency export --format html       # HTML with bubble styling
    agency export --format json       # raw JSON
    agency export --output ~/Desktop/chat.md
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from .history import history_dir, list_sessions, read_session

ExportFormat = Literal["md", "html", "json"]


# ---------------------------------------------------------------------------
# Format renderers
# ---------------------------------------------------------------------------

def _to_markdown(session_id: str, messages: list[dict]) -> str:
    lines = [f"## Session: {session_id}", ""]
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        ts = msg.get("timestamp", "")[:19]
        label = "**User**" if role == "user" else "**JARVIS**"
        lines.append(f"{label} _{ts}_")
        lines.append("")
        lines.append(content)
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def _to_html(session_id: str, messages: list[dict]) -> str:
    def _esc(s: str) -> str:
        return (s.replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;")
                 .replace("\n", "<br>"))

    bubble_rows: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        ts = msg.get("timestamp", "")[:19]
        if role == "user":
            bubble_rows.append(
                f'<div class="msg user">'
                f'<span class="label">You</span>'
                f'<span class="ts">{_esc(ts)}</span>'
                f'<div class="bubble">{_esc(content)}</div>'
                f'</div>'
            )
        else:
            bubble_rows.append(
                f'<div class="msg jarvis">'
                f'<span class="label">JARVIS</span>'
                f'<span class="ts">{_esc(ts)}</span>'
                f'<div class="bubble">{_esc(content)}</div>'
                f'</div>'
            )

    css = """
body { font-family: system-ui, sans-serif; max-width: 800px; margin: 40px auto;
       background: #0d0d0d; color: #e0e0e0; }
h1 { color: #00e5ff; }
.msg { margin: 16px 0; }
.label { font-weight: bold; margin-right: 8px; }
.ts { font-size: 0.75em; color: #888; }
.bubble { margin-top: 6px; padding: 10px 14px; border-radius: 8px;
          white-space: pre-wrap; line-height: 1.5; }
.user .bubble { background: #1a2a3a; border-left: 3px solid #00bcd4; }
.jarvis .bubble { background: #1a1a2e; border-left: 3px solid #7c4dff; }
"""

    rows_html = "\n".join(bubble_rows)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>JARVIS Chat — {_esc(session_id)}</title>
<style>{css}</style>
</head>
<body>
<h1>JARVIS Chat Export</h1>
<p><strong>Session:</strong> {_esc(session_id)}</p>
<hr>
{rows_html}
</body>
</html>"""


def _to_json(session_id: str, messages: list[dict]) -> str:
    payload = {"session_id": session_id, "messages": messages}
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_session(
    session_id: str | None = None,
    fmt: ExportFormat = "md",
    output_path: Path | None = None,
) -> Path:
    """Export a chat session to the given format.

    Parameters
    ----------
    session_id:
        Stem of the session file (e.g. ``2025-01-15_143022``).
        If None, the most recent session is used.
    fmt:
        Output format: ``md``, ``html``, or ``json``.
    output_path:
        Where to write the file.  Defaults to ``~/Desktop/<session_id>.<ext>``.

    Returns
    -------
    Path
        The path of the written file.
    """
    # Resolve session file
    if session_id:
        candidate = history_dir() / f"{session_id}.jsonl"
        if not candidate.exists():
            raise FileNotFoundError(f"Session not found: {candidate}")
        session_file = candidate
        sid = session_id
    else:
        sessions = list_sessions(limit=1)
        if not sessions:
            raise FileNotFoundError("No chat sessions found in ~/.agency/history/")
        session_file = sessions[0]
        sid = session_file.stem

    messages = read_session(session_file)

    # Render
    if fmt == "html":
        content = _to_html(sid, messages)
        ext = "html"
    elif fmt == "json":
        content = _to_json(sid, messages)
        ext = "json"
    else:
        content = _to_markdown(sid, messages)
        ext = "md"

    # Determine output path
    if output_path is None:
        desktop = Path.home() / "Desktop"
        desktop.mkdir(parents=True, exist_ok=True)
        output_path = desktop / f"{sid}.{ext}"

    output_path.write_text(content, encoding="utf-8")
    return output_path


def list_exportable_sessions(limit: int = 20) -> list[tuple[str, int]]:
    """Return [(session_id, message_count), ...] for the most recent sessions."""
    result: list[tuple[str, int]] = []
    for p in list_sessions(limit=limit):
        msgs = read_session(p)
        result.append((p.stem, len(msgs)))
    return result
