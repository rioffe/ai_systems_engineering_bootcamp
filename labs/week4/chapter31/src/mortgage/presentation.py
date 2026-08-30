from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from typing import Any, cast

DISCLAIMER = "Estimate for principal and interest only; not a lender-specific quote or financial advice."


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite Decimal cannot be serialized")
        return format(value, "f")
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(cast(Any, value)).items()}
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def to_json(payload: dict[str, Any]) -> str:
    data = _json_value(payload)
    data["disclaimer"] = DISCLAIMER
    return json.dumps(data, indent=2, sort_keys=True)


def to_text(payload: dict[str, Any]) -> str:
    if not payload["ok"]:
        error = payload["error"]
        return f"Error [{error.code}]: {error.message}\n{DISCLAIMER}"
    result = payload["result"]
    lines = [
        f"Principal: ${result.principal:,.2f}",
        f"Periodic rate: {result.periodic_rate}",
        f"Annual rate: {result.annual_rate * 100:.4f}%",
        f"Payments: {result.payments}",
        f"Payment: ${result.payment:,.2f}",
        f"Total paid: ${result.total_paid:,.2f}",
        f"Total interest: ${result.total_interest:,.2f}",
        DISCLAIMER,
    ]
    return "\n".join(lines)
