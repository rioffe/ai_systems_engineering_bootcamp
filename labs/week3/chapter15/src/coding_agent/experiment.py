# R-11 / C-07 / C-09 / I-013: the section-17 failure-injection experiment.
#
# `experiment.py` is LLM/network-free (it drives the loop over a scripted
# `MockPolicy`, so it belongs to the deterministic core even though it is outside
# the I-009 eight-module scan list). It orchestrates the pinned `parse-config`
# arc:
#
#   1. the C-09 fixture is copied into a sandbox (the caller owns that copy);
#   2. `inject_defect` corrupts the pinned token (the canonical defect);
#   3. the deterministic loop runs over a scripted detect -> diagnose -> repair
#      `MockPolicy` (I-014: one policy, one thread, one action batch per
#      iteration);
#   4. the C-07 `experiment.json` doc is derived from the trajectory: the
#      detect / diagnose / repair phase markers and the PINNED
#      `iterations_to_verified == 3` (I-013), not "whatever the model did".
#
# The C-07 doc is built here and written by report.py (R-16); it is a pure
# function of the trajectory, so it is byte-identical across runs (I-013).

from __future__ import annotations

from dataclasses import dataclass

from ._version import EXPERIMENT_VERSION
from .control_loop import run
from .policy import NOOP, MockPolicy, ToolCall
from .tools import EditResult
from .verifier import STATUS_FAILED, STATUS_VERIFIED, Verdict

# The closed experiment phase vocabulary (C-07): the detect/diagnose/repair arc.
PHASE_DETECT = "detect"
PHASE_DIAGNOSE = "diagnose"
PHASE_REPAIR = "repair"


# C-09: the pinned canonical defect for the parse-config experiment (I-013).
# `old` is the CORRECT token (present in the good fixture); `new` is the BUGGY
# token that is injected. The repair is the exact reversal (`new` -> `old`).
# Injecting `delimiter in line` inverts the blank-line filter so every key=value
# line is skipped -> `test_parse_basic` FAILS.
@dataclass(frozen=True)
class DefectSpec:
    file: str                 # path to corrupt, relative to the sandbox root
    symbol: str               # the symbol under test (for the C-07 record)
    injected_defect: str      # human description of the injected defect
    old: str                  # the correct token (replaced by `new` on injection)
    new: str                  # the buggy token (injected; reversed on repair)
    pre_injection_verdict: str = "FAILED"


PARSE_CONFIG_DEFECT = DefectSpec(
    file="repo/config.py",
    symbol="parse_config",
    injected_defect="inverted blank-line filter: key=value lines are skipped",
    old="delimiter not in line",
    new="delimiter in line",
    pre_injection_verdict="FAILED",
)


# A defect that could not be injected (its `old` token is absent from the file).
class InjectionError(Exception):
    name = "INJECTION_FAILED"


# The outcome of one experiment run: the terminal label, its exit code, the
# pinned iteration-to-VERIFIED count, the C-07 experiment doc, and the C-06
# trajectory it was derived from.
@dataclass(frozen=True)
class ExperimentResult:
    final_outcome: str
    exit_code: int
    iterations_to_verified: int
    experiment: dict
    trajectory: dict
    verdict: Verdict | None = None


def inject_defect(controller, defect: DefectSpec) -> EditResult:
     # Corrupt the pinned token: replace `defect.old` (correct) with `defect.new`
     # (buggy). A missing `old` token is a deterministic InjectionError, never a
     # silent no-op.
    # opengrep `auto` SQL-injection heuristic misfires on `controller.execute(...)`:
    # this is the permission-gated ToolController dispatcher (C-03/C-04); no SQL.
    result = controller.execute(  # nosemgrep
        ToolCall("edit_file", {"path": defect.file, "op": "replace",
                               "old": defect.old, "new": defect.new})
    )
    if not (isinstance(result, EditResult) and result.applied):
        raise InjectionError(f"defect injection failed for {defect.file}: {result.detail}")
    return result


# Build the scripted detect -> diagnose -> repair MockPolicy (I-014). Iteration
# 1 detects (the canonical verifier returns FAILED over the injected defect),
# iteration 2 diagnoses (read_file + search the failing module), iteration 3
# repairs (the edit_file that reverses the defect).
def repair_arc_policy(defect: DefectSpec, *, probe_file: str, probe_query: str) -> MockPolicy:
    script = [
            [NOOP()],
            [ToolCall("read_file", {"path": probe_file}),
             ToolCall("search", {"query": probe_query})],
            [ToolCall("edit_file", {"path": defect.file, "op": "replace",
                                    "old": defect.new, "new": defect.old})],
         ]
    return MockPolicy(script)


# Derive the C-07 detect/diagnose/repair phase markers from a C-06 trajectory.
# detect = the first FAILED verdict; diagnose = the first read/search/list
# investigation after detect and before repair; repair = the first applied
# edit_file. Pure over the trajectory -> deterministic (I-013).
def derive_phases(trajectory: dict) -> list[dict]:
    detect = diagnose = repair = None
    for row in trajectory["iterations"]:
        it = row["iteration"]
        names = [tc["name"] for tc in row["tool_calls"]]
        verdict = row["verdict"]
        if detect is None and verdict == STATUS_FAILED:
            detect = it
        if (diagnose is None and detect is not None and repair is None
                and any(n in ("read_file", "search", "list_files") for n in names)):
            diagnose = it
        if repair is None and "edit_file" in names and row["files_modified"]:
            repair = it
    phases = []
    if detect is not None:
        r = next(x for x in trajectory["iterations"] if x["iteration"] == detect)
        tr = r["test_results"] or {}
        phases.append({
            "phase": PHASE_DETECT, "iteration": detect,
            "evidence": f"verdict {verdict if False else r['verdict']}: "
                        f"{tr.get('failed', 0)} of {tr.get('passed', 0) + tr.get('failed', 0)} check(s) failed",
         })
    if diagnose is not None:
        phases.append({
            "phase": PHASE_DIAGNOSE, "iteration": diagnose,
            "evidence": "read_file + search over the failing module",
         })
    if repair is not None:
        r = next(x for x in trajectory["iterations"] if x["iteration"] == repair)
        phases.append({
            "phase": PHASE_REPAIR, "iteration": repair,
            "evidence": f"edit_file applied to {r['files_modified'][0]}",
         })
    return phases


def _iterations_to_verified(trajectory: dict) -> int:
     # The 1-based iteration whose verdict first reached VERIFIED (0 if never).
    for row in trajectory["iterations"]:
        if row["verdict"] == STATUS_VERIFIED:
            return row["iteration"]
    return 0


# Build the C-07 experiment.json document (versioned). Pure over its inputs ->
# byte-identical across runs (I-013).
def build_experiment_doc(*, task, defect: DefectSpec, phases: list, final_outcome: str,
                         iterations_to_verified: int,
                         trajectory_ref: str = "trajectory.json") -> dict:
    return {
            "experiment_version": EXPERIMENT_VERSION,
            "task_id": task.task_id,
            "injection": {
                "file": defect.file,
                "symbol": defect.symbol,
                "injected_defect": defect.injected_defect,
                "pre_injection_verdict": defect.pre_injection_verdict,
            },
            "phases": phases,
            "final_outcome": final_outcome,
            "iterations_to_verified": iterations_to_verified,
            "trajectory_ref": trajectory_ref,
         }


def _experiment_exit(final_outcome: str) -> int:
     # experiment exit partition: 0 VERIFIED / 1 did-not-reach-VERIFIED /
     # 5 core-ERROR (4 PULL_REQUIRED and 2 usage are resolved at the CLI layer).
    if final_outcome == "VERIFIED":
        return 0
    if final_outcome == "ERROR":
        return 5
    return 1


def run_experiment(
    *,
    task,
    defect: DefectSpec,
    policy,
    pconfig,
    controller,
    sandbox_root: str,
    context,
    verify=None,
    max_iterations: int = 8,
    max_consecutive_errors: int = 2,
    trajectory_ref: str = "trajectory.json",
    policy_name: str = "mock",
    availability_banner: str | None = None,
) -> ExperimentResult:
     # The section-17 arc: inject the defect, run the bounded loop, and derive
     # the C-07 record from the trajectory.
    inject_defect(controller, defect)
    result = run(
        task=task,
        policy=policy,
        pconfig=pconfig,
        controller=controller,
        sandbox_root=sandbox_root,
        context=context,
        verify=verify,
        max_iterations=max_iterations,
        max_consecutive_errors=max_consecutive_errors,
        policy_name=policy_name,
        availability_banner=availability_banner,
       )
    phases = derive_phases(result.trajectory)
    itv = _iterations_to_verified(result.trajectory)
    doc = build_experiment_doc(
        task=task,
        defect=defect,
        phases=phases,
        final_outcome=result.final_outcome,
        iterations_to_verified=itv,
        trajectory_ref=trajectory_ref,
       )
    return ExperimentResult(
        final_outcome=result.final_outcome,
        exit_code=_experiment_exit(result.final_outcome),
        iterations_to_verified=itv,
        experiment=doc,
        trajectory=result.trajectory,
        verdict=result.verdict,
    )


__all__ = [
    "PARSE_CONFIG_DEFECT",
    "PHASE_DETECT",
    "PHASE_DIAGNOSE",
    "PHASE_REPAIR",
    "DefectSpec",
    "ExperimentResult",
    "InjectionError",
    "build_experiment_doc",
    "derive_phases",
    "inject_defect",
    "repair_arc_policy",
    "run_experiment",
]
