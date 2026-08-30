"""Tests for rag.logging_setup -- --verbose / --quiet level mapping (SPEC 5.1)."""

from __future__ import annotations

from loguru import logger

from rag.logging_setup import configure


def _stderr_levelno():
    # loguru keeps configured handlers on the (private but stable) core; the
    # stderr handler is the only one added without a log_file.
    return {h.levelno for h in logger._core.handlers.values()}


def test_configure_verbose_is_trace():
    configure(verbose=True)
    assert _stderr_levelno() == {5}  # TRACE


def test_configure_default_is_info():
    configure()
    assert _stderr_levelno() == {20}  # INFO


def test_configure_quiet_is_warning():
    configure(quiet=True)
    assert _stderr_levelno() == {30}  # WARNING
