# pyright: reportMissingImports=false

from mortgage.tool import calculate_mortgage_tool


def test_tool_serializes_decimal_fields_as_strings():
    payload = calculate_mortgage_tool(
        {"principal": "100000", "periodic_rate": "0", "payments": 100, "payment": None}
    )
    assert payload["ok"] is True
    assert isinstance(payload["result"]["principal"], str)
    assert isinstance(payload["result"]["payments"], int)
    assert payload["metadata"]["schema_version"] == "0.2"


def test_invalid_tool_request_is_an_error_envelope():
    payload = calculate_mortgage_tool({"principal": "100", "payments": 10})
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_QUANTITY_COUNT"


def test_tool_rejects_non_finite_decimal():
    payload = calculate_mortgage_tool(
        {"principal": "NaN", "periodic_rate": "0", "payments": 10, "payment": None}
    )
    assert payload["ok"] is False
    assert payload["error"]["code"] == "TOOL_ERROR"
