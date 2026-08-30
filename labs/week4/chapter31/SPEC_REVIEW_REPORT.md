# Specification Review Report

## 1. Executive Summary

This is a fresh four-pass review of `labs/week4/chapter31/SPEC.md` after adding the PyQt5 UI, Ollama model discovery, levelled diagnostics, robust model-response normalization, natural-language schedule rendering, and the `mortgage eval` harness.

The specification remains coherent and implementation-grade in its deterministic/probabilistic boundary, numerical contracts, CLI surface, GUI model-discovery flow, and evaluation report shape. Five new findings remain: three medium implementation/verification gaps, one medium observability gap, and one low editorial issue. No critical or high-severity blocker was found.

The principal distinction is between **spec completeness** and **implementation conformance**: the spec describes tests T-39, T-43, and T-48 that are not yet present as dedicated automated tests, and the code's Ollama discovery error handling is less defensive than C-08b requires for malformed model entries.

## 2. Overall Maturity

**Level 3 — Implementation-grade, with verification gaps.**

A competent engineer can implement the specified system with minimal semantic inference. The remaining findings affect confidence and conformance evidence, not the core architecture.

## 3. Findings Summary

| Severity | Count | IDs |
| -------- | ----: | --- |
| HIGH | 0 | — |
| MEDIUM | 4 | F-014, F-015, F-016, F-017 |
| LOW | 1 | F-018 |

## 4. Detailed Findings

### F-014 — Dedicated Ollama discovery failure test is missing

**Severity:** MEDIUM

**Location:** §5.2, C-08b, T-43

#### Observation

The specification requires discovery failures to leave a safe dropdown state and display an error, and T-43 names that acceptance test. The current test suite verifies successful `/api/tags` population but does not verify the failure path.

#### Why it matters

A GUI worker failure can regress into a stuck refresh button, an unhandled thread exception, or an empty invalid model selection.

#### Potential consequence

The implementation can claim model discovery support without proving the required degraded behavior.

#### Recommended resolution

Add an offscreen test that makes `OllamaClient.list_models` raise, selects Ollama, waits for the worker to settle, and asserts an error status, a safe dropdown value, and a re-enabled refresh button.

### F-015 — Malformed `/api/tags` item behavior is not evidenced

**Severity:** MEDIUM

**Location:** C-08b, T-42

#### Observation

C-08b requires malformed JSON or malformed response shape to become `MODEL_ERROR`, but T-42 only tests valid model objects. The implementation also assumes every item supports `.get("name")`.

#### Why it matters

A valid JSON response containing a non-object model item can raise an uncaught `AttributeError` rather than the specified structured failure.

#### Potential consequence

The GUI discovery worker may surface an unclassified exception and fail to restore its controls.

#### Recommended resolution

Specify that `models` MUST be a list of objects and every object MUST contain a string `name`; otherwise return `MODEL_ERROR`. Add malformed-list, missing-name, and non-object-item tests.

### F-016 — Real-model eval failure acceptance test is missing

**Severity:** MEDIUM

**Location:** C-11, T-48, §5.1 `mortgage eval`

#### Observation

The spec requires real-model failures to be recorded per case and return exit code `5`, but there is no dedicated test for a mock real adapter producing `MODEL_ERROR` during evaluation.

#### Why it matters

The evaluator's case-failure exit (`1`) and infrastructure/model-failure exit (`5`) are materially different automation contracts.

#### Potential consequence

A future change can collapse model outages into ordinary case mismatches or incorrectly pass an interrupted evaluation.

#### Recommended resolution

Add a fake real adapter test that returns `MODEL_ERROR`, asserts the report row outcome/classification, and asserts CLI exit `5`.

### F-017 — Evaluation provenance is thinner than the requested diagnostic goal

**Severity:** MEDIUM

**Location:** C-11, §9.5, §10 observability

#### Observation

The report stores expected/actual values, checks, failure reasons, adapter, and model, but does not store per-case elapsed time, tool-call count, or a bounded raw model-response reference. The CLI's DEBUG stream can show raw payloads, but that data is not retained in `eval_report.json`.

#### Why it matters

A saved report cannot fully explain whether a failure came from slow inference, a missing calculator call, malformed model output, or a wrong extracted field.

#### Potential consequence

Post-run diagnosis requires rerunning the model with DEBUG rather than inspecting one durable artifact.

#### Recommended resolution

Add optional per-case `duration_ms`, `tool_calls`, `model_response_excerpt` (bounded and opt-in), and `failure_stage` fields. Keep raw content excluded by default for privacy; `--include-raw` can opt in.

### F-018 — Test identifier ordering is inconsistent

**Severity:** LOW

**Location:** §9.8

#### Observation

T-44, T-42, and T-43 appear before T-40 and T-41, while the traceability matrix references the identifiers in a different order.

#### Why it matters

This does not change behavior, but it makes review navigation and future additions less predictable.

#### Potential consequence

Reviewers can overlook a test or accidentally reuse an identifier.

#### Recommended resolution

Renumber or reorder the GUI acceptance bullets monotonically in a future documentation pass, preserving existing references through a deliberate ID migration.

## 5. Requirements Review

Requirements R-01..R-24 are observable and use normative language consistently. R-23 and R-24 correctly capture the newly added model discovery and evaluation surfaces. No requirement contradiction was found.

## 6. Interface and Data-Contract Review

The canonical request/result/error contracts are strong. C-08b should explicitly constrain every `/api/tags.models[]` item to an object with a string `name`, rather than leaving malformed-item behavior only in prose.

## 7. State and Failure Review

The GUI worker lifecycle is clear for successful discovery and request execution. The discovery-failure terminal state is specified but lacks automated evidence (F-014). Model-failure versus case-mismatch exit semantics are clear in the CLI table but need T-48.

## 8. Determinism and Algorithm Review

The four formulas, zero-rate paths, bisection solver, integer tolerance, rounding boundary, and schedule bound remain precise. Evaluation scoring uses explicit tolerances. No algorithmic ambiguity was introduced by the new features.

## 9. Edge-Case Review

The spec covers unavailable Ollama, malformed JSON, missing fields, aliases, false clarifications, unsupported scope, and model failures. Malformed individual `/api/tags` entries require a concrete contract/test addition (F-015).

## 10. Non-Functional Requirement Review

Offline mock evaluation, Qt offscreen testing, O(n) amortization, bounded schedules, and worker-thread requirements are measurable. Evaluation timing is logged at runtime but not retained per case, producing the observability gap in F-017.

## 11. Security and Trust-Boundary Review

The deterministic calculator remains authoritative. Host validation prevents non-HTTP URL schemes, and raw diagnostics are opt-in at DEBUG. If raw model responses are retained in reports, they must be bounded and explicitly opt-in as recommended by F-017.

## 12. Observability and Provenance Review

CLI diagnostics provide model/phase/payload-size information, and DEBUG provides raw prompts/responses. The durable evaluation report should retain bounded provenance for post-run analysis without making sensitive raw content the default.

## 13. Testing and Verification Review

The suite covers the deterministic core, GUI success path, model discovery success, response normalization, and mock evaluation. Dedicated tests remain for discovery failure, malformed model-list items, and real-model evaluation failure (F-014..F-016).

## 14. Metrics and Evaluation Review

The evaluation metrics are defined and reproducible for non-empty case sets. Intent, field, numeric, clarification, and scope accuracy are all computed from per-case checks. The report would be more diagnostically useful with timing/tool-call provenance (F-017).

## 15. Traceability Review

R-23/R-24 and C-08b/C-11 are present in the traceability matrix. T-43 and T-48 are specified but currently lack dedicated tests, so those rows represent intended verification rather than present evidence.

## 16. Internal-Consistency Review

The spec is internally consistent. The only editorial issue is non-monotonic GUI test ordering (F-018). The `eval` exit partition correctly distinguishes model failures from ordinary case failures at the specification level.

## 17. Architecture Review

The architecture remains sound: `cli.py`/`ui.py` select adapters, `eval.py` compares adapter behavior, `tool.py` delegates to the deterministic core, and Ollama transport remains isolated. No redesign is required.

## 18. Implementation-Agent Readiness

**YES — WITH MINOR CLARIFICATIONS.**

A strong coding agent can implement the remaining behavior without material product questions. Before claiming verification-grade conformance, it should add the tests in F-014..F-016 and decide whether to adopt the optional provenance fields in F-017.

## 19. Quality Scorecard

| Dimension | Score |
| --------- | ----: |
| Scope clarity | 5 |
| Terminology | 4 |
| Requirement precision | 4 |
| Interface completeness | 4 |
| Data-contract completeness | 4 |
| State/lifecycle definition | 4 |
| Algorithm precision | 5 |
| Failure semantics | 4 |
| Edge-case coverage | 4 |
| Non-functional requirements | 4 |
| Security specification | 4 |
| Observability/provenance | 3 |
| Testability | 4 |
| Evaluation/metrics | 4 |
| Traceability | 4 |
| Internal consistency | 4 |
| Architecture consistency | 5 |
| Implementation readiness | 4 |

## 20. Remediation Plan

### P0 — Blocking

None.

### P1 — Important

- F-014: Add the GUI discovery-failure test.
- F-015: Pin malformed `/api/tags` item semantics and add tests.
- F-016: Add the real-model evaluation failure test.
- F-017: Decide whether durable per-case provenance is required for operational evaluation.

### P2 — Improvement

- F-018: Reorder GUI test identifiers in a future documentation cleanup.

## 21. Final Verdict

Specification maturity:
**Level 3 — Implementation-grade**

Implementation readiness:
**READY WITH MINOR FIXES**

Primary blocker:
**NONE**

Most important improvement:
**Add dedicated failure-path tests for model discovery and real-model evaluation, then strengthen durable evaluation provenance if post-run diagnosis is required.**
