"""Shared logging helpers for SemaFS runtime and CLI entrypoints."""

from __future__ import annotations

import logging
import os

DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DEFAULT_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def resolve_log_level(
    level: str | None = None,
    *,
    env_var: str = "SEMAFS_LOG_LEVEL",
    default: str = "INFO",
) -> int:
    """Resolve a log level token to a stdlib logging level integer."""
    raw = (level or os.getenv(env_var) or default).strip().upper()
    if raw.isdigit():
        return int(raw)
    return getattr(logging, raw, logging.INFO)


def configure_logging(
    level: str | None = None,
    *,
    force: bool = False,
) -> None:
    """Configure root logging for CLI-style executions."""
    logging.basicConfig(
        level=resolve_log_level(level),
        format=DEFAULT_LOG_FORMAT,
        datefmt=DEFAULT_LOG_DATEFMT,
        force=force,
    )
