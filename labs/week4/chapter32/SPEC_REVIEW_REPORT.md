# Specification Review Report

## 1. Executive Summary

The Chapter 32 specification defines a strong deterministic-first synthetic dataset architecture: scenario generation is separated from ground truth, language realization is untrusted, validation gates publication, and reproducibility/provenance are first-class concerns. The 12-section structure, normative language, CLI surface, artifact contracts, universal verbosity contract, and traceability matrix are present.

The four-pass review found **2 HIGH**, **6 MEDIUM**, and **2 LOW** findings. The principal gaps concern reproducibility identity (the manifest does not identify the dataset artifact to reproduce), underspecified distribution semantics, underspecified declarative schema types, and ambiguous validator/calculator boundaries. The specification is implementable, but two competent implementations could diverge in these areas.

## 2. Overall Maturity

**Level 2 — Implementable with material precision gaps.**

The architecture is clear enough to begin implementation, but it is not yet Level 3 because several externally observable choices remain open.

## 3. Findings Summary

| Severity | Count | IDs |
| -------- | ----: | --- |
| HIGH | 2 | F-001, F-002 |
| MEDIUM | 6 | F-003, F-004, F-005, F-006, F-007, F-008 |
| LOW | 2 | F-009, F-010 |

## 4. Detailed Findings

### F-001 — Reproduction target is not identified by the manifest

**Severity:** HIGH

**Location:** C-09, R-12, I-012, K-10, T-17/T-18

#### Observation

The manifest records generator configuration but does not contain the path, content hash, or artifact identity of the dataset being reproduced. `reproduce MANIFEST` is therefore not implementable without an undocumented convention for locating the original JSONL.

#### Why it matters

A manifest cannot establish which dataset to compare, especially when multiple datasets use the same specification and seed.

#### Potential consequence

Two conforming implementations may compare different files or silently regenerate without comparison.

#### Recommended resolution

Add `dataset_path`, `dataset_sha256`, `report_path`, and `manifest_path` to C-09. Define that `reproduce` resolves the dataset relative to the manifest unless an explicit `--dataset` override is supplied, and fails on a hash mismatch.

### F-002 — Distribution semantics are not sufficiently pinned

**Severity:** HIGH

**Location:** C-06, R-05, §6, §12, K-04

#### Observation

The spec names `uniform`, `lognormal`, `choice`, and `values`, but does not define parameter names, boundary inclusion, lognormal parameterization, Decimal/float conversion, or whether category weights use sequential RNG draws or a deterministic allocation algorithm.

#### Why it matters

Distribution behavior directly determines generated records and byte-level reproducibility.

#### Potential consequence

Two generators using the same seed and specification can produce materially different datasets while both claiming conformance.

#### Recommended resolution

Pin each distribution schema and formula, use a run-local `random.Random`, define inclusive/exclusive bounds, define lognormal `mu`/`sigma`, and define weighted-category selection/order and rounding of category counts.

### F-003 — Declarative field schema lacks types and validation rules

**Severity:** MEDIUM

**Location:** C-01, R-01, R-08, T-01/T-02

#### Observation

`schema.fields` is shown as a list of field names only. The specification does not define field type, required status, nullability, format, or range for generated fields.

#### Why it matters

A schema validator cannot determine whether `annual_rate` must be a decimal, whether `principal` may be null, or whether metadata fields are required.

#### Potential consequence

Generated JSONL records differ in shape and downstream validators accept incompatible records.

#### Recommended resolution

Define a field descriptor object with `name`, `type`, `required`, `nullable`, `minimum`, `maximum`, and optional enum/format. Pin the mortgage example’s field descriptors.

### F-004 — Constraint expression language is unspecified

**Severity:** MEDIUM

**Location:** §10, C-06, K-11, T-02

#### Observation

Examples use expressions such as `principal > 0` and `payment > principal * annual_rate / 12`, but no grammar, supported operators, field lookup rules, numeric semantics, or error behavior is defined.

#### Why it matters

An implementer must choose whether to use `eval`, a parser, an expression library, or a restricted custom language, and those choices affect safety and behavior.

#### Potential consequence

Constraint expressions may be interpreted differently or introduce code-execution risk.

#### Recommended resolution

Pin a safe expression grammar: identifiers, numeric literals, `+ - * /`, comparisons, `and/or/not`, parentheses, and membership in finite lists; prohibit calls, attribute access, imports, and arbitrary evaluation. Define division-by-zero and missing-field errors.

### F-005 — Ground-truth calculator registration and failure contract are incomplete

**Severity:** MEDIUM

**Location:** C-03, C-10, R-03, R-22

#### Observation

C-10 defines a calculator protocol but does not specify how a named dataset/domain calculator is registered or selected from C-01. C-03 also does not define the shape of calculator failure beyond “structured error.”

#### Why it matters

A CLI implementation cannot know which calculator handles `mortgage_questions`, and validators cannot consistently classify a calculator rejection.

#### Potential consequence

The same specification may use different calculators or silently fall back to a generic truth function.

#### Recommended resolution

Add a calculator registry keyed by `dataset.domain` or `truth_calculator`, require that name in C-01, and define a `GroundTruthError{code,message,field,details}` contract.

### F-006 — LLM semantic-validation and regeneration policy is underspecified

**Severity:** MEDIUM

**Location:** C-04, C-07, R-07/R-09, E-07, T-10/T-11

#### Observation

The spec requires parsing a generated question back into a scenario but does not define which parser performs extraction, how numeric aliases such as `500k` are normalized, how ambiguity is reported, or whether a failed candidate receives the same seed on regeneration.

#### Why it matters

Semantic equivalence is the core safety gate for LLM-generated language.

#### Potential consequence

Different validators accept different paraphrases or regenerate different candidates from the same seed.

#### Recommended resolution

Define an `ExtractionResult` contract, normalization rules, deterministic reason ordering, and regeneration seed derivation such as `candidate_seed = hash(run_seed, scenario_id, attempt_index)`.

### F-007 — Artifact atomicity and partial-output behavior conflict

**Severity:** MEDIUM

**Location:** C-05, §5.3, E-10, R-11/R-19

#### Observation

C-05 says artifacts are written atomically or the run fails, while E-10 permits a partial report with `--allow-partial`; the spec does not define which files may exist after failure or whether a partial JSONL is valid input to `validate`/`reproduce`.

#### Why it matters

Failure cleanup is externally observable and important for automation.

#### Potential consequence

A failed run leaves an apparently complete dataset, orphaned manifest, or incompatible partial report.

#### Recommended resolution

Define a staging directory and commit/rename protocol. Without `--allow-partial`, publish nothing; with it, publish a report/manifest marked `complete=false` and a dataset containing only accepted records, which `reproduce` must reject as a complete match.

### F-008 — Quality metric denominators and rounding are not fully defined

**Severity:** MEDIUM

**Location:** C-08, R-13, §17, T-04/T-16

#### Observation

The report lists category distributions, duplicate counts, and average generation cost but does not define denominators, percentage rounding, empty-category behavior, near-duplicate scope, or missing-cost handling.

#### Why it matters

Quality reports are intended to be comparable artifacts.

#### Potential consequence

Two reports can show different percentages or averages for the same records.

#### Recommended resolution

Define every metric’s numerator, denominator, units, precision, and null policy. Use accepted-record count for category percentages, attempted-candidate count for validation rates, and `null` when cost data is unavailable rather than zero.

### F-009 — GUI requirement is optional but its acceptance boundary is unclear

**Severity:** LOW

**Location:** R-20, §5.2, T-29/T-30

#### Observation

R-20 says the system MUST provide an optional GUI or documented GUI boundary, while T-29/T-30 condition acceptance on GUI implementation. The spec does not state whether v0.1 conformance requires the GUI or only the documented boundary.

#### Why it matters

The word “MUST” and “optional” communicate conflicting conformance expectations.

#### Potential consequence

Reviewers disagree about whether a CLI-only implementation passes.

#### Recommended resolution

State explicitly: “GUI is out of v0.1 acceptance; if implemented, it MUST satisfy §5.2 and T-29/T-30.”

### F-010 — Version compatibility policy is incomplete

**Severity:** LOW

**Location:** C-08/C-09, R-12, T-17/T-18

#### Observation

Reports and manifests have versions, but no reader compatibility policy defines whether newer versions are rejected, warned, or accepted with `--force`.

#### Why it matters

Reproducibility and inspection behavior across future schema versions is ambiguous.

#### Potential consequence

A reader may silently ignore fields or compare incompatible artifacts.

#### Recommended resolution

Pin exact-version acceptance for v0.1 and require an explicit `--force` for mismatches, with a visible warning.

## 5. Requirements Review

The requirements are generally observable and cover the intended pipeline. R-12, R-13, R-16, and R-21 are strong. R-05 requires distribution semantics that are not yet specified, and R-19 requires failure details whose schema is only partially defined.

## 6. Interface and Data-Contract Review

The major contracts are present, but C-01 needs typed field descriptors, C-03 needs a calculator registry/error shape, and C-09 needs dataset identity and hash fields. These are conformance-relevant gaps.

## 7. State and Failure Review

The lifecycle states and bounded attempts are sound. Partial artifact publication, regeneration identity, and failed-candidate persistence need explicit protocols (F-006/F-007).

## 8. Determinism and Algorithm Review

Seeded RNG and timestamp normalization are good foundations. Distribution formulas, category allocation, and constraint evaluation require pinning before byte-level reproducibility can be claimed.

## 9. Edge-Case Review

The spec covers missing specs, malformed configuration, impossible constraints, LLM failure, duplicates, exhaustion, and write failure. Missing behaviors are malformed field descriptors, missing calculator registrations, and version-incompatible artifact reads.

## 10. Non-Functional Requirement Review

The spec provides useful bounds for attempts, preview size, payload size, retries, and deterministic paths. It should add output byte/record limits and define metric precision for comparable reports.

## 11. Security and Trust-Boundary Review

The LLM is correctly untrusted and ground truth is isolated. The constraint-expression language is a security boundary and must not be implemented with unrestricted evaluation (F-004). Raw model content is bounded and opt-in, which is appropriate.

## 12. Observability and Provenance Review

The record metadata and manifest are well motivated. Dataset identity, per-attempt seed derivation, and failure-stage provenance must be added to make individual records reproducible and auditable.

## 13. Testing and Verification Review

The test plan covers the main pipeline, but T-02/T-04/T-10/T-18/T-24 need concrete distribution, constraint, and artifact comparison semantics. T-34-level malformed configuration and compatibility tests would strengthen the suite.

## 14. Metrics and Evaluation Review

The metric categories are appropriate, but denominators and null/rounding policies are not pinned (F-008). The report should distinguish attempted candidates from accepted records.

## 15. Traceability Review

The matrix covers every current R/C/I/K/E/T family referenced by the spec. Once F-001..F-008 are resolved, add traceability rows for manifest dataset identity, expression grammar, registry selection, regeneration seeds, atomic staging, and metric formulas.

## 16. Internal-Consistency Review

The architecture is internally consistent. The main tension is “optional GUI” versus a MUST requirement (F-009), and atomic output versus optional partial output (F-007).

## 17. Architecture Review

The dependency direction is sound: spec -> scenario -> truth/language -> validation -> deduplication -> artifacts. The missing calculator registry and safe constraint interpreter are boundary-definition gaps, not architecture defects.

## 18. Implementation-Agent Readiness

**NO — MATERIAL QUESTIONS REMAIN.**

A strong coding agent would still need decisions about distribution formulas, field typing, constraint parsing, calculator registration, reproduction target identity, partial artifacts, and metric denominators.

## 19. Quality Scorecard

| Dimension | Score |
| --------- | ----: |
| Scope clarity | 5 |
| Terminology | 4 |
| Requirement precision | 3 |
| Interface completeness | 3 |
| Data-contract completeness | 3 |
| State/lifecycle definition | 4 |
| Algorithm precision | 2 |
| Failure semantics | 3 |
| Edge-case coverage | 4 |
| Non-functional requirements | 3 |
| Security specification | 3 |
| Observability/provenance | 3 |
| Testability | 4 |
| Evaluation/metrics | 3 |
| Traceability | 4 |
| Internal consistency | 4 |
| Architecture consistency | 4 |
| Implementation readiness | 2 |

## 20. Remediation Plan

### P0 — Blocking

- F-001: Add dataset identity/hash to the manifest and define reproduction resolution.
- F-002: Pin distribution schemas, formulas, bounds, RNG, and category allocation.

### P1 — Important

- F-003: Define typed field descriptors.
- F-004: Define a safe constraint expression grammar.
- F-005: Define calculator registry and ground-truth errors.
- F-006: Define extraction, normalization, and regeneration seed semantics.
- F-007: Define atomic staging and partial-output protocol.
- F-008: Define metric formulas and denominators.

### P2 — Improvement

- F-009: Clarify optional GUI conformance boundary.
- F-010: Define artifact version compatibility policy.

## 21. Final Verdict

Specification maturity:
**Level 2 — Implementable**

Implementation readiness:
**NOT READY**

Primary blocker:
**Reproducibility and distribution semantics are not precise enough for two implementations to produce materially equivalent datasets.**

Most important improvement:
**Pin the manifest identity/reproduction protocol and every distribution/constraint semantic before implementation.**
