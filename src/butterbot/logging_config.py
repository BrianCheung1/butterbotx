"""Logging configuration for ButterBot."""

from __future__ import annotations

import logging


def configure_logging(level_name: str) -> None:
    """Configure process-wide logging once at application startup."""
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        raise ValueError(f"Invalid log level: {level_name}")

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
