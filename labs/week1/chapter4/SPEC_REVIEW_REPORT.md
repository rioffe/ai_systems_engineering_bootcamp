# Specification Review Report — chapter4 eval harness (`labs/week1/chapter4/SPEC.md`)

> - **Subject of review:** `labs/week1/chapter4/SPEC.md` (v0.1, eval harness for the ch3 RAG pipeline).
> - **Method:** four-pass review per the `spec-review` skill — Pass 1 comprehension, Pass 2 local
>   precision, Pass 3 cross-consistency, Pass 4 implementation simulation — across the skill's twenty
>   dimensions; findings labeled CRITICAL/HIGH/MEDIUM/LOW; scorecard 0–5; maturity Level 0–4.
> - **Summary:** Level 2 (Implementable). 15 findings: **0 CRITICAL, 4 HIGH, 7 MEDIUM, 4 LOW.**
>   Readiness: **NOT READY** — two semantic ambiguities (judge ownership, verdict-status mapping)
>   must be resolved before implementation.

## 1. Executive Summary

The SPEC is a strong v0.1: the scope boundary (an eval harness that *wraps* the ch3 RAG pipeline
through a pinned adapter rather than re-implementing it) is crisp, the requirement set is
observable-behavior oriented, the artifact-level architecture (`dataset_report.json`, `eval.json`,
`compare_report.json`, `gate_report.json`, `judge_check_report.json`, `pair_report.json`) makes
provenance first-class, and the deterministic-before-probabilistic ordering (checks → judge →
classifier) is the correct encoding of ch4 §5–§7. Stratification (`by_category`), direction-aware Δ
tables, hard-constraint gates, and label-anchored evaluator validity are all normative and
well-formed.

The review finds **15 findings — 4 HIGH, 7 MEDIUM, 4 LOW** (no CRITICAL). The four HIGH findings
cluster on the seam between the AoE (ch3) and the ch4 eval core: (F-001) who *owns* the verdict —
the AoE's internal judge or the harness's own; (F-002) the verdict-status enum mapping between ch3's
`PARTIAL`-capable status and ch4's `{PASS, FAIL, PARSE_BLOCKED}`; (F-003) `dataset_id`'s "stable
name/hash" ambiguity versus the §28 production loop that must be able to append cases and still
compare; (F-004) the unfloorable 50–100+ dataset-size rule versus the 5-row fixtures the test suite
uses. Until F-001/F-002 are resolved, two implementers can write substantively different verdict
pipelines — hence **NOT READY** (Level 2 — Implementable).

Strengths most worth preserving: explicit index/query flag partition (I-008/R-08), zero-denominator
semantics per metric (I-001/E-03), byte-identity formatting rules (I-002), fail-closed gates with
explicit `n/m` markers (E-07/E-11), and the label-evidence-only rule for `EVALUATION_FAILURE`
(I-017/E-16).

Weakest seams: verdict pipeline ownership and status enum (F-001/F-002), gates unit semantics
(F-005), PARSE_BLOCKED metric treatment (F-007), classification timing versus label ingestion
(F-008), and a handful of naming/traceability hygiene items (F-012).

## 2. Overall Maturity

**Level 2 — Implementable.** A competent engineer can build the harness end-to-end on the mock path,
and conformance of the deterministic core is largely objectively testable today (I-002/I-003/I-004).
The blockers preventing Level 3 are the unresolved high-severity seam issues above; the document is
explicit about being a pre-review v0.1 awaiting this pass, which is consistent with the ch3
workflow (v0.1 → review → v0.2). Level 3 requires the P0 items from the remediation plan applied.

## 3. Findings Summary

| Severity | Count | IDs |
| -------- | ----: | --- |
| CRITICAL | 0 | — |
| HIGH | 4 | F-001, F-002, F-003, F-004 |
| MEDIUM | 7 | F-005, F-006, F-007, F-008, F-009, F-010, F-011 |
| LOW | 4 | F-012, F-013, F-014, F-015 |

| ID | Severity | Subject | Location |
| --- | -------- | ------- | -------- |
| F-001 | HIGH | Verdict/judge ownership ambiguity between AoE result and harness evaluator | C-02 vs C-03 |
| F-002 | HIGH | Verdict-status enum mapping conflict (ch3 `PARTIAL` vs ch4 `{PASS, FAIL, PARSE_BLOCKED}`) | C-03, I-005 |
| F-003 | HIGH | `dataset_id` "stable name/hash" undefined → blocks §28 append-then-compare workflow | C-01, E-12 |
| F-004 | HIGH | 50–100+ dataset-size rule cannot bind `check` (tests use 5-row fixtures) | R-02, T-01 |
| F-005 | MEDIUM | Gates unit semantics (`max_pct_points` vs `max_pct`) and constraint-parameter pairing undefined | C-07 |
| F-006 | MEDIUM | `run` behavior on an invalid dataset unspecified (E-02 scoped to `check` only) | §5.1, E-02 §9.1 |
| F-007 | MEDIUM | Metric semantics for `PARSE_BLOCKED` verdicts (accuracy/completeness) undefined | C-04, I-005 |
| F-008 | MEDIUM | Classification step 2 (label-evidence `EVALUATION_FAILURE`) ordering vs ingestion undefined | C-08, §3.2 |
| F-009 | MEDIUM | MRR/MAP/NDCG reused from ch3 but absent from `METRIC_KEYS` — report coverage ambiguous | §0, §1, C-04 |
| F-010 | MEDIUM | Global `--model` flag ambiguous (generation model vs judge model vs both) | §5.1, R-15 |
| F-011 | MEDIUM | `pair` config JSON schema unspecified (gates.yml has schema; pair configs do not) | C-10, §5.1 |
| F-012 | LOW | Test-id collisions (`T-08a`, `T-13`) and untested edge cases (E-01, E-05, E-08, E-14, E-17) | §9, §11 |
| F-013 | LOW | `usage_kind` synthetic-vs-measured mismatch unguarded at `compare` | C-02, C-06 |
| F-014 | LOW | `run` exit-code row omits the K-01 usage-error code | §5.1 vs K-01 |
| F-015 | LOW | `by_difficulty` asymmetric presence in `compare` unspecified | R-05, C-06 |

---
