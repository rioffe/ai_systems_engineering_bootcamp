# pyright: reportMissingImports=false

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import sys
from typing import Sequence

from .llm import MockLLMAdapter
from .models import CalculationRequest
from .presentation import to_json, to_text
from .service import calculate


def _decimal(value: str, name: str) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{name} must be finite")
    return result


def _request(args: argparse.Namespace, *, include_schedule: bool) -> CalculationRequest:
    if args.payments is not None and args.term_years is not None:
        raise ValueError("--payments and --term-years are mutually exclusive")
    principal = _decimal(args.principal, "principal") if args.principal is not None else None
    payment = _decimal(args.payment, "payment") if args.payment is not None else None
    rate = _decimal(args.rate, "rate") if args.rate is not None else None
    periodic_rate = None
    if rate is not None:
        if args.rate_period == "annual":
            rate /= Decimal(100) * Decimal(12)
        else:
            periodic_rate = rate
        periodic_rate = periodic_rate if periodic_rate is not None else rate
    payments = args.payments
    if args.term_years is not None:
        term_years = _decimal(args.term_years, "term-years")
        candidate = term_years * Decimal(12)
        if candidate != candidate.to_integral_value():
            raise ValueError("term-years must convert to a whole number of monthly payments")
        try:
            payments = int(candidate)
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise ValueError("term-years must convert to an integer number of payments") from exc
    if args.rounding_places < 0 or args.rounding_places > 10:
        raise ValueError("rounding-places must be between 0 and 10")
    return CalculationRequest(principal, periodic_rate, payments, payment, include_schedule, args.rounding_places)


def _add_calculation_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--principal")
    parser.add_argument("--rate")
    parser.add_argument("--rate-period", choices=("annual", "monthly"), default="annual")
    parser.add_argument("--payments", type=int)
    parser.add_argument("--term-years")
    parser.add_argument("--payment")
    parser.add_argument("--include-schedule", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--rounding-places", type=int, default=2)


def _exit_for_error(code: str) -> int:
    if code in {"UNSUPPORTED_SCOPE"}:
        return 4
    if code in {"SOLVER_CONVERGENCE", "TOOL_ERROR"}:
        return 3
    if code in {"MODEL_ERROR"}:
        return 5
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mortgage")
    subparsers = parser.add_subparsers(dest="command", required=True)
    calculate_parser = subparsers.add_parser("calculate")
    _add_calculation_args(calculate_parser)
    ask_parser = subparsers.add_parser("ask")
    ask_parser.add_argument("--adapter", choices=("mock", "real"), default="mock")
    ask_parser.add_argument("text")
    amortize_parser = subparsers.add_parser("amortize")
    _add_calculation_args(amortize_parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "ask":
            if args.adapter == "real":
                print("Error [MODEL_ERROR]: real model adapter is not configured", file=sys.stderr)
                return 5
            response = MockLLMAdapter().ask(args.text)
            if response.interpretation.clarification and response.result is None and response.error is None:
                print(response.interpretation.clarification)
                return 0
            if response.error is not None:
                print(f"Error [{response.error['code']}]: {response.error['message']}")
                return _exit_for_error(response.error["code"])
            print(response.explanation)
            print("Estimate for principal and interest only; not a lender-specific quote or financial advice.")
            return 0

        request = _request(args, include_schedule=args.command == "amortize" or args.include_schedule)
        payload = calculate(request, adapter="direct")
        if args.format == "json":
            print(to_json(payload))
        else:
            print(to_text(payload))
        return 0 if payload["ok"] else _exit_for_error(payload["error"].code)
    except (TypeError, ValueError) as exc:
        print(f"Error [USAGE]: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
