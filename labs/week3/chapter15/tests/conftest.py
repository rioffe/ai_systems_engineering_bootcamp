# SPEC section 9: fully offline suite (no Ollama, no sockets -- R-13 / K-06).
#
# Nothing here imports a model/network client. The Ollama client lives only in
# policy.py (lazy) behind the `Policy` interface and is never exercised by the
# default suite; T-12 injects a fake availability probe so the model-availability
# taxonomy resolves without httpx.
import os

# Keep the sandbox + tmp deterministic per run within a session so C-06's
# `sandbox_root` (and hence trajectory.json) is byte-identical (I-002 / T-09).
os.environ.setdefault("AGENT_SANDBOX_ROOT", "agent-sbx")
