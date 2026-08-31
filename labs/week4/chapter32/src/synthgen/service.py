# pyright: reportMissingImports=false
from __future__ import annotations

import hashlib
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .dedup import Deduplicator
from .errors import CalculatorError, ConstraintError, ExhaustedError, ModelError
from .metrics import build_report
from .models import GenerationResult
from .scenarios import ScenarioGenerator
from .spec import DatasetSpecification, validate_spec
from .templates import TemplateRealizer
from .truth import default_registry
from .validators import validate_candidate
from .writers import stable_json, write_artifacts


def _candidate_seed(seed: int, scenario_id: str, attempt: int, method: str) -> int:
    value = f"{seed}:{scenario_id}:{attempt}:{method}".encode()
    return int.from_bytes(hashlib.sha256(value).digest()[:8], "big")


def generate_dataset(spec: DatasetSpecification, *, size: int | None = None, seed: int | None = None, method: str | None = None, max_attempts: int | None = None, registry: Any = None, realizer: Any = None, allow_partial: bool = False, output: Path | None = None, report_path: Path | None = None, manifest_path: Path | None = None, spec_path: Path | None = None) -> GenerationResult:
    registry = registry or default_registry()
    validate_spec(spec, registry)
    size = size if size is not None else spec.dataset.size
    seed = seed if seed is not None else spec.dataset.seed
    if seed is None:
        raise ValueError("an explicit seed is required when specification has no seed")
    method = method or str(spec.realization.get("method", "template"))
    max_attempts = max_attempts or spec.dataset.max_attempts or max(size * 5, size + 10)
    if size < 1 or max_attempts < 1:
        raise ValueError("size and max_attempts must be positive")
    if method == "ollama" and realizer is None:
        from .llm import OllamaRealizer
        realizer = OllamaRealizer(str(spec.realization.get("model", "llama3")), str(spec.realization.get("host", "http://127.0.0.1:11434")))
    realizer = realizer or TemplateRealizer()
    rng = random.Random(seed)
    scenarios = ScenarioGenerator(spec)
    dedup = Deduplicator(bool(spec.raw.get("deduplication", {}).get("near", False)))
    records, failures = [], []
    duplicates, methods = Counter(), Counter()
    attempted = 0
    while len(records) < size and attempted < max_attempts:
        attempted += 1
        try:
            scenario = scenarios.sample(rng, attempted - 1)
            truth = registry.get(spec.dataset.domain).calculate(scenario)
            realization = None
            for regeneration in range(int(spec.realization.get("max_regenerations", 3)) + 1):
                try:
                    realization = realizer.realize(scenario, truth, _candidate_seed(seed, scenario.scenario_id, attempted + regeneration, method)) if method == "ollama" else realizer.realize(scenario, truth, rng)
                    validation = validate_candidate(scenario, truth, realization, spec)
                    if validation.valid:
                        break
                    failures.append({"stage": validation.stage, "reason": list(validation.reasons), "scenario_id": scenario.scenario_id, "candidate": realization.question[:4000]})
                    realization = None
                except ModelError as exc:
                    failures.append({"stage": "model", "reason": [str(exc)], "scenario_id": scenario.scenario_id})
            if realization is None:
                continue
            decision = dedup.check(realization.question, f"{scenario.category}-{len(records):02d}")
            if decision.duplicate:
                duplicates[decision.kind] += 1
                failures.append({"stage": "dedup", "reason": [f"{decision.kind} duplicate", decision.normalized_key], "prior_record_id": decision.prior_record_id, "scenario_id": scenario.scenario_id})
                continue
            record = {"case_id": f"{scenario.category}-{len(records):02d}", "category": scenario.category, "question": realization.question, "expected": {"intent": scenario.category, "outcome": truth.outcome, "fields": {k: str(v) for k, v in truth.fields.items()}}, "metadata": {"scenario_id": scenario.scenario_id, "generator": realization.method, "template_id": realization.template_id, "model": realization.model, "seed": _candidate_seed(seed, scenario.scenario_id, attempted, method), "spec_hash": spec.spec_hash}}
            records.append(record)
            methods[realization.method] += 1
        except (ConstraintError, CalculatorError, ValueError) as exc:
            failures.append({"stage": "scenario" if isinstance(exc, ConstraintError) else "calculator", "reason": [str(exc)]})
    complete = len(records) == size
    output_file = Path(output or spec.dataset.output)
    report_file = Path(report_path or spec.dataset.report)
    manifest_file = Path(manifest_path or spec.dataset.manifest)
    manifest_base = manifest_file.parent.resolve()
    def manifest_ref(path: Path) -> str:
        try:
            return str(path.resolve().relative_to(manifest_base))
        except ValueError:
            return str(path.resolve())
    report_name = manifest_ref(report_file)
    near_enabled = bool(spec.raw.get("deduplication", {}).get("near", False))
    report = build_report(spec.dataset.name, size, attempted, records, failures, duplicates, methods, complete, report_name, near_enabled)
    manifest = {"manifest_version": "0.1", "generator_version": "0.1.0", "spec_hash": spec.spec_hash, "spec_path": str((spec_path or Path("examples/mortgage.yaml")).resolve()), "dataset_path": manifest_ref(output_file), "report_path": report_name, "manifest_path": manifest_ref(manifest_file), "seed": seed, "requested_size": size, "max_attempts": max_attempts, "adapter": method, "model": getattr(realizer, "model", None), "temperature": None, "created_at": datetime.now(timezone.utc).isoformat()}
    if output is not None or report_path is not None or manifest_path is not None:
        if not complete and not allow_partial:
            raise ExhaustedError(f"accepted {len(records)} of {size} records")
        write_artifacts(records, report, manifest, output_file, report_file, manifest_file, allow_partial)
    return GenerationResult(tuple(records), report, manifest, tuple(failures))


def reproduce_manifest(manifest_path: Path, *, force: bool = False) -> bool:
    from .spec import load_spec
    from .writers import load_json, sha256_file
    manifest = load_json(manifest_path)
    if manifest.get("manifest_version") != "0.1" and not force:
        raise ValueError("unsupported manifest version")
    dataset = Path(manifest["dataset_path"])
    if not dataset.is_absolute():
        dataset = manifest_path.parent / dataset
    if sha256_file(dataset) != manifest.get("dataset_sha256"):
        return False
    spec_path = Path(str(manifest.get("spec_path", "../examples/mortgage.yaml")))
    if not spec_path.is_absolute():
        spec_path = manifest_path.parent / spec_path
    spec = load_spec(spec_path)
    try:
        requested_size = int(manifest["requested_size"])
        manifest_seed = int(manifest["seed"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("manifest has invalid generation parameters") from exc
    result = generate_dataset(spec, size=requested_size, seed=manifest_seed, method=str(manifest["adapter"]))
    try:
        expected = dataset.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read dataset: {dataset}") from exc
    return expected == "".join(stable_json(r) + "\n" for r in result.records)
