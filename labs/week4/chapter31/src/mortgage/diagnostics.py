from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from loguru import logger

VERBOSITY_LEVELS = ("OFF", "INFO", "DEBUG")


def configure_verbosity(
    level: str | None,
    *,
    sink: Callable[[str], Any] | None = None,
) -> None:
    """Configure colored Loguru diagnostics for CLI or GUI use."""
    logger.remove()
    normalized = (level or "OFF").upper()
    if normalized not in VERBOSITY_LEVELS:
        raise ValueError(f"verbosity must be one of {', '.join(VERBOSITY_LEVELS)}")
    if normalized == "OFF":
        return
    if sink is None:
        logger.add(
            sys.stderr,
            level=normalized,
            colorize=True,
            format="<green>{time:HH:mm:ss}</green> | <level>{level:<5}</level> | {message}",
        )
    else:
        logger.add(
            lambda message: sink(str(message).rstrip("\n")),
            level=normalized,
            colorize=False,
            format="{message}",
        )


def metadata(message: str, *args: Any, **kwargs: Any) -> None:
    logger.info(message, *args, **kwargs)


def raw(message: str, *args: Any, **kwargs: Any) -> None:
    logger.debug(message, *args, **kwargs)
