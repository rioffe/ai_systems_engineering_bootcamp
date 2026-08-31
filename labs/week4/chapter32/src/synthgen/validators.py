# pyright: reportMissingImports=false
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from .models import ExtractionResult, GroundTruth, Realization, Scenario, ValidationResult
from .spec import DatasetSpecification

_NUMBER = r"(?:\$?([0-9][0-9,]*(?:\.[0-9]+)?)\s*(k|m)?|([0-9]+(?:\.[0-9]+)?)\s*%)"


def _number(text: str) -> Decimal:
    match = re.search(_NUMBER, text, re.I)
    if not match:
        raise ValueError("numeric value not found")
    value = Decimal((match.group(1) or match.group(3)).replace(",", ""))
    suffix = (match.group(2) or "").lower()
    return value * (1000 if suffix == "k" else 1000000 if suffix == "m" else 1)


def normalize_question(question: str) -> str:
    return " ".join(question.casefold().split())


def extract_question(question: str, spec: DatasetSpecification) -> ExtractionResult:
    fields: dict[str, object] = {}
    lower = question.casefold()
    if "how long" in lower or "term" in lower or "take to repay" in lower:
        fields["intent"] = "term"
    elif "how much can i borrow" in lower or "principal" in lower:
        fields["intent"] = "principal"
    elif "interest rate" in lower or "annual rate" in lower:
        fields["intent"] = "rate"
    elif "payment" in lower or "monthly" in lower:
        fields["intent"] = "payment"
    patterns = {"principal": r"\$[0-9][0-9,]*(?:\.[0-9]+)?(?:\s*[km])?", "payment": r"(?:payments? of|afford)\D+\$?[0-9][0-9,]*(?:\.[0-9]+)?", "annual_rate": r"[0-9]+(?:\.[0-9]+)?\s*%", "term_years": r"[0-9]+(?:\.[0-9]+)?\s*(?:year|yr)"}
    intent = fields.get("intent")
    wanted = {"payment": ("principal", "annual_rate", "term_years"), "principal": ("payment", "annual_rate", "term_years"), "term": ("principal", "annual_rate", "payment"), "rate": ("principal", "payment", "term_years")}.get(intent if isinstance(intent, str) else "", tuple(patterns))
    for label in wanted:
        pattern = patterns[label]
        match = re.search(pattern, question, re.I)
        if match:
            try:
                fields[label] = _number(match.group(0))
            except ValueError:
                pass
    unsupported = [term for term in ("tax", "insurance", "hoa", "adjustable", "lender advice") if term in lower]
    reasons = tuple([f"unsupported scope: {term}" for term in unsupported] + (["intent not found"] if "intent" not in fields else []))
    return ExtractionResult(not reasons, fields, reasons)


def _equal(left: object, right: object) -> bool:
    try:
        return Decimal(str(left)).quantize(Decimal("0.01")) == Decimal(str(right)).quantize(Decimal("0.01"))
    except (ArithmeticError, ValueError, TypeError):
        return left == right


def validate_candidate(scenario: Scenario, truth: GroundTruth, realization: Realization, spec: DatasetSpecification) -> ValidationResult:
    reasons: list[str] = []
    if not realization.question.strip():
        reasons.append("question is empty")
    extracted = extract_question(realization.question, spec)
    reasons.extend(extracted.reasons)
    if extracted.fields.get("intent") != scenario.category:
        reasons.append("intent mismatch")
    for name in ("principal", "annual_rate", "term_years", "payment"):
        if name in scenario.fields and name in extracted.fields and not _equal(scenario.fields[name], extracted.fields[name]):
            reasons.append(f"{name} mismatch")
    return ValidationResult(not reasons, "semantic" if reasons else "schema", tuple(dict.fromkeys(reasons)), extracted.fields)
