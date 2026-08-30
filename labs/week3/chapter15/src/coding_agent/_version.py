"""Pinned version of every durable artifact (R-17 / I-012).

Both `trajectory.json` (C-06) and `experiment.json` (C-07) carry a literal
`*_version == "0.1"` and are validated against `schemas/*.json` on every read;
a mismatch is a deterministic load error (E-05/E-06) unless bypassed with
`--force`.
"""

TRAJECTORY_VERSION = "0.1"
EXPERIMENT_VERSION = "0.1"

__all__ = ["EXPERIMENT_VERSION", "TRAJECTORY_VERSION"]
