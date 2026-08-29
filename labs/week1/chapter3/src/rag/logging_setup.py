"""Centralized loguru logging configuration.

Implements the --verbose / --quiet CLI options (SPEC section 5.1):
- by default loguru is configured at INFO with no per-stage noise;
- --verbose sets the level to DEBUG (and TRACE in some contexts) so every stage
  and every failure_stage is traced;
- --quiet suppresses per-case stderr progress.

The pipeline imports the module-level `log` logger everywhere; nothing else in the
deterministic boundary should import `logging` or `loguru` directly.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from loguru import logger

_CONFIGURED = False


def configure(verbose: bool = False, quiet: bool = False, *, log_file: str | None = None) -> None:
    """Configure loguru once. Idempotent.

    - verbose=True  => DEBUG level on stderr (+ optional file)
    - quiet=True    => WARNING on stderr (suppress per-case progress)
    - neither        => INFO on stderr
    """
    global _CONFIGURED
    # Drop the default loguru handler; replace with a configured one.
    logger.remove()

    level = "TRACE" if verbose else ("WARNING" if quiet else "INFO")
    # Redirect std logging (e.g. httpx warnings) into loguru.
    logger.add(
        sys.stderr,
        level=level,
        format="{time:HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        colorize=True,
    )
    if log_file:
        logger.add(
            Path(log_file),
            level=level,
            format="{time:HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            mode="a",
        )

    # Quiet the noisy std-log bridges; keep them mapped through loguru via InterceptHandler.
    logging.basicConfig(
        handlers=[_InterceptHandler()] if not _CONFIGURED else None, level=logging.WARNING
    )
    for name in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)
    _CONFIGURED = True


class _InterceptHandler(logging.Handler):
    """Bridge stdlib logging records into loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        # Make sure the loguru level matches the stdlib level name.
        level = "WARNING" if record.levelno >= logging.WARNING else "INFO"
        try:
            logger.log(level, record.getMessage())
        except (ValueError, TypeError, KeyError):
            # Only the three realistic emit failures are rethrown as an emit error;
            # a truly unexpected crash propagates rather than being swallowed blind.
            self.handleError(record)
