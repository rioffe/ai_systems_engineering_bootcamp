# R-16 / R-17 / I-012 / F-006: the single artifact writer + schema-gated loader.
#
# `report.py` is IN the I-009 LLM/network-free core list. It is the ONLY module that
# serializes a durable artifact (R-16 -- no subcommand prints its own ad-hoc
# serialization): `canonical_json` is the one, byte-deterministic form (I-002).
# Every load goes through the "0.1" schema gate (R-17/I-012): a malformed or
# schema-invalid artifact is a deterministic LoadError (E-05), never a silent
# partial read; a `*_version` mismatch is a VersionMismatch unless `force`
# (E-06). `render_summary` is the offline inspect view (T-08); `compare` is the
# F-006 regression delta over two versioned trajectory artifacts.

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from ._version import EXPERIMENT_VERSION, TRAJECTORY_VERSION

# The schemas ship with the lab at <lab_root>/schemas (two levels above this package).
_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"


# E-05: a malformed / missing / schema-invalid artifact.
class LoadError(Exception):
    name = "LOAD_ERROR"


# E-06: a `*_version` that does not match the pinned "0.1" gate.
class VersionMismatch(Exception):
    name = "VERSION_MISMATCH"


# R-16: the single canonical serialization. sort_keys + fixed indent + trailing
# newline make it a pure function of the document (I-002 byte-identity).
def canonical_json(doc) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_json(path, doc) -> None:
    # R-16: the ONLY writer of durable artifacts.
    Path(path).write_text(canonical_json(doc), encoding="utf-8")


def _load_schema(name: str) -> dict:
    # A missing/corrupt schema is a deterministic load error (E-05), never a crash.
    try:
        with open(_SCHEMA_DIR / name, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LoadError(f"could not load schema {name!r}: {exc}") from exc
    if not isinstance(doc, dict):
        raise LoadError(f"schema {name!r} is not a JSON object")
    return doc


# E-05: parse a JSON-object artifact; every failure mode is a LoadError.
def load_json(path) -> dict:
    p = Path(path)
    try:
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        raise LoadError(f"artifact not found: {p}") from None
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        raise LoadError(f"malformed artifact {p}: {exc}") from exc
    if not isinstance(doc, dict):
        raise LoadError(f"artifact {p} is not a JSON object")
    return doc


def _check_version(doc: dict, field: str, expected: str, *, force: bool) -> None:
    # E-06: refuse a mismatched `*_version` unless force (R-17).
    if force:
        return
    actual = doc.get(field)
    if actual != expected:
        raise VersionMismatch(
            f"{field} {actual!r} != expected {expected!r} (E-06); pass --force to bypass"
        )


def _validate(doc: dict, schema: dict, path) -> None:
    # I-012: the "0.1" schema gate on every read.
    try:
        jsonschema.validate(doc, schema)
    except jsonschema.ValidationError as exc:
        raise LoadError(f"artifact {path} fails the 0.1 schema: {exc.message}") from exc


# R-17/I-012: load + version-gate + schema-validate a trajectory artifact.
def load_trajectory(path, *, force: bool = False) -> dict:
    doc = load_json(path)
    _check_version(doc, "trajectory_version", TRAJECTORY_VERSION, force=force)
    _validate(doc, _load_schema("trajectory.json"), path)
    return doc


# R-17/I-012: load + version-gate + schema-validate an experiment artifact.
def load_experiment(path, *, force: bool = False) -> dict:
    doc = load_json(path)
    _check_version(doc, "experiment_version", EXPERIMENT_VERSION, force=force)
    _validate(doc, _load_schema("experiment.json"), path)
    return doc


# T-08: the offline inspect render -- a human summary of a loaded trajectory.
def render_summary(doc: dict) -> str:
    lines = [
        f"task:          {doc['task_id']}",
        f"policy:        {doc['policy']}",
        f"final_outcome: {doc['final_outcome']}",
        f"iterations:    {doc['iterations_used']}",
        f"total_tokens:  {doc['total_tokens']['estimated']} ({doc['total_tokens']['mode']})",
    ]
    if doc.get("availability_banner"):
        lines.append(f"banner:        {doc['availability_banner']}")
    for row in doc.get("iterations", []):
        calls = ", ".join(c["name"] for c in row["tool_calls"]) or "-"
        lines.append(
            f"  iter {row['iteration']}: {calls}  verdict={row['verdict']}  phase={row['phase']}"
        )
    return "\n".join(lines)


# F-006: outcome ranks -- lower is better. VERIFIED is the only success.
_OUTCOME_RANK = {
    "VERIFIED": 0,
    "BUDGET_EXHAUSTED": 1,
    "STALLED:NOOP": 2,
    "STALLED:BUDGET": 3,
    "DENIED_LOOP": 4,
    "ERROR": 5,
}


# F-006: the regression delta over two versioned trajectory artifacts. A
# regression is a worse terminal outcome, or -- both VERIFIED -- more iterations.
def compare(baseline: dict, current: dict) -> dict:
    def pick(doc: dict) -> dict:
        return {
            "final_outcome": doc["final_outcome"],
            "iterations_used": doc["iterations_used"],
            "total_tokens": doc["total_tokens"]["estimated"],
        }

    b, c = pick(baseline), pick(current)
    worse_outcome = _OUTCOME_RANK[c["final_outcome"]] > _OUTCOME_RANK[b["final_outcome"]]
    more_work = (
        b["final_outcome"] == "VERIFIED"
        and c["final_outcome"] == "VERIFIED"
        and c["iterations_used"] > b["iterations_used"]
    )
    return {
        "compare_version": "0.1",
        "baseline": b,
        "current": c,
        "delta": {
            "iterations_used": c["iterations_used"] - b["iterations_used"],
            "total_tokens": c["total_tokens"] - b["total_tokens"],
            "final_outcome": c["final_outcome"],
        },
        "regression": worse_outcome or more_work,
    }


__all__ = [
    "LoadError",
    "VersionMismatch",
    "canonical_json",
    "compare",
    "load_experiment",
    "load_json",
    "load_trajectory",
    "render_summary",
    "write_json",
]
