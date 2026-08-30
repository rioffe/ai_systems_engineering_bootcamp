# R-16 / K-01 / K-02: the `agent` CLI -- the primary product surface.
#
# `cli.py` wires the subcommands (`run`, `experiment`, `inspect`, `compare`) to the
# deterministic core and returns the F-003 exit-code partition:
#
#     0 = VERIFIED (run/experiment success)
#     1 = BUDGET_EXHAUSTED / STALLED:* / DENIED_LOOP / did-not-reach-VERIFIED
#     2 = usage error (K-01: missing flags, bad paths, unknown subcommand)
#     3 = malformed-artifact load / version mismatch (inspect/compare, E-06)
#     4 = PULL_REQUIRED (real model not pulled, E-12)
#     5 = terminal core-ERROR / unwritable sandbox (E-10)
#
# The CLI is the ONLY place that touches the network (the `--real` Ollama probe);
# the deterministic core it drives is LLM/network-free (I-009). `main(argv)` is a
# pure `argv -> int` function so the whole surface is testable offline.

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

from . import report
from .context import DEFAULT_BUDGET, ContextManager
from .control_loop import run
from .experiment import (
    PARSE_CONFIG_DEFECT,
    InjectionError,
    repair_arc_policy,
    run_experiment,
)
from .permissions import PermsConfig
from .policy import (
    NOOP,
    STOP,
    Availability,
    MockPolicy,
    ToolCall,
    resolve,
)
from .sandbox import (
    RefusedRepo,
    Sandbox,
    UnwritableRoot,
)
from .task import Task
from .tools import ToolController
from .verifier import VerifySpec

# F-003 exit-code partition (K-02).
EXIT_OK = 0
EXIT_STALLED = 1
EXIT_USAGE = 2
EXIT_ARTIFACT = 3
EXIT_PULL = 4
EXIT_ERROR = 5

# The opt-in real-model endpoint (R-14).
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "qwen3.8"


# A usage error (E-01 missing/empty task, E-07 bad --max-iterations, bad paths).
class UsageError(Exception):
    name = "USAGE"


# ---------------------------------------------------------------- helpers
def _looks_like_path(value: str) -> bool:
    return (
        "/" in value
        or "\\" in value
        or os.path.splitext(value)[1] in (".md", ".txt", ".json", ".task")
    )


def _load_task(value: str) -> str:
    # E-01: an empty task or a missing task FILE is a usage error. A plain string
    # is used as the prompt verbatim; an existing file's body is the prompt.
    if value is None or not value.strip():
        raise UsageError("task is empty (E-01)")
    if os.path.isfile(value):
        try:
            with open(value, encoding="utf-8") as fh:
                body = fh.read()
        except OSError as exc:
            raise UsageError(f"cannot read task file {value!r}: {exc}") from exc
        if not body.strip():
            raise UsageError(f"task file {value!r} is empty (E-01)")
        return body
    if _looks_like_path(value) and not os.path.exists(value):
        raise UsageError(f"task file {value!r} not found (E-01)")
    return value


def _task_id_from(value: str) -> str:
    if os.path.isfile(value):
        return os.path.splitext(os.path.basename(value))[0]
    return "task"


def _default_sandbox_root(task_id: str) -> str:
    return os.path.join(tempfile.gettempdir(), "agent-sbx", task_id)


def _load_script(path: str) -> list:
    # A --script file is a JSON list of per-iteration action batches (I-014).
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise UsageError(f"cannot read --script {path!r}: {exc}") from exc
    batches = []
    for batch in data:
        actions = []
        for a in batch:
            t = a["type"]
            if t == "tool":
                actions.append(ToolCall(a["name"], a.get("args", {})))
            elif t == "stop":
                actions.append(STOP())
            elif t == "noop":
                actions.append(NOOP())
            else:
                raise UsageError(f"unknown action type {t!r} in --script")
        batches.append(actions)
    return batches


def _mock_policy(args) -> MockPolicy:
    # The mock policy for `run`: a --script if given, else a passive [STOP] that
    # lets the canonical verifier decide (a good repo verifies in one iteration).
    if getattr(args, "script", None):
        return MockPolicy(script=_load_script(args.script))
    return MockPolicy(script=[[STOP()]])


def _probe_ollama(host: str, model: str) -> tuple:
    # The real-path availability probe: (daemon_up, model_pulled). Only called on
    # --real; a down/unreachable daemon yields (False, False) -> DEGRADED_MOCK.
    import urllib.request

    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=2) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                names = [m.get("name", "") for m in data.get("models", [])]
                pulled = any(n == model or n.startswith(model + ":") for n in names)
                return (True, pulled)
    except (OSError, ValueError):
        # A down/unreachable daemon (OSError covers URLError/timeout) or a malformed
        # response (ValueError covers JSONDecodeError) means not-available; the CLI
        # degrades to DEGRADED_MOCK (E-11) rather than failing the run.
        return (False, False)
    return (False, False)


def _resolve_policy_mode(args) -> tuple:
    # (policy, policy_name, banner, exit_code). A non-None exit_code means the run
    # should stop now (e.g. PULL_REQUIRED -> 4) without allocating a sandbox.
    if not getattr(args, "real", False):
        return (_mock_policy(args), "mock", None, None)
    res = resolve(lambda: _probe_ollama(OLLAMA_HOST, OLLAMA_MODEL), model=OLLAMA_MODEL)
    if res.availability == Availability.PULL_REQUIRED:
        print(res.remediation or "PULL_REQUIRED", file=sys.stderr)
        return (None, None, None, EXIT_PULL)
    if res.availability == Availability.RUN_REAL:
        return (res.policy, "ollama", None, None)
    # DEGRADED_MOCK: fall back to the mock policy, banner recorded (E-11).
    return (_mock_policy(args), "mock", res.banner, None)


# ---------------------------------------------------------------- subcommands
def _cmd_run(args) -> int:
    prompt = _load_task(args.task)
    if args.max_iterations < 1:
        raise UsageError(
            f"--max-iterations must be a positive integer, got {args.max_iterations} (E-07)"
        )
    task = Task(
        task_id=_task_id_from(args.task),
        prompt=prompt,
        target_repo=args.repo,
        verifier=VerifySpec(kind=args.verify_kind, command=args.verify_command),
    )
    policy, policy_name, banner, stop_code = _resolve_policy_mode(args)
    if stop_code is not None:
        return stop_code
    sandbox_root = args.sandbox or _default_sandbox_root(task.task_id)
    sb = Sandbox.create(args.repo, sandbox_root)  # E-08 RefusedRepo / E-10 UnwritableRoot
    try:
        controller = ToolController(sandbox_root)
        pconfig = PermsConfig(sandbox_root=sandbox_root)
        context = ContextManager(budget=DEFAULT_BUDGET, compact=not args.no_compact)
        result = run(
            task=task,
            policy=policy,
            pconfig=pconfig,
            controller=controller,
            sandbox_root=sandbox_root,
            context=context,
            max_iterations=args.max_iterations,
            max_consecutive_errors=args.max_consecutive_errors,
            policy_name=policy_name,
            availability_banner=banner,
        )
        report.write_json(args.out, result.trajectory)
        print(report.render_summary(result.trajectory))
        return result.exit_code
    finally:
        sb.remove()


def _cmd_experiment(args) -> int:
    # The section-17 failure-injection experiment over the pinned C-09 fixture.
    task = Task(
        task_id="parse-config",
        prompt="add a function that parses configuration",
        target_repo=args.repo,
        verifier=VerifySpec(kind="tests", command="pytest -q"),
    )
    _policy, policy_name, banner, stop_code = _resolve_policy_mode(args)
    if stop_code is not None:
        return stop_code
    sandbox_root = args.sandbox or _default_sandbox_root("parse-config")
    sb = Sandbox.create(args.repo, sandbox_root)
    try:
        controller = ToolController(sandbox_root)
        pconfig = PermsConfig(sandbox_root=sandbox_root)
        policy = repair_arc_policy(
            PARSE_CONFIG_DEFECT, probe_file=PARSE_CONFIG_DEFECT.file, probe_query="delimiter"
        )
        context = ContextManager(budget=DEFAULT_BUDGET, compact=not args.no_compact)
        res = run_experiment(
            task=task,
            defect=PARSE_CONFIG_DEFECT,
            policy=policy,
            pconfig=pconfig,
            controller=controller,
            sandbox_root=sandbox_root,
            context=context,
            max_iterations=args.max_iterations,
            policy_name=policy_name,
            availability_banner=banner,
        )
        out_dir = os.path.dirname(os.path.abspath(args.out))
        report.write_json(os.path.join(out_dir, "trajectory.json"), res.trajectory)
        report.write_json(args.out, res.experiment)
        print(
            f"experiment: {res.final_outcome} (iterations_to_verified={res.iterations_to_verified})"
        )
        return res.exit_code
    finally:
        sb.remove()


def _cmd_inspect(args) -> int:
    # T-08: load + render a saved trajectory offline; E-06 version gate.
    doc = report.load_trajectory(args.in_path, force=args.force)
    print(report.render_summary(doc))
    return EXIT_OK


def _cmd_compare(args) -> int:
    # F-006: regression delta over two versioned artifacts; E-06 version gate.
    baseline = report.load_trajectory(args.baseline, force=args.force)
    current = report.load_trajectory(args.current, force=args.force)
    rep = report.compare(baseline, current)
    report.write_json(args.out, rep)
    print(f"regression: {rep['regression']}")
    return EXIT_OK


# ---------------------------------------------------------------- parser
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent", description="Minimal coding agent harness")
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="one closed-loop run over a sandbox copy of --repo")
    p_run.add_argument("--task", required=True)
    p_run.add_argument("--repo", required=True)
    p_run.add_argument("--out", required=True)
    mode = p_run.add_mutually_exclusive_group()
    mode.add_argument("--mock", dest="real", action="store_false")
    mode.add_argument("--real", dest="real", action="store_true")
    p_run.set_defaults(real=False)
    p_run.add_argument("--max-iterations", type=int, default=8)
    p_run.add_argument("--max-consecutive-errors", type=int, default=2)
    p_run.add_argument("--no-compact", action="store_true")
    p_run.add_argument("--script", default=None)
    p_run.add_argument("--verify-kind", default="tests")
    p_run.add_argument("--verify-command", default="pytest -q")
    p_run.add_argument("--sandbox", default=None)
    p_run.set_defaults(handler=_cmd_run)

    p_exp = sub.add_parser("experiment", help="the section-17 failure-injection experiment")
    p_exp.add_argument("--task", default="parse-config")
    p_exp.add_argument("--repo", required=True)
    p_exp.add_argument("--out", required=True)
    exp_mode = p_exp.add_mutually_exclusive_group()
    exp_mode.add_argument("--mock", dest="real", action="store_false")
    exp_mode.add_argument("--real", dest="real", action="store_true")
    p_exp.set_defaults(real=False)
    p_exp.add_argument("--max-iterations", type=int, default=8)
    p_exp.add_argument("--no-compact", action="store_true")
    p_exp.add_argument("--sandbox", default=None)
    p_exp.set_defaults(handler=_cmd_experiment)

    p_insp = sub.add_parser("inspect", help="load + render a saved trajectory offline")
    p_insp.add_argument("--in", dest="in_path", required=True)
    p_insp.add_argument("--force", action="store_true")
    p_insp.set_defaults(handler=_cmd_inspect)

    p_cmp = sub.add_parser("compare", help="regression delta over two artifacts")
    p_cmp.add_argument("--baseline", required=True)
    p_cmp.add_argument("--current", required=True)
    p_cmp.add_argument("--out", default="compare_report.json")
    p_cmp.add_argument("--force", action="store_true")
    p_cmp.set_defaults(handler=_cmd_compare)

    return parser


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        # argparse uses SystemExit(0) for successful --help and SystemExit(2)
        # for invalid usage; preserve that distinction for the testable API.
        code = e.code
        if code == 0:
            return EXIT_OK
        return EXIT_USAGE if code in (None, 2) else int(code)
    if not getattr(args, "handler", None):
        parser.print_help()
        return EXIT_USAGE
    try:
        return args.handler(args)
    except UsageError as e:
        print(f"usage error: {e}", file=sys.stderr)
        return EXIT_USAGE
    except (report.LoadError, report.VersionMismatch) as e:
        print(f"artifact error: {e}", file=sys.stderr)
        return EXIT_ARTIFACT
    except RefusedRepo as e:
        print(f"refused: {e}", file=sys.stderr)
        return EXIT_USAGE
    except UnwritableRoot as e:
        print(f"sandbox error: {e}", file=sys.stderr)
        return EXIT_ERROR
    except InjectionError as e:
        print(f"injection error: {e}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["UsageError", "main"]
