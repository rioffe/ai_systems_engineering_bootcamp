# pyright: reportMissingImports=false
from __future__ import annotations

import random
from decimal import Decimal
from typing import Any

from .constraints import check_constraints
from .distributions import allocate_category, build_distribution
from .errors import ConstraintError, SpecificationError
from .models import Scenario
from .spec import DatasetSpecification


class ScenarioGenerator:
    def __init__(self, spec: DatasetSpecification):
        self.spec = spec
        self._category_map = {c.name: c for c in spec.categories}

    def sample(self, rng: random.Random, index: int) -> Scenario:
        category = allocate_category(rng, self._category_map)
        config = self._category_map[category].fields
        fields: dict[str, Any] = {}
        for descriptor in self.spec.fields:
            if descriptor.name in {"question", "intent", "expected_outcome"}:
                continue
            field_config = config.get(descriptor.name, descriptor.distribution)
            if isinstance(field_config, dict) and field_config.get("distribution"):
                fields[descriptor.name] = build_distribution(field_config).sample(rng)
            elif descriptor.name == "payments" and "term_years" in fields:
                try:
                    fields[descriptor.name] = int(Decimal(str(fields["term_years"])) * 12)
                except (ArithmeticError, ValueError, TypeError) as exc:
                    raise ConstraintError("term_years cannot produce payments") from exc
            elif descriptor.name == "intent":
                fields[descriptor.name] = category
        fields["intent"] = category
        ok, reasons = check_constraints(fields, self.spec.constraints)
        if not ok:
            raise ConstraintError("; ".join(reasons))
        return Scenario(f"{category}-{index:06d}", category, fields, str(config.get("expected_outcome", "calculated")), index)
