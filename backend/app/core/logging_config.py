"""
Logging configuration module.

Provides a single `configure_logging()` entry point that sets up
structured, consistent logging for the entire application. Invoked once
at application startup (see app/main.py).

Design notes:
- Supports plain-text logs (readable in local development) and
  JSON-formatted logs (useful if aggregated later), controlled by the
  LOG_JSON setting.
- Sensitive data (passwords, JWT tokens, raw financial line items,
  full document text) must NEVER be passed into log calls anywhere in the
  application — this module only controls format/level/output, not what
  gets logged by call sites.
- No business logic lives here.
"""

import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict

from app.core.config import get_settings


class JSONLogFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        log_entry: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        request_id = getattr(record, "request_id", None)
        if request_id:
            log_entry["request_id"] = request_id

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


class PlainTextLogFormatter(logging.Formatter):
    """Human-readable formatter used for local development."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def configure_logging() -> None:
    """
    Configure the root logger for the application.

    Idempotent: safe to call multiple times (e.g. in tests) without
    duplicating log handlers.
    """
    settings = get_settings()

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL.upper())

    for existing_handler in list(root_logger.handlers):
        root_logger.removeHandler(existing_handler)

    handler = logging.StreamHandler(stream=sys.stdout)
    formatter: logging.Formatter = (
        JSONLogFormatter() if settings.LOG_JSON else PlainTextLogFormatter()
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Tame overly verbose third-party loggers while keeping our own
    # application loggers at the configured level.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DEBUG else logging.WARNING
    )
    # sentence-transformers / huggingface libraries are very chatty at
    # INFO level (model download/load progress); quiet them down here so
    # they don't drown out application logs once the RAG module is wired
    # up in a later phase.
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging configured (level=%s, json=%s, environment=%s)",
        settings.LOG_LEVEL.upper(),
        settings.LOG_JSON,
        settings.ENVIRONMENT,
    )


def get_logger(name: str) -> logging.Logger:
    """Convenience accessor so call sites don't import `logging` directly."""
    return logging.getLogger(name)
