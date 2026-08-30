"""coding_agent -- a minimal coding agent harness (ch15 / SPEC).

The deterministic core (sandbox, control_loop, context, tools, permissions,
verifier, instrument, report) is LLM- and network-free (R-15 / I-009): it
embeds *only* the model through the :class:`~coding_agent.policy.Policy`
interface. The offline `MockPolicy` makes the whole suite reproducible without
Ollama or the network (R-13 / K-06); the opt-in `OllamaPolicy` is the sole
module that MAY reach the model.

See SPEC.md (section 4 contracts, section 6 invariants, section 9 tests) for
the authoritative behavior.
"""

__version__ = "0.1"

__all__ = ["__version__"]
