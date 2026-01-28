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
    "level_color",
    "name_color",
    "source_color",
    "reset",
    "color_message",
    "log_level",
}

# Context is propagated correctly across async tasks and awaits.
_LOG_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar("log_context", default=None)

DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

APP_LOGGER_PREFIX = "app"

# Pragmatic defaults to reduce third-party noise when LOG_LEVEL is DEBUG.
_DEFAULT_THIRD_PARTY_LEVELS: dict[str, str] = {
    "uvicorn": "WARNING",
    "uvicorn.error": "INFO",
    "uvicorn.access": "WARNING",
    "httpx": "WARNING",
    "httpcore": "WARNING",
    "urllib3": "WARNING",
    "weasyprint": "WARNING",
    "supabase": "WARNING",
    "postgrest": "WARNING",
    "gotrue": "WARNING",
    "realtime": "WARNING",
    "storage3": "WARNING",
}

# Third-party loggers that are allowed to emit below WARNING.
_ALLOW_BELOW_WARNING: set[str] = {"uvicorn.error"}


def _build_log_format(include_source: bool) -> str:
    """Return the base format string, using formatter-provided color fields."""

    if include_source:
        return (
            "%(level_color)s%(asctime)s | %(levelname)s%(reset)s | "
            "%(name_color)s%(name)s%(reset)s | "
            "%(source_color)s%(filename)s:%(lineno)d%(reset)s | "
            "%(level_color)s%(message)s%(reset)s"
        )

    return (
        "%(level_color)s%(asctime)s | %(levelname)s%(reset)s | "
        "%(name_color)s%(name)s%(reset)s | "
        "%(level_color)s%(message)s%(reset)s"
    )


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


class AppLoggingFilter(logging.Filter):
    """Apply consistent log levels to app vs third-party loggers."""

    def __init__(
        self,
        root_level: int,
        *,
        app_prefix: str,
        third_party_levels: Mapping[str, int],
    ) -> None:
        super().__init__()
        self.root_level = root_level
        self.app_prefix = app_prefix
        self.third_party_levels = dict(third_party_levels)

    def _is_app_logger(self, name: str) -> bool:
        return name == "__main__" or name == self.app_prefix or name.startswith(f"{self.app_prefix}.")

    def _match_third_party_level(self, name: str) -> int | None:
        """Return the most specific matching third-party level, if any."""

        best_level: int | None = None
        best_len = -1
        for prefix, level in self.third_party_levels.items():
            if name == prefix or name.startswith(prefix + "."):
                prefix_len = len(prefix)
                if prefix_len > best_len:
                    best_level = level
                    best_len = prefix_len
        return best_level

    def _allow_below_warning(self, name: str) -> bool:
        for prefix in _ALLOW_BELOW_WARNING:
            if name == prefix or name.startswith(prefix + "."):
                return True
        return False

    def filter(self, record: logging.LogRecord) -> bool:
        logger = logging.getLogger(record.name)

        # Only set the level when it hasn't been explicitly configured.
        if logger.level == logging.NOTSET:
            matched_level = self._match_third_party_level(record.name)
            if matched_level is not None:
                logger.setLevel(matched_level)
            elif not self._is_app_logger(record.name):
                logger.setLevel(logging.WARNING)
            else:
                logger.setLevel(self.root_level)

        # Always drop low-level third-party chatter.
        if not self._is_app_logger(record.name):
            matched_level = self._match_third_party_level(record.name)
            threshold = matched_level if matched_level is not None else logging.WARNING
            if threshold < logging.WARNING and not self._allow_below_warning(record.name):
                threshold = logging.WARNING
            return record.levelno >= threshold

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
    """Colorize timestamp+level+message by level, name/source by fixed blues."""

    _RESET = "\x1b[0m"
    _LEVEL_COLORS = {
        "DEBUG": "\x1b[36m",  # cyan
        "INFO": "\x1b[32m",  # green
        "WARNING": "\x1b[33m",  # yellow
        "ERROR": "\x1b[31m",  # red
        "CRITICAL": "\x1b[1;31m",  # bold red
    }
    _NAME_COLOR = "\x1b[34m"  # blue
    _SOURCE_COLOR = "\x1b[94m"  # bright blue

    def format(self, record: logging.LogRecord) -> str:
        # Inject fields used by the format string.
        level_color = self._LEVEL_COLORS.get(record.levelname, "")
        record.level_color = level_color  # type: ignore[attr-defined]
        record.name_color = self._NAME_COLOR  # type: ignore[attr-defined]
        record.source_color = self._SOURCE_COLOR  # type: ignore[attr-defined]
        record.reset = self._RESET  # type: ignore[attr-defined]
        return super().format(record)


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


def _resolve_log_level(default: str = "INFO") -> int:
    raw_level = os.getenv("LOG_LEVEL", default).upper().strip()
    return getattr(logging, raw_level, logging.INFO)


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _use_color() -> bool:
    # Color by default in interactive terminals, but easy to override.
    return _env_flag("LOG_COLOR", sys.stdout.isatty())


def _level_from_name(level_name: str, fallback: int) -> int:
    return getattr(logging, level_name.upper(), fallback)


def _clamp_to_warning(level: int) -> int:
    """Ensure third-party loggers never go below WARNING."""

    return level if level >= logging.WARNING else logging.WARNING


def _resolve_third_party_levels(root_level: int, overrides: Mapping[str, str] | None) -> dict[str, int]:
    levels: dict[str, int] = {}
    for name, level_name in _DEFAULT_THIRD_PARTY_LEVELS.items():
        level = _level_from_name(level_name, root_level)
        if name not in _ALLOW_BELOW_WARNING:
            level = _clamp_to_warning(level)
        levels[name] = level

    if not overrides:
        return levels

    for name, level_name in overrides.items():
        level = _level_from_name(level_name, root_level)
        if name not in _ALLOW_BELOW_WARNING:
            level = _clamp_to_warning(level)
        levels[name] = level
    return levels


def _reset_logging_state() -> logging.Logger:
    """Reset handlers and logger state so configuration is deterministic."""

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    for name in logging.root.manager.loggerDict:
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
        logger.setLevel(logging.NOTSET)

    logging.captureWarnings(True)
    return root_logger


def _apply_logger_levels(
    *,
    root_logger: logging.Logger,
    root_level: int,
    app_prefix: str,
    third_party_levels: Mapping[str, int],
) -> None:
    """Apply levels to existing loggers and add a filter for future ones."""

    root_logger.setLevel(root_level)

    app_filter = AppLoggingFilter(
        root_level,
        app_prefix=app_prefix,
        third_party_levels=third_party_levels,
    )

    for handler in root_logger.handlers:
        handler.addFilter(app_filter)

    for name in logging.root.manager.loggerDict:
        logger = logging.getLogger(name)

        is_app = name == "__main__" or name == app_prefix or name.startswith(f"{app_prefix}.")
        if is_app:
            logger.setLevel(root_level)
            continue

        matched_level = app_filter._match_third_party_level(name)
        if matched_level is not None:
            logger.setLevel(matched_level)
            continue

        logger.setLevel(logging.WARNING)


def setup_logging(
    *,
    log_level: str | None = None,
    third_party_levels: Mapping[str, str] | None = None,
) -> None:
    """
    Configure global, context-aware logging for the application.

    Environment variables:
    - LOG_LEVEL: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)
    - LOG_COLOR: enable ANSI colors (default: auto when TTY)
    """
    root_level = _resolve_log_level(log_level or "INFO")
    include_source = True
    log_format = _build_log_format(include_source)

    root_logger = _reset_logging_state()

    handler = logging.StreamHandler(sys.stdout)
    formatter: logging.Formatter
    if _use_color():
        formatter = ColorFormatter(log_format, datefmt=DEFAULT_DATE_FORMAT)
    else:
        # Strip color fields from the format when ANSI colors are disabled.
        plain_format = "%(asctime)s | %(levelname)s | %(name)s | %(filename)s:%(lineno)d | %(message)s"
        formatter = SmartContextFormatter(plain_format, datefmt=DEFAULT_DATE_FORMAT)

    handler.setFormatter(formatter)
    handler.addFilter(ContextInjectionFilter())
    root_logger.addHandler(handler)

    resolved_third_party_levels = _resolve_third_party_levels(root_level, third_party_levels)

    _apply_logger_levels(
        root_logger=root_logger,
        root_level=root_level,
        app_prefix=APP_LOGGER_PREFIX,
        third_party_levels=resolved_third_party_levels,
    )

    logging.getLogger(__name__).info(
        "Logging configured",
        extra={"log_level": logging.getLevelName(root_level)},
    )
