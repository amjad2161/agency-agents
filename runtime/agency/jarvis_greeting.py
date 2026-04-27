"""JARVIS Greeting Module — startup banner, farewell, and time-aware bilingual greetings.

All timestamps use Asia/Jerusalem (Israel Standard Time / IDT) via zoneinfo.
Falls back to UTC if the timezone data is unavailable.

Usage::

    from agency.jarvis_greeting import get_startup_banner, get_greeting, get_farewell
    print(get_startup_banner())
    print(get_greeting())          # time-aware Hebrew/English
    print(get_farewell())
"""

from __future__ import annotations

import datetime
from typing import Any

from .jarvis_soul import JARVIS_SOUL

# ---------------------------------------------------------------------------
# Timezone helper
# ---------------------------------------------------------------------------

_TZ_NAME = "Asia/Jerusalem"


def _jerusalem_now() -> datetime.datetime:
    """Return current time in Asia/Jerusalem. Falls back to local if unavailable."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(tz=ZoneInfo(_TZ_NAME))
    except Exception:
        # tzdata not installed or Python < 3.9 — fall back to local time
        return datetime.datetime.now()


# ---------------------------------------------------------------------------
# Box-drawing constants
# ---------------------------------------------------------------------------

_TL = "╔"
_TR = "╗"
_BL = "╚"
_BR = "╝"
_H = "═"
_V = "║"
_WIDTH = 50


def _box_line(content: str, width: int = _WIDTH) -> str:
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


# ---------------------------------------------------------------------------
# Time-aware greeting logic
# ---------------------------------------------------------------------------

def _time_period(hour: int) -> tuple[str, str]:
    """Return (hebrew_greeting, english_period) for the given hour (0-23)."""
    if 5 <= hour < 10:
        return "בוקר טוב", "Good morning"
    if 10 <= hour < 13:
        return "שלום", "Good day"
    if 13 <= hour < 17:
        return "אחר הצהריים טוב", "Good afternoon"
    if 17 <= hour < 21:
        return "ערב טוב", "Good evening"
    # night: 21-24, 0-5
    return "לילה טוב", "Good night"


def get_greeting(owner: str = "Amjad") -> str:
    """Return a time-aware bilingual greeting.

    Hebrew primary, English secondary. Includes Jerusalem local time.
    """
    now = _jerusalem_now()
    hebrew, english = _time_period(now.hour)
    time_str = now.strftime("%H:%M")
    tz_label = "IST" if now.utcoffset() is not None else "local"
    return f"{hebrew}, {owner}. {english}. {time_str} {tz_label}. מוכן."


# ---------------------------------------------------------------------------
# Startup banner
# ---------------------------------------------------------------------------

def get_startup_banner(status: dict[str, Any] | None = None) -> str:
    """Return a multi-line JARVIS startup banner string.

    Parameters
    ----------
    status:
        Optional dict with keys:
        - ``"mode"``          : current persona mode (str)
        - ``"systems_ok"``    : count of healthy subsystems (int)
        - ``"systems_total"`` : total subsystem count (int)
        - ``"subsystems"``    : dict of name → {"healthy": bool} (optional)

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

    now = _jerusalem_now()
    time_str = now.strftime("%Y-%m-%d %H:%M:%S")
    try:
        tz_name = str(now.tzinfo) if now.tzinfo else "local"
    except Exception:
        tz_name = "local"

    hebrew, _ = _time_period(now.hour)

    lines: list[str] = [_top_border()]
    lines.append(_box_line("J.A.R.V.I.S — Supreme Brainiac Active"))
    lines.append(_box_line("Just A Rather Very Intelligent System"))
    lines.append(_separator())
    lines.append(_box_line(f"Owner  : {JARVIS_SOUL['owner']}"))
    lines.append(_box_line(f"Mode   : {mode}"))
    lines.append(_box_line(f"Systems: {systems_ok}/{systems_total} online"))
    lines.append(_box_line(f"Time   : {time_str} ({tz_name})"))
    lines.append(_box_line(f"Greeting: {hebrew}, {JARVIS_SOUL['owner']}."))

    if subsystems:
        lines.append(_separator())
        for name, info in list(subsystems.items())[:8]:
            healthy = info.get("healthy", False)
            marker = "✓" if healthy else "✗"
            detail = info.get("detail", "")
            entry = f"  [{marker}] {name:<20} {detail}"
            if len(entry) > _WIDTH:
                entry = entry[: _WIDTH - 1] + "…"
            lines.append(f"{_V}{entry:<{_WIDTH}}{_V}")

    lines.append(_separator())
    lines.append(_box_line("Mission: Total ownership of Amjad's digital life"))
    lines.append(_bot_border())

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Farewell + auxiliary messages
# ---------------------------------------------------------------------------

def get_farewell(owner: str = "Amjad") -> str:
    """Return a JARVIS shutdown farewell message with Jerusalem local time."""
    now = _jerusalem_now()
    time_str = now.strftime("%H:%M:%S")
    _, english = _time_period(now.hour)
    return (
        f"[{time_str}] J.A.R.V.I.S — מערכות יורדות. "
        f"נתראה, {owner}. {english}. "
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
    return f"[{_V} JARVIS/{level.upper()} {_V}] {message}"
