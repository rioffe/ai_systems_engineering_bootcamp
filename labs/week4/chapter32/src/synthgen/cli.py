# pyright: reportMissingImports=false
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .diagnostics import configure_diagnostics, metadata
from .errors import SynthgenError
from .service import generate_dataset, reproduce_manifest
from .spec import load_spec
from .truth import default_registry
from .writers import load_json


def _verbose(argv: Sequence[str]) -> list[str]:
    result = []
    for i, arg in enumerate(argv):
        result.append(arg)
        if arg == "--verbose" and (i + 1 == len(argv) or argv[i + 1] not in {"INFO", "DEBUG"}):
            result.append("INFO")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="synthgen")
    parser.add_argument("--verbose", nargs="?", const="INFO", choices=("INFO", "DEBUG"), default=None)
    subs = parser.add_subparsers(dest="command", required=True)
    generate = subs.add_parser("generate")
    generate.add_argument("spec")
    generate.add_argument("--size", type=int)
    generate.add_argument("--seed", type=int)
    generate.add_argument("--output")
    generate.add_argument("--report")
    generate.add_argument("--manifest")
    generate.add_argument("--method", choices=("template", "ollama"))
    generate.add_argument("--model")
    generate.add_argument("--host")
    generate.add_argument("--max-attempts", type=int)
    generate.add_argument("--allow-partial", action="store_true")
    generate.add_argument("--include-raw", action="store_true")
    generate.add_argument("--verbose", nargs="?", const="INFO", choices=("INFO", "DEBUG"), default=argparse.SUPPRESS)
    preview = subs.add_parser("preview")
    preview.add_argument("spec"); preview.add_argument("--size", type=int, default=1); preview.add_argument("--seed", type=int); preview.add_argument("--method", choices=("template", "ollama")); preview.add_argument("--verbose", nargs="?", const="INFO", choices=("INFO", "DEBUG"), default=argparse.SUPPRESS)
    for name in ("validate", "stats", "inspect", "reproduce"):
        p = subs.add_parser(name); p.add_argument("path"); p.add_argument("--force", action="store_true"); p.add_argument("--verbose", nargs="?", const="INFO", choices=("INFO", "DEBUG"), default=argparse.SUPPRESS)
    return parser


def _records(path: Path) -> list[dict[str, object]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError) as exc:
        raise SynthgenError(f"invalid dataset: {exc}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(); args = parser.parse_args(_verbose(argv if argv is not None else sys.argv[1:]))
    configure_diagnostics(getattr(args, "verbose", None), bool(getattr(args, "include_raw", False))); metadata("command={}", args.command)
    try:
        if args.command == "generate":
            spec = load_spec(Path(args.spec))
            realizer = None
            if args.method == "ollama":
                from .llm import OllamaRealizer
                realizer = OllamaRealizer(args.model or str(spec.realization.get("model", "llama3")), args.host or str(spec.realization.get("host", "http://127.0.0.1:11434")))
            result = generate_dataset(spec, size=args.size, seed=args.seed, method=args.method, max_attempts=args.max_attempts, realizer=realizer, output=Path(args.output) if args.output else Path(spec.dataset.output), report_path=Path(args.report) if args.report else Path(spec.dataset.report), manifest_path=Path(args.manifest) if args.manifest else Path(spec.dataset.manifest), allow_partial=args.allow_partial, spec_path=Path(args.spec))
            print(f"Generated {len(result.records)}/{result.report['requested']} records")
            return 0 if result.report["complete"] else 1
        if args.command == "preview":
            if args.size < 1 or args.size > 100: raise ValueError("preview size must be between 1 and 100")
            result = generate_dataset(load_spec(Path(args.spec)), size=args.size, seed=args.seed, method=args.method)
            print("\n".join(json.dumps(record, sort_keys=True, default=str) for record in result.records)); return 0
        if args.command == "reproduce":
            return 0 if reproduce_manifest(Path(args.path), force=args.force) else 1
        records = _records(Path(args.path))
        if not records: raise ValueError("empty dataset")
        if args.command == "validate":
            required = {"case_id", "category", "question", "expected", "metadata"}
            invalid = []
            for record in records:
                expected = record.get("expected")
                metadata_value = record.get("metadata")
                if (set(record) - required) or not required <= set(record) or not isinstance(expected, dict) or not expected.get("outcome") or not isinstance(metadata_value, dict):
                    invalid.append(record.get("case_id", "unknown"))
            for case_id in invalid: print(f"INVALID {case_id}")
            return 1 if invalid else 0
        categories = {}; methods = {}
        for record in records:
            categories[record.get("category")] = categories.get(record.get("category"), 0) + 1
            metadata_value = record.get("metadata")
            method = metadata_value.get("generator") if isinstance(metadata_value, dict) else None
            methods[method] = methods.get(method, 0) + 1
        if args.command == "stats": print(json.dumps({"records": len(records), "categories": categories, "realization_methods": methods}, sort_keys=True))
        else: print(json.dumps({"sample": records[:5], "records": len(records)}, indent=2, sort_keys=True, default=str))
        return 0
    except (SynthgenError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr); return getattr(exc, "exit_code", 2)


if __name__ == "__main__": raise SystemExit(main())
