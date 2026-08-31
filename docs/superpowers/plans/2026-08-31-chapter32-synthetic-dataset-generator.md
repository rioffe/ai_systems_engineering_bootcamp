# Synthetic Dataset Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the complete Chapter 32 deterministic-first `synthgen` generator, reusing Chapter 31's mortgage calculator through an injected adapter and providing deterministic templates, optional Ollama realization, validation, deduplication, reports, manifests, CLI, and PyQt5 GUI.

**Architecture:** `synthgen` owns specification parsing, safe constraints, seeded scenario generation, realization, validation, deduplication, metrics, artifact publication, and interfaces. Chapter 31 is consumed only through a small adapter implementing the `GroundTruthCalculator` protocol; no generator module imports Chapter 31 internals beyond that adapter boundary. The CLI and GUI call one shared service and use Loguru for diagnostics.

**Tech Stack:** Python 3.12, `uv`, PyYAML, Loguru, standard-library `argparse`/`urllib`, pytest, Hypothesis, optional PyQt5/pytest-qt, Chapter 31 mortgage package.

**Spec:** `/Users/rioffe/projects/ai_systems_engineering_bootcamp/labs/week4/chapter32/SPEC.md`

## Global Constraints

- Python MUST be `>=3.12,<3.13` and installation/commands MUST use `uv`.
- `max_attempts` MUST default to `max(size * 5, size + 10)` and remain finite.
- Preview MUST accept at most 100 records and MUST NOT publish production artifacts by default.
- Deterministic/template generation MUST open no network sockets.
- LLM retries MUST be bounded by `max_regenerations`, default `3`.
- Raw prompts/responses are omitted by default and capped at 4,000 characters when retained.
- JSON/JSONL artifacts use UTF-8, sorted keys, and trailing newlines.
- Exact deduplication is mandatory before publication; near-deduplication status is reported.
- Category weights are positive and sum to `1.0` within `1e-9`.
- A single record MUST NOT exceed 1 MB of language or metadata payload.
- Omitted diagnostics are quiet, INFO is metadata-only, and DEBUG is the only raw-payload level.
- Ground truth is calculated only by the injected calculator and is never supplied by an LLM.

---

### Task 1: Scaffold package, dependency boundary, and shared contracts

**Files:**

- Create: `labs/week4/chapter32/pyproject.toml`
- Create: `labs/week4/chapter32/README.md`
- Create: `labs/week4/chapter32/src/synthgen/__init__.py`
- Create: `labs/week4/chapter32/src/synthgen/models.py`
- Create: `labs/week4/chapter32/src/synthgen/errors.py`
- Test: `labs/week4/chapter32/tests/test_models.py`

**Interfaces:**

- Produces frozen `Scenario`, `GroundTruth`, `Realization`, `ExtractionResult`, `ValidationResult`, `GenerationResult`, and calculator protocols/registry contracts.
- Produces stable structured exceptions for specification, constraint, calculator, model, exhaustion, duplicate, and artifact failures.

- [ ] **Step 1: Write the failing contract tests**

```python
from decimal import Decimal
from synthgen.models import GroundTruth, Realization, Scenario

def test_contracts_are_frozen_and_preserve_decimal_values():
    scenario = Scenario("payment-000001", "payment", {"principal": Decimal("100")}, "calculated", 0)
    truth = GroundTruth("calculated", {"payment": Decimal("1")}, "mortgage", "chapter31")
    realization = Realization("What is the payment?", "template", "payment_01", None, None)
    assert scenario.fields["principal"] == Decimal("100")
    assert truth.source == "mortgage"
    assert realization.raw_response is None

def test_publication_result_exposes_records_report_manifest_and_failures():
    from synthgen.models import GenerationResult
    result = GenerationResult(records=(), report={}, manifest={}, failures=())
    assert result.records == ()
```

- [ ] **Step 2: Run the tests and verify the expected missing-module failure**

Run: `cd labs/week4/chapter32 && uv run pytest tests/test_models.py -v`
Expected: FAIL because `synthgen.models` does not yet exist.

- [ ] **Step 3: Implement minimal contracts and package metadata**

Use frozen dataclasses, `Protocol` interfaces, `Literal` method types, and error dataclasses with stable `code`, `message`, `field`, and `details`. Add dependencies and console scripts `synthgen = synthgen.cli:main` and `synthgen-gui = synthgen.ui:run_gui`. Add a local `uv` path source for Chapter 31's mortgage package so `import mortgage` is available without copying its implementation.

- [ ] **Step 4: Run the focused tests**

Run: `cd labs/week4/chapter32 && uv sync --extra test && uv run pytest tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add labs/week4/chapter32
git commit -m "feat(ch32): scaffold synthgen contracts"
```

### Task 2: Load and validate typed YAML/JSON specifications

**Files:**

- Create: `labs/week4/chapter32/src/synthgen/spec.py`
- Create: `labs/week4/chapter32/src/synthgen/schema.py`
- Create: `labs/week4/chapter32/schemas/dataset-spec.json`
- Create: `labs/week4/chapter32/schemas/dataset-record.json`
- Create: `labs/week4/chapter32/examples/mortgage.yaml`
- Test: `labs/week4/chapter32/tests/test_spec.py`

**Interfaces:**

- `load_spec(path: Path) -> DatasetSpecification`
- `validate_spec(spec: DatasetSpecification, registry: CalculatorRegistry) -> None`
- `normalize_spec(spec) -> dict[str, object]`
- Field descriptors support `string`, `decimal`, `integer`, `enum`, required/nullability, finite bounds, and enum values.

- [ ] **Step 1: Write failing tests** for valid YAML/JSON normalization, malformed syntax, missing sections, unknown methods/domains, malformed descriptors, invalid weights, and unbounded distributions.
- [ ] **Step 2: Run `uv run pytest tests/test_spec.py -v` and confirm failures are caused by absent loader/validator behavior.**
- [ ] **Step 3: Implement strict parsing, defaults, path-aware errors, SHA-256 normalized specification hashing, and JSON Schema reference artifacts. The loader must reject unknown top-level fields where the contract requires strictness and preserve specification order.**
- [ ] **Step 4: Run focused tests and verify all invalid inputs return structured specification errors.**
- [ ] **Step 5: Commit with `git commit -m "feat(ch32): validate dataset specifications"`.**

### Task 3: Implement deterministic distributions and safe constraint evaluation

**Files:**

- Create: `labs/week4/chapter32/src/synthgen/distributions.py`
- Create: `labs/week4/chapter32/src/synthgen/constraints.py`
- Test: `labs/week4/chapter32/tests/test_distributions.py`
- Test: `labs/week4/chapter32/tests/test_constraints.py`

**Interfaces:**

- `build_distribution(config: Mapping[str, object]) -> Distribution`
- `allocate_category(rng: random.Random, categories: OrderedMapping) -> str`
- `compile_constraint(expression: str) -> Constraint`
- `check_constraints(scenario, constraints) -> tuple[bool, tuple[str, ...]]`

- [ ] **Step 1: Write failing tests** covering `[min,max)` uniform sampling, bounded lognormal, weighted choice, ordered values, same-seed equality, category weight validation, arithmetic/comparison/and/or/in grammar, missing fields, division by zero, and rejection of calls/attributes/imports/indexing/assignment.
- [ ] **Step 2: Run focused tests and observe expected failures.**
- [ ] **Step 3: Implement a tokenizer/parser using only the pinned grammar; never call `eval`. Convert samples to declared field types and use only the run-local RNG.**
- [ ] **Step 4: Run focused tests plus property tests for deterministic sequences and finite outputs.**
- [ ] **Step 5: Commit with `git commit -m "feat(ch32): add seeded distributions and safe constraints"`.**

### Task 4: Add scenario generation and Chapter 31 calculator adapter

**Files:**

- Create: `labs/week4/chapter32/src/synthgen/scenarios.py`
- Create: `labs/week4/chapter32/src/synthgen/truth.py`
- Test: `labs/week4/chapter32/tests/test_scenarios.py`
- Test: `labs/week4/chapter32/tests/test_truth.py`

**Interfaces:**

- `ScenarioGenerator(spec).sample(rng, index) -> Scenario`
- `CalculatorRegistry.register(name, calculator)` and `.get(name)`
- `Chapter31MortgageCalculator.calculate(scenario) -> GroundTruth`
- `calculate_truth(scenario, registry, domain) -> GroundTruth`

- [ ] **Step 1: Write failing tests** for stable scenario IDs, category selection, field distributions, constraint rejection, mortgage payment/principal/rate/term outcomes, payment-too-low errors, unknown domains, and a substituted calculator double.
- [ ] **Step 2: Run `uv run pytest tests/test_scenarios.py tests/test_truth.py -v` and verify missing implementation failures.**
- [ ] **Step 3: Implement scenario sampling with `random.Random(seed)`, stable seed offsets, registry lookup, and a Chapter 31 adapter translating scenario fields to `CalculationRequest` and `CalculationResult`/`CalculationError` into C-03 ground truth. Preserve Decimal values and stable calculator version.**
- [ ] **Step 4: Run focused tests and verify the adapter does not import or call Chapter 31 CLI/LLM code.**
- [ ] **Step 5: Commit with `git commit -m "feat(ch32): generate scenarios through chapter31 truth adapter"`.**

### Task 5: Implement deterministic templates and Ollama realization

**Files:**

- Create: `labs/week4/chapter32/src/synthgen/templates.py`
- Create: `labs/week4/chapter32/src/synthgen/llm.py`
- Create: `labs/week4/chapter32/src/synthgen/diagnostics.py`
- Test: `labs/week4/chapter32/tests/test_generators.py`

**Interfaces:**

- `TemplateRealizer.realize(scenario, truth, rng) -> Realization`
- `OllamaRealizer.realize(scenario, truth, candidate_seed) -> Realization`
- `configure_diagnostics(level: str | None, include_raw: bool = False) -> None`

- [ ] **Step 1: Write failing tests** for all declared mortgage intents and template variations, unit/rate/term preservation, offline template operation, immutable truth boundary, Ollama request formatting, bounded raw payloads, INFO/DEBUG logging, model failures, and bounded regeneration seeds.
- [ ] **Step 2: Run the focused tests and verify failures before implementation.**
- [ ] **Step 3: Implement deterministic template IDs and phrasing variants. Implement Ollama using `urllib.request`, sending only the fixed scenario/truth context needed for wording, parsing a question-only response, and translating connection/HTTP/JSON failures into structured model errors. Configure Loguru to stderr with quiet/INFO/DEBUG semantics; never log raw content at INFO.**
- [ ] **Step 4: Run tests with a local HTTP test server and assert template tests do not create sockets.**
- [ ] **Step 5: Commit with `git commit -m "feat(ch32): add template and ollama realizers"`.**

### Task 6: Implement schema, semantic, scope validation, and deduplication

**Files:**

- Create: `labs/week4/chapter32/src/synthgen/validators.py`
- Create: `labs/week4/chapter32/src/synthgen/dedup.py`
- Test: `labs/week4/chapter32/tests/test_validation.py`
- Test: `labs/week4/chapter32/tests/test_dedup.py`

**Interfaces:**

- `validate_candidate(scenario, truth, realization, spec) -> ValidationResult`
- `extract_question(question, spec) -> ExtractionResult`
- `normalize_question(question) -> str`
- `Deduplicator.check(question, record_id) -> DuplicateDecision`

- [ ] **Step 1: Write failing tests** for accepted template records, changed principal/rate/term/payment/outcome, unit aliases, ambiguous/malformed questions, unsupported taxes/insurance/HOA/ARM/advice, unknown fields, missing required fields, exact duplicate keys, near duplicate classification, and deterministic reason ordering.
- [ ] **Step 2: Run focused tests and observe expected failures.**
- [ ] **Step 3: Implement normalization and a strict mortgage extraction parser, compare scenario fields and truth, enforce declared scope, validate C-05 records, and implement exact deduplication plus configurable near-duplicate similarity with an explicit disabled state.**
- [ ] **Step 4: Run focused tests and verify rejected candidates never become records.**
- [ ] **Step 5: Commit with `git commit -m "feat(ch32): validate semantics and deduplicate records"`.**

### Task 7: Implement generation service, metrics, reports, atomic writers, and manifests

**Files:**

- Create: `labs/week4/chapter32/src/synthgen/service.py`
- Create: `labs/week4/chapter32/src/synthgen/metrics.py`
- Create: `labs/week4/chapter32/src/synthgen/writers.py`
- Create: `labs/week4/chapter32/schemas/report.json`
- Create: `labs/week4/chapter32/schemas/manifest.json`
- Test: `labs/week4/chapter32/tests/test_reports.py`
- Test: `labs/week4/chapter32/tests/test_generators.py`

**Interfaces:**

- `generate_dataset(spec, options, registry) -> GenerationResult`
- `build_report(run) -> dict[str, object]`
- `write_artifacts(result, paths, allow_partial=False) -> None`
- `reproduce_manifest(manifest_path, overrides=None, force=False) -> ComparisonResult`

- [ ] **Step 1: Write failing tests** for accepted ordering, max-attempt exhaustion, regeneration, rejection provenance, metrics denominators/six-place formatting/nulls, stable JSONL, metadata, spec/dataset hashes, relative manifest paths, timestamp normalization, version mismatch/force, atomic cleanup, and partial publication.**
- [ ] **Step 2: Run focused tests and confirm failures.**
- [ ] **Step 3: Implement the bounded run state machine, candidate seed hash `(run_seed, scenario_id, attempt_index, method)`, report failure records, C-05 conversion, stable serialization, staging directory, atomic rename, complete flag, manifest fields, and normalized reproduction comparison. Ensure no accepted ID is consumed by rejection.**
- [ ] **Step 4: Run focused tests and verify artifacts are absent after ordinary failure.**
- [ ] **Step 5: Commit with `git commit -m "feat(ch32): publish reproducible dataset artifacts"`.**

### Task 8: Implement the complete CLI

**Files:**

- Create: `labs/week4/chapter32/src/synthgen/cli.py`
- Test: `labs/week4/chapter32/tests/test_cli.py`

**Interfaces:**

- `build_parser() -> argparse.ArgumentParser`
- `main(argv: Sequence[str] | None = None) -> int`

- [ ] **Step 1: Write failing subprocess tests** for `generate`, `validate`, `stats`, `preview`, `reproduce`, and `inspect`, all overrides, verbose before/after subcommands, exit codes 0/1/2/5, partial behavior, read-only behavior, and default output paths.
- [ ] **Step 2: Run `uv run pytest tests/test_cli.py -v` and observe missing command failures.**
- [ ] **Step 3: Implement argparse dispatch over the shared service, normalize bare `--verbose`, emit summaries to stdout and Loguru diagnostics to stderr, and map structured errors to the specified exit codes.**
- [ ] **Step 4: Run the CLI tests and manually execute the six documented commands against `examples/mortgage.yaml`.**
- [ ] **Step 5: Commit with `git commit -m "feat(ch32): add synthgen command line interface"`.**

### Task 9: Implement the optional PyQt5 GUI boundary

**Files:**

- Create: `labs/week4/chapter32/src/synthgen/ui.py`
- Test: `labs/week4/chapter32/tests/test_ui.py`

**Interfaces:**

- `SynthgenWindow(service=None)`
- `run_gui() -> int`

- [ ] **Step 1: Write failing Qt tests** for construction without generation, specification display, size/seed/method controls, Preview/Generate/Validate/Stats/Inspect actions, artifact path display, and Off/INFO/DEBUG diagnostics.
- [ ] **Step 2: Run the tests with the GUI extra and observe failures.**
- [ ] **Step 3: Implement a thin PyQt5 window that delegates every operation to the shared service and never duplicates generation/validation logic. Keep raw model content confined to a DEBUG diagnostics view.**
- [ ] **Step 4: Run GUI tests in offscreen mode and verify construction performs no generation.**
- [ ] **Step 5: Commit with `git commit -m "feat(ch32): add shared synthgen pyqt interface"`.**

### Task 10: Add documentation, end-to-end evals, and final verification

**Files:**

- Modify: `labs/week4/chapter32/README.md`
- Create: `labs/week4/chapter32/evals/generated.jsonl`
- Create: `labs/week4/chapter32/evals/report.json`
- Create: `labs/week4/chapter32/evals/manifest.json`
- Test: `labs/week4/chapter32/tests/test_end_to_end.py`

- [ ] **Step 1: Write failing end-to-end tests** for a 30-record mortgage run, byte-identical same-seed runs, changed-seed difference, validate/stats/inspect read-only behavior, reproduction success/mismatch, and Ollama malformed/paraphrase ground-truth preservation.**
- [ ] **Step 2: Run the end-to-end tests and verify they fail only because the final wiring/evals are absent.**
- [ ] **Step 3: Complete README usage, architecture, calculator reuse boundary, offline guarantees, Ollama setup, GUI setup, artifact contracts, diagnostics, and troubleshooting. Generate checked-in 30-record eval artifacts with stable options.**
- [ ] **Step 4: Run the complete verification suite:**

```bash
cd labs/week4/chapter32
uv sync --extra test --extra gui
uv run pytest
uv run synthgen generate examples/mortgage.yaml --size 30 --seed 42 --output /tmp/ch32.jsonl --report /tmp/ch32.report.json --manifest /tmp/ch32.manifest.json
uv run synthgen validate /tmp/ch32.jsonl
uv run synthgen stats /tmp/ch32.jsonl
uv run synthgen inspect /tmp/ch32.jsonl
uv run synthgen reproduce /tmp/ch32.manifest.json
```

Expected: all tests pass; deterministic generate/reproduce returns 0; artifacts have stable sorted serialization and trailing newlines.

- [ ] **Step 5: Run `uv run pyright` if configured, inspect `git diff --check`, and run `lens_diagnostics` before claiming completion.**
- [ ] **Step 6: Commit with `git commit -m "feat(ch32): complete synthetic dataset generator"`.**

---

## Self-review

- **Spec coverage:** R-01–R-06 are covered by Tasks 2–4; R-07–R-10 by Tasks 5–6; R-11–R-13 by Task 7; R-14–R-19 by Tasks 7–8; R-20–R-24 by Tasks 1, 5, 7, and 9. C-01–C-10, I-001–I-013, K-01–K-12, and E-01–E-19 are explicitly tested across Tasks 2–10.
- **Option B boundary:** Only Task 4’s adapter imports Chapter 31; all other layers depend on `GroundTruthCalculator`/`CalculatorRegistry` protocols.
- **TDD:** Every task begins with a failing test and an explicit failing-test run before production implementation.
- **Optional features:** Ollama, near deduplication, raw debug diagnostics, and PyQt5 GUI are included rather than deferred.
- **No placeholders:** All tasks specify concrete files, interfaces, test behavior, commands, and expected outcomes.
