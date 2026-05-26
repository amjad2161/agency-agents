"""Structured logging for the runtime.

A single named logger (`agency`) that every module uses. Off by default
(WARNING). Enable with `AGENCY_LOG=info` or the CLI `--verbose` flag.

Records include searchable `key=value` fields appended to the log message
text so a downstream handler or log-file search can filter by skill /
tool / model, though machine consumers must parse message text.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import contextmanager
from typing import Any, Generator

LOGGER_NAME = "agency"


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def configure(level: str | int | None = None, *, stream: Any = None) -> logging.Logger:
    """Attach a single stream handler with a compact formatter.

    Idempotent — calling it twice doesn't duplicate handlers. Default level
    comes from `AGENCY_LOG`; if unset, WARNING.
    """
    logger = get_logger()
    if level is None:
        level = os.environ.get("AGENCY_LOG", "WARNING")
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.WARNING)
    logger.setLevel(level)
    # Don't bubble to the root logger — we own the format on this channel.
    logger.propagate = False
    if not any(getattr(h, "_agency", False) for h in logger.handlers):
        handler = logging.StreamHandler(stream or sys.stderr)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        ))
        handler._agency = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    return logger


@contextmanager
def timed(event: str, **fields: Any) -> Generator[dict[str, Any], None, None]:
    """Measure a block and emit one INFO record with elapsed_ms + fields.

    No-op (no timing, no string formatting) when INFO is disabled, so
    wrapping every tool/LLM call costs near-zero in production where
    logging is off by default. Callers can attach more fields after the
    fact by mutating the dict yielded into the `as` clause:

        with timed("tool.run", name="read_file") as fields:
            result = run_tool(...)
            fields["is_error"] = result.is_error
    """
    logger = get_logger()
    if not logger.isEnabledFor(logging.INFO):
        yield fields
        return

    start = time.monotonic()
    try:
        yield fields
    finally:
        ms = round((time.monotonic() - start) * 1000)
        logger.info("%s elapsed_ms=%d %s",
                    event, ms,
                    " ".join(f"{k}={v}" for k, v in fields.items()))
