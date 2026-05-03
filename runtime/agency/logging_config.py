"""Structured logging configuration for the agency runtime.

``setup_logging(level, format)`` installs a single named logger (``agency``)
with either a JSON formatter (for production / log-aggregation pipelines) or a
human-readable "pretty" formatter (for local development).

JSON log record fields
----------------------
timestamp   ISO-8601 UTC string (milliseconds)
level       DEBUG / INFO / WARNING / ERROR / CRITICAL
logger      logger name (e.g. "agency" or "agency.llm")
message     formatted log message
session_id  present when set via ``set_session_id()``
duration_ms present when the caller includes it in the extra dict

Usage
-----
    from agency.logging_config import setup_logging, set_session_id
    setup_logging(level="INFO", format="json")   # production
    setup_logging(level="DEBUG", format="pretty") # dev

Keep ``agency.logging`` (the legacy module) intact for back-compat —
this module is additive.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextlib import contextmanager
from typing import Any, Generator

LOGGER_NAME = "agency"

# Thread-local / module-level session context injected into every JSON record.
_session_id: str | None = None


def set_session_id(sid: str | None) -> None:
    """Set or clear the session_id injected into JSON log records."""
    global _session_id
    _session_id = sid


def get_session_id() -> str | None:
    return _session_id


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        # Build base payload
        payload: dict[str, Any] = {
            "timestamp": self._utc_iso(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Inject session_id if available
        sid = getattr(record, "session_id", None) or _session_id
        if sid:
            payload["session_id"] = sid
        # Propagate duration_ms if the caller set it
        dur = getattr(record, "duration_ms", None)
        if dur is not None:
            payload["duration_ms"] = dur
        # Any extra fields passed via extra= kwarg
        _SKIP = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
            "taskName",
        }
        for k, v in record.__dict__.items():
            if k not in _SKIP and not k.startswith("_"):
                payload[k] = v
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)

    @staticmethod
    def _utc_iso(created: float) -> str:
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(created, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


class _PrettyFormatter(logging.Formatter):
    """Coloured, human-readable formatter for dev terminals."""

    _COLORS = {
        "DEBUG":    "\033[36m",   # cyan
        "INFO":     "\033[32m",   # green
        "WARNING":  "\033[33m",   # yellow
        "ERROR":    "\033[31m",   # red
        "CRITICAL": "\033[35m",   # magenta
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        color = self._COLORS.get(record.levelname, "")
        reset = self._RESET
        ts = self.formatTime(record, "%H:%M:%S")
        sid = getattr(record, "session_id", None) or _session_id
        sid_part = f" [{sid[:8]}]" if sid else ""
        dur = getattr(record, "duration_ms", None)
        dur_part = f" ({dur}ms)" if dur is not None else ""
        msg = record.getMessage()
        line = f"{ts} {color}{record.levelname:<7}{reset} {record.name}{sid_part}  {msg}{dur_part}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


# ---------------------------------------------------------------------------
# Public setup API
# ---------------------------------------------------------------------------

def setup_logging(
    level: str | int = "INFO",
    format: str = "pretty",  # noqa: A002
    *,
    stream: Any = None,
) -> logging.Logger:
    """Install structured logging on the 'agency' logger.

    Parameters
    ----------
    level:
        Logging level string (``"DEBUG"``, ``"INFO"``, …) or int constant.
        Falls back to ``AGENCY_LOG`` env var, then ``WARNING``.
    format:
        ``"json"`` — machine-readable JSON lines (production).
        ``"pretty"`` — coloured human text (development).
    stream:
        Output stream; defaults to ``sys.stderr``.

    Returns the configured logger (idempotent — won't duplicate handlers).
    """
    logger = logging.getLogger(LOGGER_NAME)

    # Resolve level
    if isinstance(level, str):
        env_level = os.environ.get("AGENCY_LOG", "")
        resolved = level or env_level or "WARNING"
        numeric = getattr(logging, resolved.upper(), logging.WARNING)
    else:
        numeric = level

    logger.setLevel(numeric)
    logger.propagate = False

    # Idempotent: skip if already configured with our marker
    fmt_type = format.lower()
    if not any(getattr(h, "_agency_structured", False) for h in logger.handlers):
        if fmt_type == "json":
            formatter: logging.Formatter = _JsonFormatter()
        else:
            formatter = _PrettyFormatter()

        handler = logging.StreamHandler(stream or sys.stderr)
        handler.setFormatter(formatter)
        handler._agency_structured = True  # type: ignore[attr-defined]
        logger.addHandler(handler)

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return the agency logger (or a child logger if *name* is given)."""
    base = LOGGER_NAME
    return logging.getLogger(f"{base}.{name}" if name else base)


# ---------------------------------------------------------------------------
# Timed context manager (also available in legacy logging.py)
# ---------------------------------------------------------------------------

@contextmanager
def timed_structured(
    event: str,
    logger: logging.Logger | None = None,
    **fields: Any,
) -> Generator[dict[str, Any], None, None]:
    """Measure a block; emit one INFO record with ``duration_ms`` + extra fields.

    Example::

        with timed_structured("llm.call", model="opus") as ctx:
            result = call_llm(...)
            ctx["tokens"] = result.usage.input_tokens
    """
    log = logger or get_logger()
    if not log.isEnabledFor(logging.INFO):
        yield fields
        return

    start = time.monotonic()
    try:
        yield fields
    finally:
        ms = round((time.monotonic() - start) * 1000)
        extra = dict(fields)
        extra["duration_ms"] = ms
        log.info("%s %s", event,
                 " ".join(f"{k}={v}" for k, v in fields.items()),
                 extra={"duration_ms": ms})
