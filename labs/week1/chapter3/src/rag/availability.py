"""Model-availability outcome taxonomy (E-13 / R-19 / F-013).

On the REAL path the app resolves to EXACTLY ONE of three mutually-exclusive
outcomes, each a DISTINCT canonical banner + exit code, before any work.
--mock short-circuits to DEGRADED_MOCK. This is the ch1/ch2 F-003 analog:
one boolean with one banner is wrong; distinct conditions need distinct
outcomes, and the two failure outcomes never collide so a human never
misreads why a mock ran.

    DEGRADED_MOCK  daemon UNREACHABLE -> mock doubles, banner, exit 0
    PULL_REQUIRED  daemon reachable, model MISSING -> remediation, exit 4 (no crash)
    RUN_REAL       daemon reachable, model PULLED  -> real, no banner, exit 0
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Distinct canonical banners (E-13); ASCII to stay formatter/encoding-robust.
DEGRADED_MOCK_BANNER = "[REAL>MOCK] Ollama unreachable; running deterministic mock doubles"
PULL_REQUIRED_BANNER = "MODEL_MISSING: run ollama pull {m} -- or pass --mock"


class Availability(Enum):
    DEGRADED_MOCK = "DEGRADED_MOCK"
    PULL_REQUIRED = "PULL_REQUIRED"
    RUN_REAL = "RUN_REAL"


@dataclass(frozen=True)
class Outcome:
    # exactly one canonical availability outcome for this run
    kind: Availability
    use_mock: bool  # True for DEGRADED_MOCK (fall back to doubles)
    exit_code: int  # 0 on success/degrade; 4 on PULL_REQUIRED
    banner: str | None  # None for RUN_REAL; canonical banner otherwise
    missing_models: tuple = ()  # populated only for PULL_REQUIRED


def _probe(daemon_url: str, timeout: float) -> tuple[bool, set]:
    # (reachable, set_of_pulled_model_names); any failure -> unreachable (DEGRADED_MOCK).
    try:
        import httpx

        resp = httpx.get(daemon_url + "/api/tags", timeout=timeout)
        resp.raise_for_status()
        names: set = set()
        for m in resp.json().get("models") or []:
            nid = m.get("name") or m.get("model")
            if nid:
                names.add(nid)
        return (True, names)
    except Exception:  # noqa: BLE001 -- unreachable daemon / no httpx / transient
        return (False, set())


def resolve_availability(
    requested_models, daemon_url="http://localhost:11434", mock=False, timeout: float = 3.0
) -> Outcome:
    # Resolve the EXACT one canonical availability outcome (R-19 / F-013).
    if mock:
        return Outcome(Availability.DEGRADED_MOCK, True, 0, DEGRADED_MOCK_BANNER)
    reachable, present = _probe(daemon_url, timeout)
    if not reachable:
        return Outcome(Availability.DEGRADED_MOCK, True, 0, DEGRADED_MOCK_BANNER)
    missing = tuple(m for m in requested_models if m not in present)
    if missing:
        banner = "; ".join(PULL_REQUIRED_BANNER.format(m=m) for m in missing)
        return Outcome(Availability.PULL_REQUIRED, False, 4, banner, missing)
    return Outcome(Availability.RUN_REAL, False, 0, None)
