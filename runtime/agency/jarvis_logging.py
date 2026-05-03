"""Structured JSON logging for JARVIS.

Provides a :func:`configure` helper to set up the ``"agency"`` logger
with either JSON or plain-text formatting, and a :func:`get_logger`
accessor for retrieval by subsystems.

Example::

    from runtime.agency.jarvis_logging import configure, get_logger
    configure(json_format=True, level=logging.INFO)
    logger = get_logger()
    logger.info("Request processed", extra={"span_id": "abc123"})
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Dict, Any


def configure(
    name: str = "agency",
    level: int = logging.INFO,
    json_format: bool = True,
) -> logging.Logger:
    """Configure structured logging for JARVIS.

    Attaches a :class:`logging.StreamHandler` to *sys.stdout* using
    either :class:`JsonFormatter` (when *json_format* is ``True``)
    or a simple plain-text formatter.

    Args:
        name: Logger namespace (default ``"agency"``).
        level: Minimum log level (default :data:`logging.INFO`).
        json_format: Emit JSON when ``True``, plain text otherwise.

    Returns:
        The configured :class:`logging.Logger` instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        if json_format:
            handler.setFormatter(JsonFormatter())
        else:
            handler.setFormatter(
                logging.Formatter(
                    fmt="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%Y-%m-%dT%H:%M:%S",
                )
            )
        logger.addHandler(handler)

    return logger


class JsonFormatter(logging.Formatter):
    """JSON log formatter for structured logging.

    Produces single-line JSON records with timestamp, level, logger name,
    message, and optional ``span_id`` or exception information.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format *record* as a JSON string.

        Args:
            record: The log record to format.

        Returns:
            A JSON-encoded log line.
        """
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "span_id"):
            log_entry["span_id"] = record.span_id
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def get_logger(name: str = "agency") -> logging.Logger:
    """Return the named logger.

    Args:
        name: Logger namespace (default ``"agency"``).

    Returns:
        A :class:`logging.Logger` instance.
    """
    return logging.getLogger(name)
