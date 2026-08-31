# pyright: reportMissingImports=false
from __future__ import annotations

import sys
from loguru import logger

_level: str | None = None
_include_raw = False

logger.remove()


def configure_diagnostics(level: str | None, include_raw: bool = False) -> None:
    global _level, _include_raw
    _level, _include_raw = level, include_raw
    logger.remove()
    if level:
        logger.add(sys.stderr, level=level, format="{time:HH:mm:ss} | {level} | {message}")


def metadata(message: str, *args: object) -> None:
    if _level in {"INFO", "DEBUG"}:
        logger.info(message, *args)


def debug_payload(message: str, *args: object) -> None:
    if _level == "DEBUG" or _include_raw:
        logger.debug(message, *args)
