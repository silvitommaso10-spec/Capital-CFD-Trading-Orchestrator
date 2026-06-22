"""Secure logging utilities.

The orchestrator must never write secrets (API keys, passwords, session
tokens) to logs. This module provides a logging filter that redacts known
sensitive patterns and a helper to configure logging consistently.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Iterable, Pattern

# Header/field names whose values must always be redacted.
_SENSITIVE_KEYS = (
    "password",
    "api_key",
    "apikey",
    "x-cap-api-key",
    "cst",
    "x-security-token",
    "securitytoken",
    "authorization",
    "token",
    "secret",
)

# Match `key: value`, `key=value`, or `"key": "value"` style occurrences.
_KEY_VALUE_PATTERNS: tuple[Pattern[str], ...] = tuple(
    re.compile(
        rf'(?i)(["\']?{re.escape(key)}["\']?\s*[:=]\s*["\']?)([^"\'\s,}}]+)'
    )
    for key in _SENSITIVE_KEYS
)

_REDACTION = "***REDACTED***"


def redact(text: str) -> str:
    """Return ``text`` with the values of known sensitive keys redacted."""

    redacted = text
    for pattern in _KEY_VALUE_PATTERNS:
        redacted = pattern.sub(rf"\1{_REDACTION}", redacted)
    return redacted


class RedactingFilter(logging.Filter):
    """Logging filter that redacts secrets from messages and arguments."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(
    level: str | int | None = None,
    *,
    extra_filters: Iterable[logging.Filter] = (),
) -> None:
    """Configure root logging with secret redaction enabled.

    The level defaults to the ``LOG_LEVEL`` environment variable, then ``INFO``.
    """

    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO")

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    handler.addFilter(RedactingFilter())
    for extra in extra_filters:
        handler.addFilter(extra)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Return a logger that always has the redacting filter attached."""

    logger = logging.getLogger(name)
    if not any(isinstance(f, RedactingFilter) for f in logger.filters):
        logger.addFilter(RedactingFilter())
    return logger
