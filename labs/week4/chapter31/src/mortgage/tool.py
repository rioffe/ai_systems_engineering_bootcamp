# pyright: reportMissingImports=false

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from decimal import Decimal
from typing import Any, cast

from .models import CalculationError, CalculationResult, ResponseMetadata
from .service import calculate, parse_decimal


def _serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite Decimal cannot be serialized")
        return format(value, "f")
    if is_dataclass(value):
        return {key: _serialize(item) for key, item in asdict(cast(Any, value)).items()}
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def calculate_mortgage_tool(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        payments = payload.get("payments")
        if payments is not None and (isinstance(payments, bool) or not isinstance(payments, int)):
            raise ValueError("payments must be an integer")
        from .models import CalculationRequest

        request = CalculationRequest(
            principal=parse_decimal(payload.get("principal"), "principal"),
            periodic_rate=parse_decimal(payload.get("periodic_rate"), "periodic_rate"),
            payments=payments,
            payment=parse_decimal(payload.get("payment"), "payment"),
            include_schedule=bool(payload.get("include_schedule", False)),
        )
    except (TypeError, ValueError) as exc:
        error = CalculationError("TOOL_ERROR", str(exc))
        return _serialize({"ok": False, "result": None, "error": error, "metadata": ResponseMetadata(adapter="direct")})
    return _serialize(calculate(request, adapter="direct"))
