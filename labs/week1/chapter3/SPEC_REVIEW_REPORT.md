# Specification Review Report

**Target:** `SPEC.md` — *RAG Pipeline System (dense + hybrid retrieval, rerank, contextual, citations, + uv)*, status **v0.1 — draft for implementation**
**Reviewer:** spec-review skill (4-pass method: comprehension → local precision → cross-consistency → implementation simulation)
**Grounding:** *spec-only* review. Unlike ch1/ch2, **no implementation exists yet** — there is no `src/rag/` — so findings distinguish *spec defects* and *spec↔spec inter-consistency* issues from any code divergence. The 20 curriculum dimensions (§1–§28 of `curriculum/week1/chapter3.md`) are the intent this spec operationalizes; the review's job is to fix the residual **semantic uncertainty** between that intent and a verifiable build.
**Maturity scale:** 0 = absent · 1 = seriously deficient · 2 = weak · 3 = adequate · 4 = strong · 5 = implementation-grade
**Finding severities:** CRITICAL · HIGH · MEDIUM · LOW. **Remediation priorities:** P0 (blocking) · P1 (important) · P2 (improvement).

*(Sections §1–§21 of this review are written and committed chapter by chapter; see the report's git history.)*

---

## 1. Executive Summary

`SPEC.md` v0.1 is a **strong Level 2 (→ Level 3 after P0/P1)** specification, and one of the most disciplined lab deliverables in the curriculum. It operationalizes chapter 3's thesis — *RAG is a multi-stage, per-stage-measurable information-retrieval + probabilistic-generation system, not "embeddings + a vector database"* — into observable contracts: a deterministic-vs-probabilistic boundary that is *architecturally enforced by a source scan* (I-009/T-02, R-20); guarded, worked-example metric math for both retrieval (§20: P/R@k, MRR, MAP, NDCG) and generation (§21: faithfulness/completeness/citation_quality) with exact division-by-zero behavior (I-001/I-007, T-05a/b, T-08a); a full per-case state machine (I-008, §3.2) with complete retrieval diagnostics surviving a later-stage fault; seven curated **failure-mode tiers** (§14–§19) that make *where it failed* measurable (R-13/R-15); a grounded, offline, byte-reproducible `MockEmbedder` (FNV-1a hashed-BoW, O-1) that is the linchpin of the whole "RAG without a model" claim; and an explicit `id→where realized→test` traceability matrix with nine open questions (§11). The metric core, the failure-semantics core, and the architecture core are genuinely implementation-grade.

The spec is **not yet a clean Level 3** for one reason that is *different in character* from ch1/ch2's spec↔code drift: here the gaps are **unresolved semantic ambiguities that two competent implementers would resolve differently**, not a document lagging a written implementation. Three **HIGH** findings are material-divergence points:

- **F-001 (HIGH)** — the `MockLLM` is described as producing a "ground-truth-fit" answer, but its `LLM.generate` contract passes only `system/context/question` and *no* `gold_facts`/`gold_answer`, so it is undefined whether the offline generation metrics reflect *retrieval quality* (the chapter's thesis) or are *tautologically perfect*. This affects the central claim of §21.
- **F-002 (HIGH)** — the hybrid candidate-pool formation and the per-channel min-max normalization are under-specified: how the dense and lexical top-N sets combine, how a candidate present in one channel but not the other is handled, and the zero-range (all-equal-score) case are not fixed, so the headline *+hybrid* capability is not byte-deterministic (I-002).
- **F-003 (HIGH)** — `--contextual`/`--strategy` are **index-time** operations (§3.1) yet appear as query-time `eval` options (§5.1, §9.11), and the `build-index`→`eval` handoff (in-memory vs. pickle vs. rebuild-when-toggled) is undefined; this destabilizes the §22 per-capability experiment and T-20/T-21.

Eleven **MEDIUM** findings (generation-metric numerators, the `which_doc_decided` name-vs-meaning mismatch, conflict/recency precedence, token-budget vs. `est_tokens` bookkeeping, stale cross-refs, no access *principal*, and the like) and ten **LOW** findings (editorial/traceability) round out the set. **No finding is rated CRITICAL** — nothing is contradictory-to-the-point-of-impossibility or fundamentally unverifiable.

**Strengths (most important).**

- **Formal, guarded, worked-example metrics** for both families of measures (Evaluation/metrics 4.5, Algorithm precision 4).
- **Architecturally-enforced reliability boundary** — a source-scan invariant (I-009/T-02) that proves the deterministic layers name no `Ollama`/`httpx`/model, exactly the ch1 model answer, upgraded for RAG.
- **The `MockEmbedder` crux (O-1)** makes dense/hybrid retrieval *assertable offline* — a genuinely novel move that earns this spec its Level-2 ceiling.
- **Comprehensive, deterministic edge/failure semantics** (E-01…E-18 across all six §14–§19 failure modes) and a fully-traced `id→contract→test` matrix (§11).

**Weaknesses (most important).**

- **Three material ambiguities (F-001/002/003)** on the offline-generation metric, the hybrid pool, and the index/query toggle — all clarifiable, none a redesign, but enough that a second competent agent would build a meaningfully different system.
- **A cluster of inter-consistency defects** (F-004/007/008): a field named `which_doc_decided` that means "which *metadata field*," a stale `I-008 → E-15` trace pointer, and the injection banner mis-attributed to `E-13` (Ollama-unreachable) instead of `E-16` (injection).
- **Residual NFR/thin-security coverage**: `access_level` is stored but has no authorizing *principal* (F-009); the injection defense is correctly *flagged* but its *prevention* is only as strong as grounding + schema (F-21 / §18).

**Findings by severity.** 0 CRITICAL · 3 HIGH · 11 MEDIUM · 10 LOW. Total: **24 findings.** (Severities are stated per finding in §4; §20 prioritizes them P0/P1/P2.)

**Primary blocker:** **F-001** — the `MockLLM` gold-access contract is undefined, so it is *unspecifiable whether the offline generation/judgement metrics exercise retrieval or are tautological.* A faithful implementation-and-verification pair cannot be derived from v0.1 until this, F-002, and F-003 are resolved.

**Recommendation:** resolve the 3 HIGH (P0) + the 11 MEDIUM (P1) — all additive or one-line — to reach a clean **Level 3**. The LOW set (P2) is a Level-4 stretch. **No architectural change is recommended** (§17). The deterministic core is already implementation-grade; the work is *precision*, not *structure*.

---

## 2. Overall Maturity

**Level 2 — Implementable** (a competent agent *can* build the system), with an unusually short path to a clean **Level 3 — Implementation-grade** once the P0/P1 set in §20 lands. It is not yet Level 3, and it is not a "concept/direction" (Level 0/1): the ambiguity is *local and clarifiable*, not *substantial semantic decisions left to the implementer*.

### 2.1 Why it clears the bar for "implementable"

The specification already satisfies the Level-3 *gate* on every core surface:

- **Deterministic layers are zero-inference.** `build_index`/`search`/`cosine`/hybrid-mock/rerank-mock/expand-mock/`contextualize`/`build_context`/`est_tokens`/`metrics`/`corpus`+`generate_corpus_and_questions` have fully-specified contracts with exact worked examples (O-1 hashed-BoW, O-3 min-max, I-001/I-007 metric formulas, §C-01 dataclasses, K-03 default parameter table). An agent can implement these without a single semantic guess.
- **The probabilistic path is honestly bounded, not ignored.** R-09/R-10/R-17/R-18 correctly specify Ollama `generate`/`judge` as *best-effort* and confine all nondeterminism to two named components (R-20), with deterministic doubles for the suite. This is the right Level-3 posture for a system that *contains* probabilistic components.
- **Everything traces.** §11 maps every `R-/I-/E-/T-/K-` id to a contract and a test; 14 of 14 invariants and 13 of 13 constraints carry a `verified by` / measurement.

### 2.2 Why it stops short of clean Level 3

Three **material ambiguities** (F-001, F-002, F-003) are the defining Level-2→Level-3 gap, and they live exactly where a second competent implementer would most plausibly diverge:

1. **F-001 — the crux of the chapter.** `MockLLM` is "ground-truth-fit" but its contract carries no `gold*` data. *Two implementers:* one infers the double may read the question's `gold_facts` out-of-band (generation always perfect → the §21 retrieval-vs-generation split collapses into noise); one confines it to `context` (generation quality *tracks* retrieval → the thesis holds). Same document, opposite measurement. This is the difference between "a spec that describes a system" (Level 3) and "a spec that describes a *specific* system with a *specific* measurement" (Level 4).
2. **F-002 — the headline capability.** Hybrid (R-04) is a first-class, measured, per-capability feature, yet its candidate-pool formation and per-channel normalization (missing channel, zero range) are undefined, so I-002 byte-determinism cannot hold for `--hybrid on`.
3. **F-003 — the experimental method.** §22's whole value is "toggle a capability, re-run the *same* dataset, see which metric moved." If `--contextual`/`--strategy` are index-time but `eval` re-treats them as query-time, the *same dataset* premise of T-20/T-21 breaks.

### 2.3 Why it does not descend to Level 1/2-weak

Unlike ch1 (spec lagged the *written code* — a *drift* problem), this v0.1 **precedes** its implementation, so there is no divergence to reconcile; and unlike a Level-1 "direction" spec, it is not leaving *large* semantic domains open — the domains are *small and enumerable* (the 24 findings here). The maturity is therefore a **strong Level 2**, one P0/P1 pass from Level 3, and a further P2 stretch from Level 4.

### 2.4 What Level 4 would additionally require

Beyond P0/P1, Level 4 (verification-grade, *mechanically checkable contracts + unusual traceability/reproducibility*) would require:

- **A run-level provenance record** (a `run_id`/timestamp/`spec_version`/git-sha on the report aggregate) so a metric is self-describing after the fact — currently the per-*case* `RunMetrics` is rich, but the *run* is not (F-017, and the analog of ch1's F-019).
- **A canonical, ordered report** (F-017) so "byte-identical" (R-18/I-002) holds for the artifact, not just the in-memory values.
- **Exact-match, canonical error/`failure_stage` strings** (currently prose; see F-019, §4) and **a defined model-availability outcome taxonomy** (F-013, ch1's F-003 analog) so the `real` path's observable states are mechanically checkable.

These are stretch items; none is required for an implementation-grade (Level 3) build.

---

## 3. Findings Summary

**24 findings: 0 CRITICAL · 3 HIGH · 11 MEDIUM · 10 LOW.** They cluster into three themes: (1) **three material semantic ambiguities on the offline-generation/hybrid/index-query seam** that could drive divergence between two competent implementers (F-001/002/003); (2) **a cluster of inter-consistency / cross-reference defects** (`which_doc_decided` meaning, stale `I-008→E-15`, the `E-13`/`E-16` injection-banner mixup, metric-numerator definitions) (F-004/005/006/007/008); and (3) **editorial, traceability, and stretch items** (F-009…F-024). No finding is a redesign (§17); every P0/P1 is additive or a one-line clarification. The deterministic core (metric math, failure semantics, source-scanned reliability boundary, `MockEmbedder`) is implementation-grade and is *not* where the work lies.

| ID | Sev | Location | Issue (one line) |
| ---- | ---- | -------- | ---------------- |
| F-001 | HIGH | C-09/C-10 `MockLLM`/`MockJudge`, R-09, T-*8 | `MockLLM` is "ground-truth-fit" but its `generate` contract passes no `gold*`; it is undefined whether offline generation metrics exercise retrieval (the §21 thesis) or are tautological. |
| F-002 | HIGH | C-04 `O-3`/`HybridRetriever`, R-04, I-002 | Hybrid candidate-pool formation + per-channel min-max (missing channel, zero-range) undefined → `--hybrid on` not byte-deterministic. |
| F-003 | HIGH | §3.1, §5.1, §9.11, C-12 | `--contextual`/`--strategy` are index-time but appear as `eval` options; the `build-index`→`eval` handoff (pickle vs. rebuild) is undefined, breaking T-20/T-21's "same dataset" premise. |
| F-004 | MEDIUM | C-11, R-22, E-09/E-10 | `which_doc_decided` is named "which *doc*" but semantically means "which *metadata field*"; conflict/recency precedence (version vs. `updated_at` vs. authority) is unordered. |
| F-005 | MEDIUM | C-11, R-12, T-08a | `faithfulness = supported_claims / total_factual_claims` references `supported_claims`, which is not a `Verdict` field; must be defined as `total_factual_claims − len(unsupported_claims)`. |
| F-006 | MEDIUM | C-11, R-12, §21 | Generation numerators ("reflected gold_facts", "relevant citations") are undefined / not independently reproducible for the *real* judge. |
| F-007 | MEDIUM | I-008, §11, E-15 | `I-008`/`§11` trace failure-attribution to `E-15` (a `top_n` usage exit); attribution lives in `E-11` — a stale pointer. |
| F-008 | MEDIUM | §5.1, §C-08, E-13/E-16 | The injection banner is attributed to `E-13` (Ollama-unreachable) in three places; it belongs to `E-16` (injection). |
| F-009 | MEDIUM | C-01 `access_level`, R-22 | `access_level` is stored and advertised for "permissions" filtering but no authorizing *principal* or comparison rule is defined. |
| F-010 | MEDIUM | C-01/C-11/I-004/I-006, E-05, T-06 | Token budget vs. `est_tokens`: the truncation/"`Context.tokens ≤ budget`" check (ceil-of-concatenation vs. sum-of-per-doc-ceil) is not pinned, so `truncated`/`Context.tokens` are ambiguous. |
| F-011 | MEDIUM | C-02 lexical, R-04, §10 | The BM25/`idf` formula is "ch2 O-1 formula" by reference only; ch3 is not self-contained for the lexical channel (an implementer needs ch2's spec). |
| F-012 | MEDIUM | C-05, I-006, C-12 | After `--rerank on`, the canonical ranking key (`.rerank` vs. retained `.score`) and what `retrieved` mirrors is not fixed. |
| F-013 | MEDIUM | R-19, E-13/E-14, §5.1 | Model-availability outcomes (unreachable daemon → mock fallback vs. not-pulled model → error) are not unified into one outcome taxonomy with distinct banners (ch1's F-003 analog). |
| F-014 | MEDIUM | C-11 `MRR`, R-11, T-05a/b | `MRR` is written without an `@k` while `P/R/NDCG` are `@k`; `MRR@k` vs. full-rank `MRR` is ambiguous at the boundary. |
| F-015 | MEDIUM | E-04, E-14, T-01, I-007 | E-04's "ground-truth all-missing (`|G|=0`)*runtime*" branch is unreachable: absent `relevant_chunks` are a load-time error (E-14/I-013), so the guard is dead for the generated dataset. |
| F-016 | MEDIUM | R-18, §5.1 `--seed`, §10 | Where `--seed` is actually consumed among the content-determined mocks is unclear; "reproducible with a fixed seed" is vague for the mock path. |
| F-017 | LOW | R-18, I-002, §5.1 | The `report.json` aggregate order (`by_tier`/`by_capability`/`RunMetrics` rows) is not canonically ordered, so "byte-identical" (R-18) is at risk across dict/set iteration. |
| F-018 | LOW | C-01/C-11/I-005 | `est_tokens = ceil(len(s)/4)` does not state character-count vs. byte-count for non-ASCII; should fix one. |
| F-019 | LOW | §5.1 `--out` / "also -h stdout" | The "-h" for "also human-readable to stdout" collides with `argparse`'s `-h/--help`; clarify the human-vs-JSON split and the flag. |
| F-020 | LOW | §0, R-17, R-20 | "*one* probabilistic boundary" (§0) vs. "*two components — Embedder and LLM*" (R-20); reconcile the framing. |
| F-021 | LOW | C-12 `retrieved`, R-11, I-006 | Whether `RunMetrics.retrieved` is the top-*k* (the P/R@k denominator, `R_k`) or the top-*N* candidate pool is undefined. |
| F-022 | LOW | C-11 `Verdict.status`, E-12 | Under `--judge off`, whether a `Verdict` with `status="SKIPPED"` is produced or no `Verdict` exists (generation fields `None`) is unspecified. |
| F-023 | LOW | E-03 | Typo: a case is `SCORCED` rather than `SCORED`. |
| F-024 | LOW | C-03 `SemanticChunker`, Q-04/OQ8 | `SemanticChunker` is listed as a first-class `Chunker` subclass yet deferred; clarify it is out-of-scope-for-v0.1 so an implementer does not ship it. |

**Severity discipline.** No finding is CRITICAL: nothing is contradictory-to-impossibility or fundamentally unverifiable — the deterministic core is solid and the probabilistic path is honestly bounded (R-17/R-18). The three HIGH items are *material-divergence ambiguity*, not conceptual gaps or contradictions. The MEDIUM set is the work that must be cleared before claiming conformance/Level 3; the LOW set is improvement/Level-4 stretch. **Every P0/P1 is additive or a one-line clarification; none requires a redesign** (§17).
