"""Structured logging for the runtime.

A single named logger (`agency`) that every module uses. Off by default
(WARNING). Enable with `AGENCY_LOG=info` or the CLI `--verbose` flag.

Records carry structured `extra` fields so a downstream handler (or a
search over the log file) can filter by skill / tool / model without
parsing message text.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import contextmanager

LOGGER_NAME = "agency"


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def configure(level: str | int | None = None, *, stream=None) -> logging.Logger:
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
def timed(event: str, **fields):
    """Measure a block and emit one INFO record with elapsed_ms + fields.

        with timed("tool", name="read_file"):
            run_tool(...)
    """
    logger = get_logger()
    start = time.monotonic()
    try:
        yield
    finally:
        ms = round((time.monotonic() - start) * 1000)
        logger.info("%s elapsed_ms=%d %s",
                    event, ms,
                    " ".join(f"{k}={v}" for k, v in fields.items()))
