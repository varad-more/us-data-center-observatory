"""Structured JSON logging.

Connector runs are the primary thing operators watch, and they fail in ways that
only make sense with context attached (which source, which run, which URL). All
logs are therefore structured, and ``bind_run_context`` attaches identifiers once
so every downstream line carries them.
"""

from __future__ import annotations

import logging
import sys
from typing import Any
from uuid import UUID

import structlog

_CONFIGURED = False


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Configure structlog and the stdlib root logger.

    Idempotent: repeated calls (common in tests) reconfigure cleanly rather than
    stacking duplicate handlers.

    Args:
        level: Standard logging level name.
        fmt: ``"json"`` for machine ingestion, ``"console"`` for local reading.
    """
    global _CONFIGURED

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]
    if fmt == "json":
        processors.append(structlog.processors.format_exc_info)
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()))

    # The stdlib factory is required rather than PrintLoggerFactory because
    # `add_logger_name` reads `logger.name`, which only stdlib loggers expose.
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )
    logging.basicConfig(level=numeric_level, stream=sys.stderr, format="%(message)s", force=True)
    _CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structured logger, configuring defaults on first use."""
    if not _CONFIGURED:
        configure_logging()
    return structlog.get_logger(name)  # type: ignore[no-any-return]


def bind_run_context(**values: str | int | UUID | None) -> None:
    """Attach identifiers to every subsequent log line in this context."""
    structlog.contextvars.bind_contextvars(
        **{k: str(v) if isinstance(v, UUID) else v for k, v in values.items() if v is not None}
    )


def clear_run_context() -> None:
    """Drop all bound context variables."""
    structlog.contextvars.clear_contextvars()
