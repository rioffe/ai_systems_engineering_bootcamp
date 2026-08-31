# pyright: reportMissingImports=false
import json
import random
from decimal import Decimal
from pathlib import Path

import pytest

from synthgen.constraints import compile_constraint
from synthgen.distributions import build_distribution
from synthgen.spec import load_spec


def test_load_spec_and_seeded_distribution(tmp_path):
    p = tmp_path / "spec.yaml"
    p.write_text("""dataset:\n  name: demo\n  domain: mortgage\n  size: 2\ncategories:\n  payment:\n    weight: 1.0\nschema:\n  fields:\n    - {name: principal, type: decimal, required: true, nullable: false}\n""")
    spec = load_spec(p)
    assert spec.dataset.name == "demo"
    d = build_distribution({"distribution": "values", "values": [10, 20]})
    assert d.sample(random.Random(2)) == d.sample(random.Random(2))


def test_safe_constraint_supports_arithmetic_and_rejects_calls():
    constraint = compile_constraint("payment > principal * annual_rate / 12")
    assert constraint({"payment": Decimal("10"), "principal": Decimal("100"), "annual_rate": Decimal("1")})[0]
    with pytest.raises(Exception):
        compile_constraint("__import__('os').system('x')")


def test_spec_rejects_bad_yaml(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("dataset: [")
    with pytest.raises(Exception):
        load_spec(p)
