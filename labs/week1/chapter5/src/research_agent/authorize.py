"""Declarative default-deny authorization."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str


class AuthorizationEngine:
    def __init__(self, policy: dict):
        self.rules = {rule["tool"]: rule["effect"] for rule in policy.get("rules", [])}
        self.default = policy.get("default", "deny")

    def authorize(self, tool: str, arguments: dict) -> AuthorizationDecision:
        effect = self.rules.get(tool, self.default)
        return AuthorizationDecision(
            effect == "allow", "allowed" if effect == "allow" else "permission_denied"
        )
