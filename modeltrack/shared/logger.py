"""
Structured logging setup for ModelTrack.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class _JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Attach exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        # Attach any extra fields added via `extra={...}`
        extra_keys = set(record.__dict__) - {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
            "taskName",
        }
        for key in extra_keys:
            log_obj[key] = getattr(record, key)

        return json.dumps(log_obj, default=str)


def _get_level(level_str: str) -> int:
    """Convert a level name string to a logging level integer."""
    return getattr(logging, level_str.upper(), logging.INFO)


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """
    Return a named logger configured with JSON output.

    Parameters
    ----------
    name:
        Logger name (typically ``__name__`` of the calling module).
    level:
        Override log level.  Defaults to the value in application settings.
    """
    # Avoid circular import by deferring config access
    if level is None:
        try:
            from modeltrack.config import get_settings

            level = get_settings().LOG_LEVEL
        except Exception:
            level = "INFO"

    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JSONFormatter())
        logger.addHandler(handler)
        logger.propagate = False

    logger.setLevel(_get_level(level))
    return logger
