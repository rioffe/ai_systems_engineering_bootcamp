# pyright: reportMissingImports=false
from __future__ import annotations

import math
import random
from decimal import Decimal
from typing import Any, Mapping, Protocol

from .errors import SpecificationError


class Distribution(Protocol):
    def sample(self, rng: random.Random) -> object: ...


class _Values:
    def __init__(self, values: list[Any], weights: list[float] | None = None):
        if not values:
            raise SpecificationError("distribution values must be finite and non-empty")
        self.values, self.weights = values, weights

    def sample(self, rng: random.Random) -> object:
        return rng.choices(self.values, weights=self.weights, k=1)[0] if self.weights else self.values[rng.randrange(len(self.values))]


class _Uniform:
    def __init__(self, minimum: Any, maximum: Any):
        self.minimum, self.maximum = Decimal(str(minimum)), Decimal(str(maximum))
        if not self.minimum.is_finite() or not self.maximum.is_finite() or self.minimum >= self.maximum:
            raise SpecificationError("uniform requires finite min < max")

    def sample(self, rng: random.Random) -> Decimal:
        return self.minimum + (self.maximum - self.minimum) * Decimal(str(rng.random()))


class _Lognormal:
    def __init__(self, mu: Any, sigma: Any, minimum: Any = None, maximum: Any = None):
        try:
            self.mu, self.sigma = float(mu), float(sigma)
        except (TypeError, ValueError, OverflowError) as exc:
            raise SpecificationError("lognormal parameters must be numeric") from exc
        self.minimum = Decimal(str(minimum)) if minimum is not None else None
        self.maximum = Decimal(str(maximum)) if maximum is not None else None
        if not math.isfinite(self.mu) or not math.isfinite(self.sigma) or self.sigma <= 0:
            raise SpecificationError("lognormal requires finite mu and sigma > 0")
        if self.minimum is None and self.maximum is None:
            raise SpecificationError("lognormal requires finite bounds")

    def sample(self, rng: random.Random) -> Decimal:
        value = Decimal(str(math.exp(rng.normalvariate(self.mu, self.sigma))))
        if self.minimum is not None and value < self.minimum:
            value = self.minimum
        if self.maximum is not None and value >= self.maximum:
            value = self.maximum
        return value


def build_distribution(config: Mapping[str, Any]) -> Distribution:
    method = config.get("distribution")
    if method in {"values", "choice"}:
        values = list(config.get("values", ()))
        weights = config.get("weights")
        if weights is not None:
            try:
                weights = [float(x) for x in weights]
            except (TypeError, ValueError, OverflowError) as exc:
                raise SpecificationError("distribution weights must be numeric") from exc
            if len(weights) != len(values) or any(x <= 0 for x in weights):
                raise SpecificationError("distribution weights must match positive values")
        return _Values(values, weights)
    if method == "uniform":
        return _Uniform(config.get("min"), config.get("max"))
    if method == "lognormal":
        return _Lognormal(config.get("mu"), config.get("sigma"), config.get("min"), config.get("max"))
    raise SpecificationError(f"unknown distribution: {method}")


def allocate_category(rng: random.Random, categories: Mapping[str, Any]) -> str:
    draw = rng.random()
    cumulative = 0.0
    last = next(iter(categories))
    for name, category in categories.items():
        try:
            weight = float(category.weight if hasattr(category, "weight") else category.get("weight", 0))
        except (TypeError, ValueError, OverflowError) as exc:
            raise SpecificationError("category weight must be numeric") from exc
        cumulative += weight
        last = name
        if draw < cumulative:
            return name
    return last
