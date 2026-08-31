# pyright: reportMissingImports=false
from __future__ import annotations

import random
from decimal import Decimal

from .models import GroundTruth, Realization, Scenario


def _money(value: object) -> str:
    return f"{Decimal(str(value)):,.2f}"


class TemplateRealizer:
    def realize(self, scenario: Scenario, truth: GroundTruth, rng: random.Random) -> Realization:
        f = scenario.fields
        intent = scenario.category
        principal, rate = f.get("principal"), f.get("annual_rate")
        term = f.get("term_years") or (Decimal(str(f["payments"])) / 12 if f.get("payments") else None)
        payment = f.get("payment")
        if intent == "payment":
            options = [f"What is the monthly payment on a ${_money(principal)} mortgage at {rate}% for {term} years?", f"Calculate the payment for ${_money(principal)} at {rate}% over {term} years."]
        elif intent == "principal":
            options = [f"I can afford ${_money(payment)} per month at {rate}% for {term} years. How much can I borrow?"]
        elif intent == "rate":
            options = [f"What annual interest rate gives a ${_money(payment)} payment on ${_money(principal)} for {term} years?"]
        elif intent == "term":
            options = [f"How long will it take to repay ${_money(principal)} at {rate}% with payments of ${_money(payment)}?"]
        else:
            options = ["What is the mortgage outcome?"]
        question = options[rng.randrange(len(options))]
        return Realization(question, "template", f"{intent}_01", None, None)
