from __future__ import annotations

import logging
import os
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

# Standard log record attributes that should not be treated as "extra" context.
_STANDARD_LOG_RECORD_ATTRS = {
    "name",
    "msg",
    "args",
    "created",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "thread",
    "threadName",
    "exc_info",
    "exc_text",
    "stack_info",
    "taskName",
    "asctime",
}

# Context is propagated correctly across async tasks and awaits.
_LOG_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar("log_context", default=None)

DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DEFAULT_LOG_FORMAT_WITH_SOURCE = "%(asctime)s | %(levelname)s | %(name)s | %(filename)s:%(lineno)d | %(message)s"


class ContextInjectionFilter(logging.Filter):
    """Injects contextvars-based fields into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        context = _LOG_CONTEXT.get()
        if not context:
            return True

        for key, value in context.items():
            if key in _STANDARD_LOG_RECORD_ATTRS:
                continue
            setattr(record, key, value)
        return True


class SmartContextFormatter(logging.Formatter):
    """Formatter that appends all extra fields as key=value context."""

    def format(self, record: logging.LogRecord) -> str:
        base_message = super().format(record)
        extra_fields = {key: value for key, value in record.__dict__.items() if key not in _STANDARD_LOG_RECORD_ATTRS}
        if not extra_fields:
            return base_message

        context_str = " ".join(f"{key}={value}" for key, value in extra_fields.items())
        return f"{base_message} [{context_str}]"


class ColorFormatter(SmartContextFormatter):
    """Small ANSI color wrapper around SmartContextFormatter."""

    _RESET = "\x1b[0m"
    _COLORS = {
        "DEBUG": "\x1b[36m",  # cyan
        "INFO": "\x1b[32m",  # green
        "WARNING": "\x1b[33m",  # yellow
        "ERROR": "\x1b[31m",  # red
        "CRITICAL": "\x1b[35;1m",  # bold magenta
    }
    _CONTEXT_COLOR = "\x1b[90m"  # bright black / gray

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        color = self._COLORS.get(record.levelname, "")
        if not color:
            return message
        return f"{color}{message}{self._RESET}"


@contextmanager
def log_context(**kwargs: Any) -> Iterator[None]:
    """Temporarily attach context fields to all log lines in this scope."""

    current = _LOG_CONTEXT.get() or {}
    new_context = {**current, **kwargs}
    token = _LOG_CONTEXT.set(new_context)
    try:
        yield
    finally:
        _LOG_CONTEXT.reset(token)


def get_log_context() -> Mapping[str, Any]:
    """Return the current logging context (useful for debugging/tests)."""

    return _LOG_CONTEXT.get() or {}


def _resolve_log_level() -> int:
    raw_level = os.getenv("LOG_LEVEL", "INFO").upper().strip()
    return getattr(logging, raw_level, logging.INFO)


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _use_color() -> bool:
    # Color by default in interactive terminals, but easy to override.
    return _env_flag("LOG_COLOR", sys.stdout.isatty())


def _include_source() -> bool:
    # File:line is helpful while debugging, noisy in prod.
    return _env_flag("LOG_INCLUDE_SOURCE", False)


def setup_logging() -> None:
    """
    Configure global, context-aware logging for the application.

    Environment variables:
    - LOG_LEVEL: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)
    - LOG_COLOR: enable ANSI colors (default: auto when TTY)
    - LOG_INCLUDE_SOURCE: include filename:line in logs (default: false)
    """
    root_level = _resolve_log_level()
    log_format = DEFAULT_LOG_FORMAT_WITH_SOURCE if _include_source() else DEFAULT_LOG_FORMAT

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    logging.captureWarnings(True)
    root_logger.setLevel(root_level)

    handler = logging.StreamHandler(sys.stdout)
    formatter: logging.Formatter
    if _use_color():
        formatter = ColorFormatter(log_format, datefmt=DEFAULT_DATE_FORMAT)
    else:
        formatter = SmartContextFormatter(log_format, datefmt=DEFAULT_DATE_FORMAT)
    handler.setFormatter(formatter)
    handler.addFilter(ContextInjectionFilter())
    root_logger.addHandler(handler)

    # Align common third-party loggers with the chosen level.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).setLevel(root_level)

    logging.getLogger(__name__).info("Logging configured", extra={"log_level": logging.getLevelName(root_level)})
