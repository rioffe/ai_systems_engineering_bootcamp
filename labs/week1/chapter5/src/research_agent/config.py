"""Strict budgets and authorization configuration."""
# pyright: reportMissingImports=false
from __future__ import annotations

from pathlib import Path
from typing import Any

from .schema import load_yaml

DEFAULT_BUDGETS = {
    "max_steps": 10,
    "max_tokens": 20000,
    "max_cost_usd": 0.50,
    "max_seconds": 120,
    "max_retries": 2,
    "repeat_threshold": 3,
    "max_consecutive_failures": 3,
}


class ConfigError(ValueError):
    pass


def _load(path: str | Path | None, schema: str, default: dict[str, Any]) -> dict[str, Any]:
    if path is None:
        return dict(default)
    try:
        return load_yaml(path, schema)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def load_budgets(path: str | Path | None = None) -> dict[str, Any]:
    values = _load(path, "budgets", DEFAULT_BUDGETS)
    unknown = set(values) - set(DEFAULT_BUDGETS)
    if unknown:
        raise ConfigError(f"unknown budget keys: {', '.join(sorted(unknown))}")
    return {**DEFAULT_BUDGETS, **values}


def load_policy(path: str | Path | None = None) -> dict[str, Any]:
    default = {"version": 1, "rules": [
        {"tool": "search", "effect": "allow"},
        {"tool": "retrieve", "effect": "allow"},
        {"tool": "delete_file", "effect": "deny"},
    ], "default": "deny"}
    return _load(path, "policy", default)
