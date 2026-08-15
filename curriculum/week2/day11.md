## Day 11 — Security

Deep dive:

* authentication
* authorization
* secrets
* least privilege
* sandboxing
* prompt injection
* indirect prompt injection
* tool poisoning
* data leakage
* supply-chain attacks
* model output validation

Particularly:

### Agent security

Never give an agent unrestricted capabilities.

Design:

```text
Agent
 ↓
Policy layer
 ↓
Tool authorization
 ↓
Sandbox
 ↓
External system
```

Then try attacking your own system.

---