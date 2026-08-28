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

---

## 4. Detailed Findings

Each finding follows the skill's format: **Observation · Why it matters · Potential consequence · Recommended resolution**, with location and severity. Quoted spec text is from v0.1. Findings F-001…F-024 continue in the following two subsections (§4.2, §4.3).

### 4.1 F-001 … F-008

#### F-001 — `MockLLM` gold-access contract is undefined (the §21 crux)

**Severity:** HIGH **Location:** C-09 `LLM.generate`/`MockLLM`, C-10 `MockJudge`, R-09, T-08/T-11.

**Observation** C-09 comments that `MockLLM` "*derives a schema-valid, GROUND-TRUTH-FIT Answer* from **question + assembled context**" — but the `LLM.generate` contract it must satisfy is `generate(*, system, context, question, schema, …)` and carries **neither `gold_answer` nor `gold_facts`**. The `Judge` *does* receive `gold_facts` (C-10), but the model being judged does not. The phrase "ground-truth-fit" is therefore under-defined as to *what* the mock is permitted to read.

**Why it matters** This is the chapter's central claim — *generation quality must be measured *separately* from retrieval quality (§21)*. If `MockLLM` may read `gold_facts` out-of-band, the offline generation metrics (faithfulness/completeness/citation_quality) are **near-tautologically perfect** and can never reveal a retrieval failure; the §21 split collapses. If it is confined to `context`, its fidelity *tracks retrieval* and the split is meaningful — but then the "ground-truth-fit" wording is an overstatement. Two readings produce materially different, contradictorily-tested suites.

**Potential consequence** The *test test* fails: a verifier cannot write T-11/T-08 without knowing whether the mock sees ground truth; two implementers build different suites; the headline diagnostic ("did the model *use* the evidence vs. did retrieval *provide* it") is either real or vacuous depending on an unspoken choice.

**Recommended resolution** Fix the *intended* semantics: `MockLLM` derives the answer **only from `context`+`question`** (no `gold*`), so its `supported`/`completeness` depend on what retrieval delivered — this is what makes §21 measurable. Add a one-line assertion to T-11/T-08: a `chunking`/`distractor`-tier run with degenerate retrieval yields `completeness < 1.0`/low `faithfulness`, proving the metric *varies* with retrieval. Reword "ground-truth-fit" to "*schema-valid, evidence-grounded (from the assembled context)*." If gold-access is desired for a separate "oracle" check, define it as a *distinct* double and scope it out of the scored path.

---

#### F-002 — Hybrid candidate-pool + per-channel normalization under-specified

**Severity:** HIGH **Location:** C-04 `HybridRetriever`/`O-3`, R-04, I-002, T-07.

**Observation** `O-3` says each channel's raw scores are "*min-max-scaled to `[0,1]` over the query's own candidate set*" and defines only the **single-candidate** degenerate (→ `1.0`, E-03). It does not fix: (a) **how the candidate universe is formed** — `HybridRetriever.retrieve` retrieves on *both* channels, but is the pool the *union* of dense-top-N and BM25-top-N, the *intersection*, dense-top-N scored on both, or something else? (b) **a candidate present in one channel but absent from the other** — is its missing-channel raw score `0`, `min`, or excluded from that channel's min-max? (c) the **zero-range** case where two or more candidates share identical raw scores on a channel (min-max is `0/0`).

**Why it matters** These are the exact variables that make `--hybrid on` byte-deterministic (I-002, R-18). The *implementation test* fails: union-vs-intersection and missing-channel handling are the two most plausible divergences for a headline capability, and `T-07` ("reproduces the documented per-query normalization") has no candidate pool to pin.

**Potential consequence** Two implementers produce different blended rankings / different `retrieved` orders for the same `--hybrid on` run; the per-capability `+hybrid` diff in `by_capability` (R-14) is not comparable.

**Recommended resolution** Specify the pool (recommend **union of dense-top-N and BM25-top-N, deduped by `chunk_id`**) and missing-channel handling (recommend **missing = raw `0.0`, participating in that channel's min-max so it cannot accidentally win** — or document an alternative), and define the **zero-range** rule (recommend: on a zero-width channel, all its candidates normalize to `1.0`, with `chunk_id asc` tie-break, consistent with `O-1b`). Pin a worked hybrid example (a crafted equal-score set) into T-07.

---

#### F-003 — index-time vs. query-time toggle + `build-index`→`eval` handoff

**Severity:** HIGH **Location:** §3.1, §5.1, §9.11, C-12 `build_index`/`run_case`, R-07/T-20, R-03/T-21.

**Observation** §3.1 fixes indexing as an **index-time** scope: "*at index time each chunk's **embedding** text is the context-prefixed form*" (R-07) and `build_index(docs,*, strategy, contextual, …)` is what carries `--contextual`/`--strategy`. Yet §5.1 lists `--contextual on|off` and `--strategy heading|fixed` as **common `eval` options**, and §9.11 runs `uv run rag eval --contextual on` / `--hybrid on` / `--rerank on` as *query-side* toggles. It is undefined whether toggling `--contextual`/`--strategy` at `eval` time is a **no-op**, a **rebuild**, or an **error**. The `build-index`→`eval` handoff is equally open: §5.1 says `build-index` emits "the index object the `eval` command consumes" (in memory **or** a pickle), so `eval` either reloads a *previously built* index (in which case `--contextual`/`--strategy` must be `build-index` flags) or rebuilds (in which case the pickle is vestigial).

**Why it matters** §22's entire value proposition is "toggle a capability and **re-run the *same* dataset**; see which metric moved." T-20/T-21 assert that `+contextual` *recovers* a split chunk — only recoverable if the toggle re-indexes. Left open, the experiment and its tests are not reproducible as written.

**Potential consequence** Divergence on whether `eval --contextual on` does anything; T-20/T-21 become un-assertable; the per-capability diff may silently compare *different corpora*, the antithesis of §22.

**Recommended resolution** Partition the toggles explicitly: **index-time** (`--strategy`, `--contextual`, `--chunk-size`, `--overlap` — must be `build-index` and force a rebuild) vs. **query-time** (`--hybrid`, `--rerank`, `--llm-rerank`, `--expand`, `--n-expand`, `--alpha`, `--model`, `--embed-model`, `--judge`, `--k`, `--top-n`, `--tiers`). State that `eval` **rebuilds from the corpus** when any index-time flag changes (and make the pickle an optional cache keyed by a hash of these flags), and rewrite §9.11 so a `+contextual`/`+strategy` "diff" re-runs `build-index` before `eval`.

---

#### F-004 — `which_doc_decided` name ≠ meaning; conflict/recency precedence unordered

**Severity:** MEDIUM **Location:** C-11 `Verdict.which_doc_decided`, R-22, E-09, E-10, T-17.

**Observation** The field is **named** `which_doc_decided` (an implementer will read this as a *document id*), but C-11's comment and E-09/E-10 say it records "*which **metadata field** resolved conflict/recency*" (i.e. `"version"` or `"updated_at"`), not which document. Separately, `R-22`/E-09 resolve conflict/recency by "*highest `version` / most-recent*" but leave the **precedence** between `version` and `updated_at` (and `access_level`/"authority") undefined when they disagree; `version: int | float | None` also mixes two orderings and a `None`.

**Why it matters** The name/semantics mismatch is a direct mislead for the field most central to the `conflict`/`recency` tiers; an undefined precedence means two implementers order the same pair of disagreeing policies opposite ways, flipping `correct`/`failure_stage` for E-09/E-10.

**Potential consequence** `T-17`/E-09/E-10 become non-deterministic on conflicting metadata; report consumers misread `which_doc_decided`.

**Recommended resolution** Re-name to `which_field_decided` (or state explicitly "stores the field name, not the doc id") and fix its value domain (`"version"|"updated_at"|null`). Define a **total precedence** for the resolution (`version` > `updated_at` > `access_level`, say), and define `None`/type-mix tie behavior — pin a worked case in T-17.

---

#### F-005 — `faithfulness` denominator references a non-existent `supported_claims` field

**Severity:** MEDIUM **Location:** C-11, R-12, T-08a.

**Observation** R-12 / the §C-11 equation define `faithfulness = supported_claims / total_factual_claims`, but the `Verdict` schema exposes `supported: bool`, `unsupported_claims: array[str]`, `total_factual_claims: integer` — **no `supported_claims` field**. T-08a infers it: "*`total_factual_claims=4, unsupported=1` → `faithfulness = 3/4`*", i.e. `supported_claims = total_factual_claims − len(unsupported_claims)`.

**Why it matters** The formula names a denominator-term the schema does not carry; the arithmetic is only recoverable by inference that `supported = total − |unsupported|`, and even that must be reconciled with the `grounding_violation` recount (I-003 drops foreign ids into `unsupported_claims`).

**Potential consequence** Divergence on the faithfulness denominator across the real vs. mock judge when `grounding_violation` reclassifies claims; a verifier cannot pin the worked example without the definition.

**Recommended resolution** Either add `supported_claims: int` (or a `recomputed_supported`) to the `Verdict` schema, **or** state the invariant `supported_claims ≡ total_factual_claims − len(unsupported_claims)` and that the I-003 recount updates `unsupported_claims` before `faithfulness` is computed — and pin that ordering in T-08a.

---

#### F-006 — generation-metric numerators undefined / not reproducible for the *real* judge

**Severity:** MEDIUM **Location:** C-11, R-12, §21 (faithfulness/completeness/citation_quality).

**Observation** The three generation numerators are only loosely defined: `faithfulness = supported_claims / total_factual_claims` (see F-005); `completeness = "reflected gold_facts" / |gold_facts|`; `citation_quality = "relevant citations" / total citations`. For the **`MockJudge`** these reduce to a documented string/`chunk_id` *intersection* with `gold_facts`/`relevant_chunks`, but for the **`OllamaJudge`** "*reflected*" and "*relevant*" are undefined — a claim is "reflected" *how*? A citation is "relevant" *to what*? (an answer claim, a `gold_fact`, or a `relevant_chunk`?)

**Why it matters** §16 of the review explicitly warns to "be suspicious of a metric directly supplied by the component being evaluated." For the real judge, `completeness`/`citation_quality` are *self-reported by the judge* unless "reflected"/"relevant" are tied to an external reference (`gold_facts`/`relevant_chunks`) with an explicit matching rule.

**Potential consequence** The real-judgment metrics are not independently reproducible; the `by_capability` diff mixes a reproducible mock column with an opaque real column.

**Recommended resolution** Define each numerator as a **reference-bound, deterministic** check: `relevant_facts ⊆ gold_facts` matched by a fixed rule (e.g. the mock's normalized-token overlap; the real judge's emitted `reflected_facts` intersected with `gold_facts`); `relevant_citations = {c : c.chunk_id ∈ relevant_chunks} ∪ {c : c.claim matches a gold_fact}`. State that the *real* judge *emits* `reflected_facts`/`relevant_citations` that are then **intersected with the reference** (never taken at face value), keeping §16's independence intact.

---

#### F-007 — `I-008`/§11 trace failure-attribution to the wrong edge case (`E-15`)

**Severity:** MEDIUM **Location:** I-008, §11 (`R-15 / I-008 → … E-15`; `§19 multi-hop → … E-15`), E-15 vs. E-11.

**Observation** I-008 ("*Every terminal `ERROR`/`PARTIAL` names exactly one `failure_stage`*") is annotated `verified by T-10, E-15`, and §11 routes `R-15 / I-008` → `E-15` and `§19 multi-hop` → `E-15`. But `E-15` is "*`--top-n` smaller than `--k`, or `Reranker.top_k > len(candidates)` → **a usage error (exit 2)**" — a *CLI-usage* exit, not a terminal *case* row; failure-attribution of `generation`/`judging` lives in **`E-11`** ("`failure_stage` is `"generation"` or `"judging"`").

**Why it matters** A stale trace pointer misdirects the very invariant that makes §21's diagnostic trustworthy, and the `§19 multi-hop → E-15` pointer is doubly wrong (multi-hop is the `multi` tier; its home is T-04b), so an implementer chasing `E-15` learns nothing about multi-hop.

**Potential consequence** A verifier following the matrix tests the wrong edge; the trust in I-008 (and its §11 trail) is undercut by a pointer that names the *neighboring* edge.

**Recommended resolution** Re-point I-008/T-10's edge to **`E-11`** (+ `E-12` for the `--judge off` PARTIAL/SKIPPED case); correct §11's `§19 multi-hop` row to `T-04b`/`T-23`. Sweep §11 for other stale `E-15` usages.

---

#### F-008 — the injection banner is attributed to `E-13` (Ollama), not `E-16` (injection)

**Severity:** MEDIUM **Location:** §5.1 (item 3 `§18, E-13`; GUI `INJECTION! badge (E-13)`), C-08 step 3 (`INJECTION SCAN (E-13/R-21)`), E-16 (`the report prints the injection banner (§5.1, E-13/§18)`).

**Observation** The **injection warning/banner** is attributed to **`E-13`** in four places (§5.1 item 3 and GUI badge, C-08 step 3, and E-16's own cross-ref). But `E-13` is "*`Ollama / an embed model unreachable` … **degrades to the mock doubles** and prints a banner*" — a *runtime-availability* edge, not the injection edge. The **injection** edge is `E-16` (and the `injection`-tier realization), which already *owns* `injection_warning=True` and the banner.

**Why it matters** The two edges are *conceptually distinct* (daemon-unreachable vs. adversarial-payload-in-evidence) and *behaviorally distinct* (one **degrades the whole pipeline to mocks + a runtime banner**; the other **scores the row normally + an injection badge**). Conflating their banner is exactly the kind of cross-reference that misleads an implementer's UI/error-string wiring and undermines a mechanically-checkable "banner" assertion.

**Potential consequence** GUI/report code wires the injection badge to the wrong handler; error-string/`banner` tests target the wrong branch; the §18 "measurable security boundary" is attributed to a runtime-availability edge.

**Recommended resolution** Re-attribute every injection-banner citation from `E-13` to `E-16` (§5.1 item 3, the GUI badge, C-08 step 3); keep `E-13` strictly for *Ollama-unreachable → mock degradation*. Give each a **distinct banner string** (see F-013) and pin both in a T (T-16 for the GUI badge on an `injection`-tier run; a new T-row for the runtime-degradation banner on the real path).

---

### 4.2 F-009 … F-016

#### F-009 — `access_level` has no authorizing *principal*

**Severity:** MEDIUM **Location:** C-01 `ChunkMetadata.access_level` (default `"employee"`), R-22 ("*…`permissions`*"), actor table (`User (human, single process)`), §1 `+ metadata` ("*filter … permissions*").

**Observation** R-22 lists `access_level` as a loadable/usable field for "filtering, recency ranking, authority/version resolution, **and citation**," and §1 advertises "filter/rank by … **permissions**." But the `User` actor is "*single process*" and no **requesting principal** (its own `access_level`/role/identity) or a **comparison rule** (which chunks may a given principal see?) is defined. `access_level` is stored without any consumer.

**Why it matters** In a single-user CLI the filtering may be a no-op, but the spec *advertises* a permissions capability it does not *close* — an implementation test gap: two implementers will either (a) ignore `access_level` or (b) invent a principal. The "permissions" claim in §1/R-22 is aspirational (§3.3) rather than an observable obligation.

**Potential consequence** Either `access_level` is dead metadata, or an implementer introduces an ad-hoc principal; the `citation`/`filtering` use of `access_level` is unassertable.

**Recommended resolution** Either (a) **scope out** permissions filtering for v0.1 — state explicitly that `access_level` is *carried through and ignored* in single-process mode (drop "permissions" from §1/R-22's headline uses, keep it as a field for a future multi-tenant extension), or (b) define a `principal` + a monotone `access_level` ordering and a "*include iff principal.level ≥ chunk.level*" filter rule with a T. Do not leave the capability half-open.

---

#### F-010 — token-budget vs. `est_tokens`: which count drives truncation

**Severity:** MEDIUM **Location:** C-11/C-03 `est_tokens`/`Context.tokens`/`truncated`, I-004/I-005/I-006, E-05/E-06, T-06/T-06b/T-11.

**Observation** I-004 requires "*`Context.tokens ≤ token_budget` always*" and I-005 fixes `est_tokens(s) = ceil(len(s)/4)` as "*the single formula used identically by the context builder and the report.*" But it is undefined whether `Context.tokens` is (a) `est_tokens` over the **concatenated** context string, or (b) the **sum** of `est_tokens` over each included doc. Because `ceil` is sub-additive (`ceil(a/4)+ceil(b/4) ≠ ceil((a+b)/4)` in general), the two definitions agree most of the time but **disagree at the boundary**, and that boundary is exactly where E-05/T-06 assert `truncated=True` "*iff* a doc was dropped."

**Why it matters** I-005 promises *one* formula, but "the count that is checked" and "the sum that builds" can be *two* different roundings; the `truncated` predicate (`I-004`, "iff a doc was dropped") can then flip between a builder that uses sum-of-ceil and a report that uses ceil-of-concatenation, violating I-006 ("report equals build").

**Potential consequence** Boundary flaps in T-06/T-06a; an implementer's `truncated` can disagree with the reported `context_tokens`.

**Recommended resolution** Fix one convention: `Context.tokens = Σ est_tokens(doc_text)` over the *included* docs, and the `truncated` predicate checks the **running sum against the budget *before* appending the next doc** (first doc that would exceed is dropped → `truncated=True`). State that `I-004`/`I-006` reference this same running sum, not a re-ceil of the concatenation.

---

#### F-011 — the BM25/`idf` formula is referenced, not inlined

**Severity:** MEDIUM **Location:** C-02 (lexical `BM25Index`), R-04, §10 (*"ch2 O-1 formula, k1=1.5, b=0.75"*).

**Observation** The lexical channel is defined as "*the ch2 O-1 formulas with the same tokenizer (O-1a); `k1=1.5, b=0.75`*" and `BM25Index.search` gives only a one-line signature. The actual `score(q,d)` / `idf(t)` bodies live in **ch2's** spec. This spec is *not self-contained* for the lexical channel it blends into the headline hybrid result.

**Why it matters** A reviewer/implementer working **only** from ch3's `SPEC.md` cannot reproduce the `s_lex` used in `O-3`'s min-max; the hybrid result (F-002) depends on a formula in another document. `idf` has at least two common variants (e.g. `ln(1+(N−|D_t|+0.5)/(|D_t|+0.5))` vs. `(N−|D_t|)/|D_t|`), so "the ch2 O-1 formula" is not one function without the text.

**Potential consequence** Two implementations of `s_lex` diverge; the ch3↔ch2 coupling is invisible to a fresh implementer; `T-07` depends on an out-of-scope formula.

**Recommended resolution** Inline the BM25 `score`/`idf`/tokenizer (O-1a) into C-02 as a short worked formula (or a clearly-labelled *excerpts* from ch2 O-1 with a version pin), and add a one-paragraph "this reuses ch2 §…" with a *change-detection note* so a ch2 change cannot silently move the ch3 baseline.

---

#### F-012 — post-rerank canonical ranking key / what `retrieved` mirrors is not fixed

**Severity:** MEDIUM **Location:** C-05 `Reranker`/`MockReranker` ("*descending `ScoredChunk.rerank`*"), C-01 `ScoredChunk` (`score`/`semantic`/`lexical`/`rerank`/`rank`), I-006, C-12 `RunMetrics.retrieved`.

**Observation** `MockReranker.rerank` produces `ScoredChunk.rerank`, and the reranker "*re-rank (descending `ScoredChunk.rerank`)*." But `ScoredChunk.score` is defined as "*the *combined* ranking score (hybrid when `--hybrid`, else the winning channel)*," which is the **pre-rerank** value, and `rank` is "*1-based position in the *final* ranked list.*" It is undefined whether, when `--rerank on`, (a) `.score` is rewritten to the rerank output, (b) only `.rerank` is set and the final order is by `.rerank` while `.score` lags, or (c) both. And `I-006` requires `retrieved` to mirror "*the ranking actually assembled*" — which ranking, when `.score` and `.rerank` disagree?

**Why it matters** This is the single point at which the *report's* ranking (used for P/R@k, MAP, NDCG — all computed on `retrieved`) could diverge from the *displayed* rerank order. The test test fails: a verifier cannot assert `retrieved == final order` without knowing which field is canonical.

**Potential consequence** P/R@k/NDCG computed on the pre-rerank order while the UI shows the post-rerank order (or vice-versa); the `+rerank` per-capability diff (R-14) is not well-defined.

**Recommended resolution** State that with `--rerank on` the **canonical final order is by `.rerank` (desc, `chunk_id` asc tie-break)** and that `retrieved`/I-006 mirror **this** order; define whether `.score` is frozen (pre-rerank, for the "+rerank diff" baseline) or overwritten; pin in T-23/T-11.

---

#### F-013 — model-availability outcomes are not unified (ch1 F-003 analog)

**Severity:** MEDIUM **Location:** R-19, E-13, E-14, §5.1 exit codes, §4 `+ metadata`/GUI banner.

**Observation** The real path has at least **three** distinct runtime situations but only two behaviors: **unreachable daemon** → "*degrades to the mock doubles and prints a banner*" (E-13); **daemon up but `--embed-model`/`--model` not pulled** → "*a clear `pull required` error rather than a crash*" (R-19). E-14 is a *corpus* load error. These three are conflated under "E-13/E-14" in several cross-refs, and the **banner string** for the mock-degradation is not fixed, so it collides with the injection banner (F-008). (This mirrors ch1's `discover_registry` finding: one boolean with one banner for distinct conditions.)

**Why it matters** Three observable states (UNREACHABLE-DAEMON / REACHABLE-MODEL-ABSENT / REACHABLE-POPULATED) need distinct behaviors **and** distinct banners; a conflated banner misleads the human about *why* the mock is running, and the GUI `INJECTION!` badge could never be disambiguated from the runtime-degradation banner.

**Potential consequence** A human reading "mock" on screen cannot tell *reachable-but-empty-model* from *daemon-down*; GUI banner wiring is ambiguous with F-008.

**Recommended resolution** Define an **outcome enum** `{DEGRADED_MOCK (daemon unreachable), PULL_REQUIRED (model absent: emit `ollama pull <m>` + exit 4), RUN_REAL}` with a **distinct, canonical banner per outcome**, and unify E-13/E-14's cross-refs. This is the ch1 F-003 fix, adapted.

---

#### F-014 — `MRR` is written without an `@k` while `P/R/NDCG` are `@k`

**Severity:** MEDIUM **Location:** C-11 `MRR` equation, R-11, T-05a/T-05b.

**Observation** R-11 names the family "*`Precision@k`, `Recall@k`, `MRR`, `MAP`, `NDCG@k`*" — three measures carry `@k`, `MRR` does not. The §C-11 equation `MRR = 1/rank(first g ∈ R_k)` *implies* `MRR@k` (first relevant *within top-k*, else `0`), but "in `R_k`" is the only thing pinning it; the worked example (T-05b, `MRR=1.0`, rank 1) does not distinguish `MRR@k` from full-rank `MRR`. With `k=5` (K-03) and first-relevant at rank > 5, the two readings differ (`0` vs. `1/rank`).

**Why it matters** `MRR` feeds `RunMetrics.mrr` and the aggregate; an off-by-k boundary case (first relevant at rank 6) yields a different reported value under the two readings, so `by_tier`/`by_capability` diffs can disagree.

**Potential consequence** Divergent `mrr` in the report / aggregate; T-05a/b do not cover the rank > k case.

**Recommended resolution** Adopt `MRR@k` (first relevant within top-`k`, else `0`) explicitly, add `MRR@k` to R-11 and the `RunMetrics` field comment, and extend T-05b with a rank > `k` sub-case to pin the `0` behavior.

---

#### F-015 — E-04's "ground-truth all-missing" runtime branch is unreachable

**Severity:** MEDIUM **Location:** E-04, E-14/I-013, T-01, I-007.

**Observation** E-04 says the `|G| = 0` guard fires on "*a query whose ground-truth is also **empty or all-missing** (`|G|=0`)*." But T-01 requires every question to have **non-empty** `relevant_chunks`, and I-013/E-14 make "*a `relevant_chunks` id absent from the built index*" a **load-time error** (exit 3) that prevents the run. So the `|G| = 0` *runtime* branch (with `|G|` computed as the count of `relevant_chunks` *present* in the index) cannot be reached: by the time a case runs, all `relevant_chunks` are guaranteed present. The only route to it is `gold_facts = []`, which T-01 forbids for the generated set (and which is the *completeness* denominator, not `G` for retrieval `|G|`).

**Why it matters** The guard is *defensive but dead* for the specified dataset; leaving it implies a runtime path that does not exist, and an implementer may build a branch that T-* cannot trigger without an out-of-spec corpus — weakening the otherwise-strict E↔T correspondence.

**Potential consequence** A dead guard confuses the failure model; a verifier can't exercise it from a T without first violating T-01/E-14.

**Recommended resolution** Either (a) **mark E-04 explicitly defensive** — "*unreachable under T-01/E-14; present only as a divide-guard for a hand-edited corpus*" and reference it only by I-007, or (b) **add a T** that constructs a corrupted-then-hand-edited dataset (a `synthetic` corpus) and assert the `None` behavior — and drop "all-missing*runtime*" from E-04's wording, confining it to a *completeness* empty-`gold_facts` case.

---

#### F-016 — where `--seed` is consumed is unclear

**Severity:** MEDIUM **Location:** R-18, §5.1 `--seed`, §10 (*"seed threading (corpus + mock paths)"*), O-1, §C-06 `MockQueryExpander`.

**Observation** R-18 promises "*with a fixed `seed` on the **mock** path, all deterministic outputs … are reproducible/byte-identical*," and §11 traces `R-18 → seed threading (corpus + mock paths)`. But the mock doubles are *content-determined* — `MockEmbedder` uses **fixed** FNV-1a (no seed, by design, O-1), `MockReranker`/`multi_query` are functions of their inputs, and `MockJudge` derives from `gold_facts`/`claims`. The **only** genuine use of `seed` is `gen-corpus` (which writes the corpus). `MockQueryExpander` is "*seeded*" yet its templates + fixed synonym map are deterministic *without* a seed. So the contract says "*seeded*" for objects whose determinism does not depend on the seed.

**Why it matters** "*Reproducible with a fixed seed*" is a weaker promise than the determinism the spec actually delivers; an implementer may *add* a seeded RNG to a mock "to honor R-18" and thereby **degrade** the byte-identical guarantee, or *omit* seed threading to a mock that genuinely randomizes (future `LLMQueryExpander`, `LLMReranker`).

**Potential consequence** The `R-18`/T-03/T-07 byte-identical contract is either *stronger than promised* (an implementer adds needless entropy) or *weaker than needed* (a future mock is non-deterministic and the suite is "seeded-but-wonky").

**Recommended resolution** For each mock double, declare precisely which of `seed` / inputs / both determine its output (recommend: corpus = `seed`; mocks = **inputs only**, `seed` ignored), and update `--seed`'s help to say "*affects gen-corpus; the mock doubles are input-determined*." Add a test that a second `gen-corpus --seed 42` is byte-identical but a `gen-corpus --seed 7` is not, pinning the *seed surface* itself.

---

### 4.3 F-017 … F-024 (LOW)

#### F-017 — `report.json` ordering not canonically fixed, jeopardizing R-18 byte-identity

**Severity:** LOW **Location:** R-18/I-002, §5.1 (JSON report), C-11 `by_tier`/`by_capability`.

**Observation** R-18 promises "*computed metrics … reproducible/byte-identical*." The aggregate carries `by_tier` (per populated tier) and `by_capability` (per toggled stage); these are naturally **dict/set**-keyed. Without an **ordering discipline** (e.g. `tier`/`capability` keys sorted; `RunMetrics` rows in `--tiers` or `q_id` order), the serialized `report.json` can vary with dict/set iteration across Python builds, breaking byte-identity *between runs* on the same machine.

**Why it matters** "*Byte-identical*" (R-18, the determinism crux of the whole spec) is only meaningful for the *artifact*, not just the in-memory floats. A verifier comparing two `report.json` files needs a deterministic serialization.

**Potential consequence** `git diff report.json` is noisy across runs even with identical inputs; a CI byte-equality test would flap.

**Recommended resolution** Specify the report serializer: `RunMetrics` rows in `q_id` order; `by_tier`/`by_capability` keyed by a **sorted** canonical order; `json.dumps(..., sort_keys=True, indent=2)` with fixed float formatting; and add a T that two `eval --mock` runs are byte-identical *files*.

---

#### F-018 — `est_tokens = ceil(len(s)/4)` does not state char vs. byte

**Severity:** LOW **Location:** C-01 `Chunk.tokens`, C-11 `est_tokens`, I-005, T-06/T-06b (O-2 *"analog of ch2*").

**Observation** `est_tokens(s) = ceil(len(s)/4)` is fixed as the single formula but the **unit of `len(s)`** is not: in Python `len(str)` is *characters* (so an emoji counts as 1), but many real tokenizers count bytes or sub-word units. The §C-01 comment "*(same formula as ch2 O-2, I-006)*" pins the *shape* but not the *unit*.

**Why it matters** With non-ASCII corpus text (travel/finance docs might include a `—` or a non-ASCII quote), byte-count and char-count differ, moving `context_tokens`/`truncated` and so `I-006` (report = build) is only provable for ASCII.

**Potential consequence** A non-ASCII corpus yields a `context_tokens` disagreement *between the builder and the report* if one uses `len` and the other `len(encode())`.

**Recommended resolution** State "*`len` is the Python character count (`len(str)`, UTF-16-code-unit-independent of encoding) — **not** a byte or sub-word count*; non-ASCII is out-of-scope for the estimator." Optionally pin a non-ASCII case in T-06b.

---

#### F-019 — "`--out` … also `-h` stdout" collides with `argparse`

**Severity:** LOW **Location:** §5.1 options and "1. A **human-readable summary** to stdout … 2. … `--out`." The line "*write the JSON report (default: `report.json`; also `-h` stdout)*" overloads `-h`.

**Observation** §5.1 item 2 says "*write the JSON report (default: `report.json`; also `-h` stdout)*" but then `--out PATH write the JSON report (default: report.json; also -h stdout)` — the token `-h` is, in the standard `argparse` (the natural choice for a `rag` CLI), the **help** flag. Conflating "*also print human-readable to stdout*" with the help flag is a real usability bug waiting to happen, and the report's **human summary** (item 1) already *is* the stdout human output, so it is unclear which "`-h`" is meant.

**Why it matters** A CLI that reuses `-h` for something other than `help` (the universal convention) will surprise every human user, and any test that runs `rag --h` to get a human report would collide with `--help`.

**Potential consequence** The CLI either *silently* hijacks `-h` (breaking `--help`) or the "*also `-h` stdout*" phrase is interpreted as the human summary, in which case the JSON report is the *only* file output and the human summary is implicit.

**Recommended resolution** State the two output channels precisely: **human summary → always `stdout`**, **JSON report → `--out PATH`** (default `report.json`); **drop the `-h` shorthand** entirely (let `--help` be `argparse`'s). Add `--quiet` (already present) as the knob to suppress the human summary when only JSON is wanted.

---

#### F-020 — "one probabilistic boundary" vs. "two components: Embedder + LLM"

**Severity:** LOW **Location:** §0 ("*the generator/judge is the **one** probabilistic boundary*"), R-20 ("The **probabilistic boundary is two components** — the **Embedder** and the **LLM**"), actor table (`Embedder`, `LLM`).

**Observation** §0 first calls generation the *one* probabilistic boundary, then R-20 corrects/replaces it with *two* components (Embedder + LLM). Both are *true* — the real path has two Ollama calls — but the language is inconsistent: the §0 framing reads as one boundary and then R-20 says two. The §C-08/C-02 `source-scan` invariant (I-009/T-02) lists *three* modules (`embedding.py`, `model.py`, `judgment.py`) — so the *operational* story is *two interfaces × two roles* = *three modules*.

**Why it matters** The *reliability-boundary* story of the spec is its central pitch (ch1 §15 → ch2 → ch3 §0/R-20). If "one boundary" vs. "two components vs. three modules" are not reconciled, a fresh reader may not know whether I-009's three-module source-scan is a *consequence* of two-component-or-three-module or an *independent* design choice, and whether expanding/judging is "part of" the generative boundary or a *second* boundary it *happens* to reuse the LLM module for.

**Potential consequence** A reader/verifier misreads *what* the boundary is and *why* I-009 scans 3 modules rather than 2; the pitch loses one click of clarity.

**Recommended resolution** State cleanly: "*The system has **one** reliability boundary — the *probabilistic boundary* — realized by **two Ollama-facing components**: the Embedder and the LLM. The LLM is reused for both generation and judging; rerank and expand are *opt-in LLM roles* that share the same module but default to their deterministic mocks. Three source modules (`embedding.py`, `model.py`, `judgment.py`) implement the boundary; I-009/T-02 scan those three.*" Keep "one boundary / two components / three modules" as the canonical sentence and align §0, R-20, and §C-02/C-08 with it.

---

#### F-021 — `RunMetrics.retrieved` is top-`k` or top-`N`?

**Severity:** LOW **Location:** C-12 `RunMetrics` field list, R-11, I-006, T-11.

**Observation** `RunMetrics.retrieved` is commented `# chunk_ids ranked` but it is undefined whether this is the **post-rerank top-`k`** (the P/R@k `R_k`), the **pre-rerank top-`N`** (the rerank input), or the **raw candidate pool** (the hybrid union). `I-006` ("*`retrieved` exactly mirror the `Context`/ranking actually assembled for that case*") says "*ranking actually assembled*" — but two rankings exist at that point (pre- and post-rerank), and two *contexts* exist if `--expand on` (per-expansion contexts vs. the *union* context used to build `D'\`).

**Why it matters** An off-by-set choice flips which `chunk_id`s appear in `retrieved`, hence which P/R@k/NDCG the report claims, and whether `retrieved` is *the ranking used to build the context that was judged* (the defensible reading) or *the ranking as it left the retriever* (the *pre-rerank* reading).

**Potential consequence** `retrieved` can be top-N with `k=5` reported P/R@5 computed on those 20 chunks, inflating `Recall@5` vs. the `top-5` the context actually saw.

**Recommended resolution** Fix `retrieved = the top-`k` ranking actually consumed by the `ContextBuilder` (post-rerank, post-expand-union), pin it in C-12, and add to I-006 a cross-check `set(retrieved[:k]) == sorted(R_k_by_score)[:k]`.

---

#### F-022 — `Verdict.status = "SKIPPED"` only under `--judge off`?

**Severity:** LOW **Location:** C-11 `Verdict.status` ("`"JUDGED" | "ERROR" | "SKIPPED"`"), E-12, R-10.

**Observation** The `Verdict` enum carries `"SKIPPED"` but E-12 ("*`--judge off` … The `JUDGING` stage is skipped; generation fields are `None`*") and T-* never assert *which* of two behaviors happens: (a) a `Verdict(status="SKIPPED", …)` is *produced* and stored on the `RunMetrics` row, or (b) **no** `Verdict` object exists at all and `RunMetrics.correct/fidelity/…` are simply `None` with `status="SCORED"`/`"PARTIAL"` at the *row* level.

**Why it matters** `RunMetrics` has its **own** `status` field (`"SCORED"|"PARTIAL"|"ERROR"`), so "*row status*" and "*verdict status*" are **two different** concepts that need an explicit mapping; the `"SKIPPED"` enum value is either vestigial or load-bearing and the spec does not choose.

**Potential consequence** A verifier either expects a `Verdict(status="SKIPPED")` object or a `None` verdict field; E-12's "*generation fields are None*" is ambiguous as to which *fields* of *which object*.

**Recommended resolution** Pick one: recommend **no `Verdict` under `--judge off`** (row-level `status` carries the terminal state; `RunMetrics.correct/…` are just `None`), and **drop `"SKIPPED"` from the `Verdict` enum** — or, if the enum is kept, add a T that asserts the `Verdict(status="SKIPPED", answer=…) row-level status = "SCORED"` (or `"PARTIAL"`) mapping.

---

#### F-023 — `SCORCED` typo in E-03

**Severity:** LOW **Location:** E-03 ("*case is `SCORCED` with an (empty or wrong) answer*").

**Observation** The terminal state is spelled `SCORCED` in E-03; the canonical spelling `SCORED` is used everywhere else (e.g. the state table in §3.2, I-008, `RunMetrics.status` in §C-12). This is a one-character typo, but it is a *state-name* typo in a normative row.

**Why it matters** An error-string / `failure_stage` assertion would have to choose a spelling; the typo is the kind of thing that creeps into a test's `assert status == "SCORCED"` by *copy*, producing a false-failing test.

**Potential consequence** A typo-propagation defect in the T-suite; cosmetic.

**Recommended resolution** Replace `SCORCED` with `SCORED` in E-03.

---

#### F-024 — `SemanticChunker` in C-03 but deferred (Q-04 / OQ8); ship-scope unclear

**Severity:** LOW **Location:** §C-03 (`class SemanticChunker(Chunker):   # OPTIONAL/extension (Q-04)`), R-03, OQ (open question 8 in §11).

**Observation** §C-03 lists `SemanticChunker` as a first-class `Chunker` subclass next to `Fixed`/`Heading`/`Contextual`, but the class body is a comment "*OPTIONAL/extension*" and open question 8 (Q-04) defers it. An implementer who treats §C-03's class list as the *interface set to implement* may ship a partial `SemanticChunker` (embedding sentences, cutting at low cosine) that is *neither tested nor used*, and which (being probabilistic at index time) would **break the determinism invariant** by re-introducing Ollama into the index path.

**Why it matters** A shipped-buthalf-built class is worse than a deferred one: it can pass a naive source-scan while *not* honoring I-009/R-18, and it confuses the `--strategy` enum (the CLI list in §5.1 has `heading|fixed` *only*, matching the deferred status — so the mismatch is the other way: §C-03 names a class the CLI does not offer).

**Potential consequence** An implementer either (a) *omits* `SemanticChunker` (correct) or (b) *ships a broken extension* that violates I-009/R-18. The *wrong* outcome passes a coarse T-* and fails I-002.

**Recommended resolution** **Delete the `SemanticChunker` class from §C-03** and keep it only in a `## Extensions (out of scope for v0.1)` block, or **mark every v0.1-vs-extension class explicitly** in §C-03 with a `# V0.1: NO` comment on the class line so an implementer knows *not* to ship it; align the §5.1 `--strategy` enum with the §C-03 class set.

---

## 5. Requirements Review

`R-01`…`R-22` are, as a set, **almost entirely observable** — the dominant trait of this spec. Each names a *stage* (chunk/embed/retrieve/expand/rerank/contextualize/ground/generate/judge/metrics/attribute), a *condition* (tier, `alpha`, `--hybrid on`, `token_budget` smaller than a doc), an *input*, and a *result* that is asserted by a named `T-*` (§11 routes every `R-*` to a test). The few that are aspirational are flagged here.

**Observable and precise (strength).** `R-02`…`R-16`, `R-18`…`R-22` are observable obligations with measurable outputs (byte-identified mock vectors; a per-channel min-max; a top-`k` ranking; a structured `Answer`/`Verdict`; a `by_tier`/`by_capability` diff). `R-08`/`R-21` (anti-hallucination + injection) are *enforced by the harness, not the model* — an unusually strong, testable formulation. `R-13` (the seven tiers) and `R-14`/`R-15` (per-capability diff + per-stage attribution) make the chapter's thesis *assertable* rather than *asserted*.

**Precision gaps (MEDIUM).**
- **`R-12` / §21 generation-metric numerators** (F-006): "*reflected gold_facts*" and "*relevant citations*" are undefined for the real judge; only the mock's intersection semantics are concrete → the real-judgment metrics are not independently reproducible.
- **`R-13` `access_level`/permissions** (F-009): the capability is advertised but has no *principal* or comparison rule → it is half-open.
- **`R-11` `MRR`** (F-014): `MRR` is unnamed at `@k` while `P/R/NDCG` are → a boundary case diverges.
- **`R-04` hybrid** (F-002): candidate-pool + per-channel norm (missing channel, zero range) undefined → not byte-deterministic.
- **`R-18`/`R-20`** (F-016, F-020): the *seed surface* and the *one-vs-two-boundary* framing are loose.
- **`R-09`/`R-10`** (F-001): the `MockLLM` contract is the deepest gap — "*ground-truth-fit*" is undefined as to which data the double may read, which decides whether §21 is real or tautological.

**Companionship vs. aspiration.** A `SHOULD`/aspirational residue exists in §1's `+ metadata (*permissions*)` (F-009) and in the C-03 `SemanticChunker` (F-024). Both should be **resolved** (scoped out or fully specified) rather than left in the aspirational middle. `MAY`/"opt-in" usage (`LLMQueryExpander`/`LLMReranker`, the numpy accelerator, the GUI) is *correctly* marked and appropriately left to the implementer — these are genuine **implementation freedom**, not defects (per the skill's *freedom test*).

**Coverage.** All six §14–§19 failure modes have a tier **and** an edge (`chunking↔E-07`, `distractor↔E-08`, `conflict↔E-09`, `recency↔E-10`, `injection↔E-16`; `easy`/`multi` positive) — unusually complete for a lab spec. No requirement in **scope** is missing. The one *implicitly-introduced* capability is `access_level`/permissions (F-009) without the principal that would need it.

**Conflicts.** No requirement *contradicts* another. The tensions are *ambiguity-within-a-requirement* (`R-12` numerators, `R-04` pool, `R-09` mock input) and one *cross-reference* confusion at the edges (`R-22`↔`which_doc_decided`, F-004), not contradictory requirements. The `R-17`/`R-18` offline+determinism pair is *coherent* and is the spec's backbone, not a source of conflict.

**Verdict of §5.** Requirements are **observable, mostly precise, and comprehensive** for scope; the gaps are a small, enumerated set of *within-requirement* precision issues (F-001/002/006/009/014 + the `R-09` mock). None is a contradiction or an out-of-scope creep requiring a redesign.

---

## 6. Interface and Data-Contract Review

The contract surface (C-01…C-12) is **dense and mostly precise**. The data types (C-01) are *nearly implementation-grade*; the gaps are in *cross-field invariants* and a couple of **under-specified algorithms**, not in *missing fields*.

### 6.1 Data-contract completeness (strong)
- **C-01** (`ChunkMetadata`, `Document`, `Chunk`, `ScoredChunk`, `Chunk`) is strong: field types, null-ability, defaults, and the `chunk_id = "doc_id#i"` stable-id rule are all fixed; `ScoredChunk` carries the *component scores* (`semantic`, `lexical`, `rerank`) needed for the per-stage diff. Only weak points: `version: int|float|None` mixing two orderings + a `None` (F-004), and `access_level` without a principal (F-009).
- **C-11** (`Question`, `Answer`, `Verdict`, `RunMetrics`) is the schema-core and is strong on shape; the weak points are *intra-schema* (F-005 `supported_claims` not a field; F-012 post-rerank `score`/`rerank`/`rank` not reconciled; F-021 `retrieved` set; F-022 `SKIPPED` status; plus the metric-numerator definitions F-006). All are *field-semantics* fixes, not missing fields.

### 6.2 Interface completeness (strong, two gaps)
- **Embedder/VectorStore/cosine (C-02)** is precise *except* the **BM25 formula is by-reference, not inlined** (F-011) and the **hybrid pool / per-channel norm edges** are undefined (F-002, in C-04). `cosine` has the zero-vector guard (E-02); `search` returns `[]` never `None` (good).
- **Chunker (C-03)** precise incl. the `boundary_guard`/`split_risk` contract (a genuinely good, *observable* formulation of §14). Only `SemanticChunker`'s scope is muddled (F-024).
- **Reranker/QueryExpander/Context/Contextualize (C-05–C-07)** precise; the post-rerank *canonical key* is the one gap (F-012).
- **`LLM`/`Judge`/`Citer` (C-08–C-10)** strong; the one *material* gap is the **`MockLLM` gold-access contract** (F-001), which is the crux of §21. The Citer's grounding+injection scan is a genuinely strong, *enforced* contract (I-003, R-21).
- **Pipeline (C-12)** wires the state machine; `retrieved` semantics (F-021) and the index/query handoff (F-003) are the two open points.

### 6.3 Schema/gate precision (very strong)
- A single `jsonschema` gate (I-010/T-08) with `additionalProperties:false` and an `out-of-range confidence` + `missing required field` reject/retry → `ERROR`, never `COMPLETED`, is the ch1/ch2 *reliability gate* carried forward cleanly into RAG (R-09). The *dual* gate (answer **and** verdict) is correct and necessary.
- **Serialization.** No explicit **serialization contract** for `report.json` is given; F-017 is the one *serialization* gap (canonical ordering for R-18 byte-identity).
- **Compatibility.** Invariant I-009 (source-scan, three modules) is a *structural compatibility* guarantee: the real-path transport (httpx/Ollama) is *quarantined* so the deterministic core's API is stable across backend swaps — a strong, unusual guarantee.

### 6.4 Input/output ambiguity
- The one place an *input* is ambiguous is **hybrid `retrieve(q_vec, query, *, candidates)`** (F-002) — which `candidate`s get blended, and how a single-channel candidate is treated. Everything else (every dataclass field, every `--flag` default in K-03, every `T-*`) has a fixed default.
- **Empty/null behavior** is largely covered: `[]`-never-`None` (E-02), no-empty-denominator (I-007, every metric), empty `--tiers`→exit 0 (E-18), empty answer citations allowed (OQ2). The *open* empty-case is the **zero-range min-max** (F-002).

**Verdict of §6.** Interface and data-contract completeness is **strong-to-very-strong**; the two *material* gaps (F-001 mock-LLM input, F-002 hybrid pool) plus the cross-field invariants (F-004/005/012/017/021) are additive fixes. No missing field, no missing interface — only *under-pinned* semantics on existing fields and *under-specified* edges on existing algorithms.

---

## 7. State and Failure Review

The state model (§3.2 `CaseState`) and the failure model (§8 E-01…E-18) are the **cohesive heart** of this spec, and mostly *excellent*: a per-case single-threaded linear state machine with terminal `SCORED`/`PARTIAL`/`ERROR`, per-case fault isolation, a complete-retrieval-diagnosis guarantee that survives a later-stage fault (I-008), and **six §14–§19 failure modes realized as asserted tiers**. The defects are *local*, not structural.

### 7.1 State-machine completeness (strong, two notational gaps)
- **States + transitions:** `IDLE→RETRIEVING→EXPANDING→RERANKING→CONTEXTING→GENERATING→JUDGING→{SCORED|PARTIAL|ERROR}` with terminal `SCORED`/`PARTIAL`/`ERROR`; toggle-gating (`--hybrid off` ⇒ pure-dense passthrough; `--rerank off` ⇒ passthrough; `--judge off` ⇒ skip `JUDGING`) is cleanly modeled as *no-op stages that carry inputs unchanged*. **Initial, terminal, and failure states are all named.** This is well above the lab norm.
- **Gap 1 — the `ERROR` diagram annotation.** §3.2's ASCII diagram annotates the `ERROR` terminal as `failure_stage in {retrieval,expansion,reranking,context}`, but **E-11** says a *generation* fault (after retries) is `ERROR` with `failure_stage="generation"`, and `C-12`'s `failure_stage` enum includes `generation|judging`. So the diagram *under-states* the `ERROR`'s reachable `failure_stage` set (it omits `generation`; and `PARTIAL` is the *judge* fault, not `ERROR`). This is a **notational mismatch** between the diagram, the state table (`ERROR` = "*a stage before judging terminal-faulted*", which correctly includes `generation`), E-11, and the `C-12` enum — a verifier reading *only* the diagram would miss that a generation fault is an `ERROR`, not a `PARTIAL`.
- **Gap 2 — the `PARTIAL` trigger.** §3.2 says `PARTIAL` ⇒ "*retrieval + generation ok but **judge** failed (E-15)*" — but the *judge*-fault case is **E-11** ("*if generation succeeded but the judge failed the row is `PARTIAL`*"); `E-15` is a `top_n`/`top_k` **usage** exit. This is the **same root as F-007** (the `I-008/T-10/E-15` pointer family): E-15 is the *nearest neighbor* of the edges that actually carry `generation`/`judging` attribution, and the state table re-points `PARTIAL` to E-15 as well. Resolve both with the **E-11 re-pointing** in F-007.

### 7.2 Failure semantics (very strong)
- **Detection + resulting state + propagation + caller observation** are all specified per operation: parse/validation retry→`ERROR` (I-010), Ollama-unreachable→mock-degrade+banner (E-13), `relevant_chunks`-absent→load-error exit 3 (E-14/I-013), bad usage→exit 2 (E-15 with the exit-code *table* in §5.1). The **retry semantics** are precise: "*up to `max_retries` with an error-informed prompt, first failure reason recorded, then terminal*" — a ch2 E-03 analog carried cleanly.
- **Partial work / resume:** the *no-resume, no-retry-of-the-case* design (one question at a time; a failed stage *terminates that case*, siblings continue) is **explicit and coherent** — and it is the right call for a *static-per-run* corpus (R-13) with no cross-question state (Q-06). No partial-completion ambiguity.
- **Recovery / cancellation:** per-case isolation is the spec's *defining* failure property and is *architecturally* enforced (I-008: a later fault preserves the *complete retrieval diagnosis*); this is a genuinely unusual strength. GUI `Cancel` teardown is speced (I-014/E-17/T-16).

### 7.3 Intra-state consistency
- **Failure-stage enumeration.** `C-12` `failure_stage` ∈ `{retrieval,expansion,reranking,context,generation,judging}` and the state table / E-set agree on *which stage produces which terminal state* **once E-11 is re-pointed** (F-007). After that fix, the *whole* error-attribution story is internally consistent, which is what makes §21's "*where did it fail?" diagnostic trustworthy.
- **The one genuine failure-model tension — `E-04` vs. `E-14`/`I-013`** (F-015): the `|G|=0` *runtime* divide-guard is *unreachable* because absent ground-truth ids are a *load-time* error. This is *redundancy*, not *contradiction* — the guard is defensively-present-but-dead, and the resolution (label it defensive, or add a synthetic-corpus T) is additive.

### 7.4 What is *correctly* out of scope
- **Retries across cases / re-run-on-fault** are not specified — correct, since R-17/R-21 make a single static run the unit and per-case isolation the guarantee. **No state/memory subsystem** (Q-06) — correct and well-motivated. These are *freedom*, not gaps.

**Verdict of §7.** State-machines-and-failure is **near-implementation-grade**: complete state set, precise retry and propagation semantics, per-case isolation as an invariant, and six asserted failure tiers. The only *real* defect is the **E-15↔E-11/T-10 pointer family** (F-007, which also fixes the §3.2 diagram's `ERROR` annotation and the `PARTIAL` trigger) plus the **defensive-but-dead `E-04`** (F-015). After these, the state/failure model is fully consistent and mechanically verifiable.

*(Note: §3.2's `ERROR` diagram annotation and the `PARTIAL`→E-15 trigger are both resolved by the single F-007 re-point; they are reported here rather than as new findings because they share F-007's root cause and resolution.)*

---

## 8. Determinism and Algorithm Review

Determinism is the **thesis of the whole spec** ("*RAG … reproducible, offline*") and, accordingly, its **strongest algorithmic dimension**. It is *mostly* implementation-grade; the residual gaps are **edge behaviors of two algorithms** (hybrid min-max, token estimation) and a **serialization discipline** for the byte-identity claim — not *undefined behavior* in the core.

### 8.1 What is already deterministic and precise (excellent)
- **`MockEmbedder` (O-1)** — the linchpin: a **fixed** FNV-1a 32-bit hashed bag-of-words, **explicitly *not* Python's per-process `hash`**, L2-normalized to a unit vector, `D_mock=256` (K-03). This is a *genuinely brilliant* move: it makes dense+hybrid retrieval *observable and assertable offline* without a model, with a *meaningful* ranking (shared vocabulary → non-zero cosine). The tie-break (`chunk_id` asc, O-1b) and the no-positive-similarity `[]` guard (E-02) close the ordering. T-04 pins *both* the byte-identical property *and* the tie-break with a crafted equal-score corpus — a *strong* determinism test.
- **Metric math (§C-11, I-001/I-007)** — P/R@k, MRR, MAP, NDCG, faithfulness/completeness/citation_quality, each with a **closed-form equation** *and* a **worked example with asserted numbers** (T-05a/b, T-08a). The *no-division-by-zero* guards are individually named per metric (`precision=None` when `TP+FP=0`, `mrr=0.0` when nothing relevant, `ndcg=None` when `IDCG=0`, generation numerators `=0.0` when denominator `0`). This is *verification-grade* algorithm precision. The only algorithmic imprecision is the `MRR`-vs-`MRR@k` **at the rank-`>k` boundary** (F-014).
- **`cosine`** — guarded against a zero vector (E-02, denominator `or 1.0`); deterministic. **`est_tokens`** — a single formula (`ceil(len/4)`, I-005) used identically by builder and report, with the *unit* being the only open point (F-018, char-vs-byte).
- **Corpus/question generation** — `gen-corpus --seed 42` → byte-identical 100 docs + `questions.json` (T-01), with the §7 metadata and the seven tiers — a *fully deterministic* ground-truth factory. Strong.

### 8.2 Nondeterminism that is *correctly* bounded
- The spec never *pretends away* nondeterminism: the **real** path (`OllamaEmbedder`/`OllamaLLM`/`OllamaJudge`) is declared **best-effort** and the suite is scoped to the deterministic doubles only (R-17/I-011/T-14, K-01). `temperature=0.0, seed=42` are *defaulted* on the real path (C-09) and the **real path is excluded from `uv run pytest`** (K-05) — the right posture. Per skill §3.9, this is *precise handling* of the nondeterministic components, not a *prompt-as-guarantee* mistake.
- **Query expansion is honestly labeled** "*probabilistic in principle, deterministic by default*" (C-06) — exactly the right way to frame a default-mock, opt-in-LLM role (R-20).

### 8.3 Residual algorithmic gaps
- **Hybrid min-max, edges (F-002).** Candidate-pool formation, missing-channel treatment, and the **zero-range** (all-equal-score → `0/0`) case are undefined; I-002 cannot hold for `--hybrid on` until these are fixed. The single-candidate degenerate is documented (E-03) but the *multi-candidate equal-score* case is not — a *real* determinism hole on the headline capability.
- **Token estimator, two things (F-010, F-018).** (a) the *count that drives truncation* (running sum-of-`est_tokens` vs. `ceil` of concatenation) is undefined, and `ceil` is sub-additive so the two diverge **at the boundary** where `truncated` flips (I-004/T-06); (b) the *unit* of `len` (char vs. byte) is unstated (F-018), so non-ASCII breaks the I-006 *report=build* property.
- **`report.json` serialization (F-017).** Byte-identity (R-18/I-002) is *in-memory*; the *serialized artifact* has no canonical ordering (`by_tier`/`by_capability`/`RunMetrics` rows) — a serialization gap, not an algorithm gap per se.
- **`--seed` scope (F-016).** What the seed *actually governs* (only `gen-corpus`?) should be stated per-double so "*reproducible with a fixed seed*" is not *stronger-than-needed* (an implementer adds needless RNG) or *weaker* (a future mock silently non-deterministic).
- **BM25 by-reference (F-011).** The lexical channel's *algorithm* is cited, not inlined; the hybrid result depends on a formula defined in ch2. Not a determinism *defect* in ch3 per se, but it makes ch3 *non-self-contained* for a deterministic algorithm.

### 8.4 Numerical behavior / boundaries
- **Rounding.** NDCG's `log2` and the worked-example decimals (`1.88685`, `2.13093`, `0.88547`) are *pinned by assertion* (T-05a), so the rounding is *implicitly fixed by T-05a* rather than stated — acceptable since T-05a *is* the pin. For *new* metrics, add a rounding/format rule (F-017's serialization rule).
- **Empty/min/max.** Covered (E-02 empty retrieval, E-18 empty `--tiers`, I-007 empty denominators). The *uncovered* boundary is **zero-range min-max** (F-002).
- **Concurrency/determinism interaction.** v0.1 is *strictly sequential* (Q-05) — so determinism has no *race* to defeat; this is *correctly* chosen and removes a whole class of nondeterminism. A future `--concurrency` (Q-05) would need a determinism-preservation argument; note it, but it is out of scope.

**Verdict of §8.** Determinism and algorithm precision is the spec's **single strongest quality** (score 4 — the gap to 5 is *serialization + two algorithm edges*, not *undefined behavior*). The core (FNV-1a `MockEmbedder`, guarded metric math with asserted worked examples, per-case byte-identity, sequential design) is *verification-grade*; the P0/P1 fixes here are **F-002 (hybrid edges), F-017 (report serialization), and the F-010/F-018 estimator pins** — all additive and localized to the edges the rest of the spec already guards.
