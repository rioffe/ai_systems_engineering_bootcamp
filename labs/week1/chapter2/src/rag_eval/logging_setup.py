"""The single logging seam for ``rag-eval`` (SPEC R-11 / §5.1 diagnostic).

loguru owns one stderr sink, configured *once* at CLI startup via :func:`configure_logging`.
Every module that wants to log imports the shared handle:

    from .logging_setup import logger
    logger.debug("raw prompt/response ...")   # --verbose DEBUG: raw LLM I/O
    logger.info("...")                         # --verbose (default INFO): lifecycle/progress

Design (see SKILL decisions with the operator):

* **Inert by default.** Without ``--verbose`` there are *no* handlers, so every
  ``logger.*`` call is a no-op -- the deterministic core stays silent and bit-for-bit
  reproducible (R-15). This is also the ``--quiet`` behavior, which ``--verbose``
  overrides.
* **One sink, stderr.** stdout stays reserved for the human-readable summary and the
  machine-readable JSON report; all diagnostic chatter goes to stderr.
* **Level gates raw I/O.** ``--verbose`` defaults to ``INFO`` (per-case progress,
  lifecycle, config/params); ``--verbose DEBUG`` additionally dumps the raw prompts and
  responses the LLM modules (``model.py`` / ``judgment.py``) pass at DEBUG.

loguru ships a default stderr handler at DEBUG on import; we own handlers entirely, so
:func:`configure_logging` always ``logger.remove()`` first and adds our sink only when
verbose. It is idempotent, so callers may re-configure per subcommand.
"""

from __future__ import annotations

from loguru import logger  # the shared, process-wide handle (one sink, many importers)

# Timestamp + level + module:function:line, colored (no ANSI when stderr is not a TTY).
DEFAULT_FORMAT = (
    "<green>{time:HH:mm:ss.SS}</green> | "
    "<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - {message}"
)

#: The level for the default ``--verbose`` (lifecycle / progress / config) when no level
#: is given. ``--verbose DEBUG`` selects DEBUG to also surface raw LLM I/O.
DEFAULT_LEVEL = "INFO"


def configure_logging(verbose: bool, level: str = DEFAULT_LEVEL) -> None:
    """Configure the process-wide loguru stderr sink.

     ``verbose`` False -> remove every handler so nothing is emitted (the deterministic
    default; ``--quiet`` is the same outcome and is *overridden* by ``--verbose``).
     ``verbose`` True  -> a single stderr sink at ``level`` (INFO by default; DEBUG dumps
    raw LLM I/O). Idempotent: callers may re-configure per subcommand.
    """
    logger.remove()  # drop loguru's default stderr handler (present on import)
    if not verbose:
        return
    logger.add(
        sys_stderr(),
        level=level,
        format=DEFAULT_FORMAT,
        backtrace=False,
        diagnose=False,
        enqueue=False,
    )


def clip(text: str, limit: int = 2000) -> str:
    """Truncate a raw LLM payload for DEBUG logging, marking where it was cut.

    The full text is never needed on screen; a truncation marker keeps a ``--verbose
    DEBUG`` log readable while recording that the payload was longer than ``limit``.
    """
    if len(text) <= limit:
        return text
    cut = len(text) - limit
    return text[:limit] + f"\n... <truncated {cut} more chars>"


def sys_stderr() -> object:
    # Imported lazily inside the function so ``import rag_eval.logging_setup`` never
    # touches sys at module load (keeps the import side-effect-free).
    import sys

    return sys.stderr


__all__ = ["DEFAULT_LEVEL", "clip", "configure_logging", "logger"]
