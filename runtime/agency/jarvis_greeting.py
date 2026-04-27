"""JARVIS Greeting Module — startup banner and farewell messages.

Generates the console greeting shown when JARVIS boots, including
subsystem health status. Also provides contextual farewell lines.

Usage::

    from agency.jarvis_greeting import get_startup_banner, get_farewell
    print(get_startup_banner({"systems_ok": 12, "systems_total": 12}))
    print(get_farewell())
"""

from __future__ import annotations

import datetime
from typing import Any

from .jarvis_soul import JARVIS_SOUL

# Box drawing characters (Unicode)
_TL = "╔"
_TR = "╗"
_BL = "╚"
_BR = "╝"
_H = "═"
_V = "║"

_WIDTH = 50  # Inner content width (between the borders)


def _box_line(content: str, width: int = _WIDTH) -> str:
    """Return a single bordered line, content centred/left-padded."""
    # Pad content to width
    padded = f"  {content}"
    if len(padded) < width:
        padded = padded + " " * (width - len(padded))
    else:
        padded = padded[:width]
    return f"{_V}{padded}{_V}"


def _top_border(width: int = _WIDTH) -> str:
    return _TL + _H * width + _TR


def _bot_border(width: int = _WIDTH) -> str:
    return _BL + _H * width + _BR


def _separator(width: int = _WIDTH) -> str:
    return "╠" + _H * width + "╣"


def get_startup_banner(status: dict[str, Any] | None = None) -> str:
    """Return a multi-line JARVIS startup banner string.

    Parameters
    ----------
    status:
        Optional dict with keys:
        - ``"mode"``         : current persona mode (str)
        - ``"systems_ok"``   : count of healthy subsystems (int)
        - ``"systems_total"``  : total subsystem count (int)
        - ``"subsystems"``   : dict of name → {"healthy": bool} (optional)

    Returns
    -------
    str
        Multi-line banner string suitable for ``print()``.
    """
    status = status or {}
    mode = status.get("mode", "supreme_brainiac")
    systems_ok = status.get("systems_ok", 0)
    systems_total = status.get("systems_total", systems_ok)
    subsystems: dict[str, Any] = status.get("subsystems", {})

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = [_top_border()]
    lines.append(_box_line(f"J.A.R.V.I.S — Supreme Brainiac Active"))
    lines.append(_box_line(f"Just A Rather Very Intelligent System"))
    lines.append(_separator())
    lines.append(_box_line(f"Owner  : {JARVIS_SOUL['owner']}"))
    lines.append(_box_line(f"Mode   : {mode}"))
    lines.append(_box_line(f"Systems: {systems_ok}/{systems_total} online"))
    lines.append(_box_line(f"Time   : {now}"))

    if subsystems:
        lines.append(_separator())
        for name, info in list(subsystems.items())[:8]:  # cap at 8 lines
            healthy = info.get("healthy", False)
            marker = "✓" if healthy else "✗"
            detail = info.get("detail", "")
            entry = f"  [{marker}] {name:<20} {detail}"
            if len(entry) > _WIDTH:
                entry = entry[: _WIDTH - 1] + "…"
            lines.append(f"{_V}{entry:<{_WIDTH}}{_V}")

    lines.append(_separator())
    lines.append(_box_line(f"Mission: Total ownership of Amjad's digital life"))
    lines.append(_bot_border())

    return "\n".join(lines)


def get_farewell(owner: str = "Amjad") -> str:
    """Return a JARVIS shutdown farewell message.

    Parameters
    ----------
    owner:
        Name of the owner (default ``"Amjad"``).
    """
    now = datetime.datetime.now().strftime("%H:%M:%S")
    return (
        f"[{now}] J.A.R.V.I.S — מערכות יורדות. "
        f"נתראה, {owner}. "
        "All systems standby."
    )


def get_mode_transition_message(from_mode: str, to_mode: str) -> str:
    """Return a brief message announcing a mode switch."""
    return (
        f"[JARVIS] Mode switch: {from_mode.upper()} → {to_mode.upper()}. "
        "מוכן."
    )


def get_alert_banner(message: str, level: str = "WARNING") -> str:
    """Return a compact single-line alert banner."""
    level_tag = level.upper()
    return f"[{_V} JARVIS/{level_tag} {_V}] {message}"
