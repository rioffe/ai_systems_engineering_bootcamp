"""Total retry taxonomy and bounded tool execution."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .tools import AuthenticationError, PermanentError, RateLimitError, TransientError


class FailureClass(str, Enum):
    TRANSIENT = "TRANSIENT"
    INVALID_INPUT = "INVALID_INPUT"
    AUTHENTICATION = "AUTHENTICATION"
    PERMISSION = "PERMISSION"
    RATE_LIMIT = "RATE_LIMIT"
    PERMANENT = "PERMANENT"

class PermissionFailure(Exception):
    pass

@dataclass
class ToolExecution:
    result: Any = None
    error: str | None = None
    failure_class: FailureClass | None = None
    attempts: int = 0
    retries: int = 0


def classify_error(error: BaseException) -> FailureClass:
    if isinstance(error, TransientError): return FailureClass.TRANSIENT
    if isinstance(error, RateLimitError): return FailureClass.RATE_LIMIT
    if isinstance(error, AuthenticationError): return FailureClass.AUTHENTICATION
    if isinstance(error, PermissionFailure): return FailureClass.PERMISSION
    if isinstance(error, (ValueError, TypeError)): return FailureClass.INVALID_INPUT
    if isinstance(error, PermanentError): return FailureClass.PERMANENT
    return FailureClass.PERMANENT


def execute_with_retry(call: Callable[[], Any], max_retries: int = 2) -> ToolExecution:
    attempts = 0
    while True:
        attempts += 1
        try:
            return ToolExecution(result=call(), attempts=attempts, retries=attempts - 1)
        except Exception as exc:  # noqa: BLE001
            kind = classify_error(exc)
            if kind in {FailureClass.TRANSIENT, FailureClass.RATE_LIMIT} and attempts <= max_retries:
                continue
            return ToolExecution(error=str(exc), failure_class=kind, attempts=attempts, retries=attempts - 1)
