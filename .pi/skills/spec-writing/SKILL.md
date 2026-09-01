---
name: spec-writing
description: Author a Level-3 (implementation-grade) SPEC.md for a labs/weekNN/chapterNN lab in this bootcamp. Use when asked to "write a spec", "create SPEC.md", or scaffold a new chapter lab. Encodes the exact 12-section template, normative-language discipline (MUST/MUST NOT/SHALL/SHOULD/MAY), the front-matter blockquote, the ID taxonomy (R-xx requirements, C-xx contracts, I-xx invariants, K-xx constraints, E-xx edges, T-xx tests, F-xx review findings), progressive Git commit conventions, and the optional spec-review → v0.2 uplift workflow.
---

# spec-writing

Write a `SPEC.md` for a `labs/weekNN/chapterNN/` lab exactly as the known-good prior art
(chapter1–chapter4) does — every part below is observable, executable, and
threaded to the `spec-review` pass.

## When to use

- "create SPEC.md for <chapter>"
- "write the spec for the <X> pipeline"
- "specify the `<interface>`"
- scaffold `labs/weekNN/chapterNN/SPEC.md`

Pair with `spec-review` when a review pass is needed; pair with `md2pdf-authoring` for the PDF
rendering of the resulting `*.md`.

## The 12-section template (copy exactly)

```markdown
# SPECIFICATION — <System Name in Title Caps> (Domain Keywords, <entry-point-CLI>+, uv)

> - **Status:** v0.1 — draft for implementation review…
> - **Language:** Python 3.12 | <component stack> | CLI/GUI labels
> - **Curriculum source:** `curriculum/weekN/chapterN.md` (§X … §Y) — a literal section list
> - **Scope of this document:** What the spec owns (the deterministic kernel, etc.)
> - **Normative language:** MUST/MUST NOT/SHALL/SHALL NOT = normative; SHOULD = strong; MAY = optional.
> - **Principle:** <one named invariant>, explained.

---

## 0. Intent and purpose

Why this subsystem exists; what the prior chapter(s) taught; where the deterministic vs
probabilistic boundary sits. Include the central thesis quote when there is one.

## 1. Actors and goals

| Actor | Goals |
| ----- | ----- |
| **Name** (`module.py`) | Behavior contract (one sentence), with a parenthetical single-principal
disclaimer where applicable |

## 2. Requirements (intent, high level)

| ID | Statement |
| -- | --------- |
| **R-01** | Observable behavior |

Requirements are **observable-behavior**-form, numbered R-01..R-NN. Map each to a curriculum §. At least one requirement MUST cover the universal verbosity contract in §5.3, including quiet defaults, CLI `INFO`/`DEBUG`, GUI `Off`/`INFO`/`DEBUG`, and stdout/stderr separation.

## 3. Behavior and state model

3.1 lifecycle scope (index-time / query-time, or eval-time, etc.); 3.2 the executable flow (text
ASCII box diagram `+`-`|`-`-`); 3.3 the durable artifacts pipeline.

## 4. Interfaces / contracts

### C-01 … ### C-NN

Each contract carries a fenced code block with a PINNED `@dataclass` or JSON-shape or
module/gated-list; note the in-scope inversions (`(F-OOO)`. Never paste the whole contract type
— only the behavioral pin.

## 5. Interface specification

### 5.1 CLI (`<cmd>`), primary surface
### 5.2 GUI, optional (`<cmd>-gui`)

### 5.3 Universal verbosity and diagnostics contract (mandatory)

Every project specification MUST define the same opt-in diagnostics behavior for both its CLI
and GUI, even when the GUI itself is optional:

- **Quiet by default:** omitted verbosity produces no diagnostic logs in normal user-facing output.
- **CLI syntax:** `--verbose` is accepted with no value and is equivalent to `--verbose INFO`;
  `--verbose INFO` and `--verbose DEBUG` MUST also be accepted. Invalid verbosity values are
  usage errors (exit `2`).
- **CLI INFO:** metadata only — command/mode, component/model, phase, timing, payload sizes,
  normalized-input summary, and status/error classification. INFO MUST NOT emit raw prompts,
  raw model responses, secrets, or full user payloads.
- **CLI DEBUG:** includes INFO metadata plus raw model prompts and raw model responses for
  model-backed operations. DEBUG raw content MUST be clearly labeled and MUST be written to
  stderr; normal result output on stdout MUST remain unchanged.
- **GUI control:** provide a verbosity selector with exactly `Off`, `INFO`, and `DEBUG`,
  defaulting to `Off`. INFO shows metadata; DEBUG additionally shows raw model prompts/responses
  in a dedicated diagnostics view/label. GUI diagnostics MUST NOT replace the primary result.
- The logging implementation MAY use any library, but the spec MUST name the selected logging
  mechanism and MUST define sink/stream, privacy, level, and formatting behavior.
- Allocate a requirement, contract, invariant, edge-case, and acceptance-test ID for this
  contract and include all of them in the traceability matrix.

CLI subcommand table columns: `Subcommand / Behavior / Exit` (usage errors exit `2`).

## 6. Invariants (must hold in every valid implementation)

The invariant set MUST include a verbosity invariant: omitted verbosity is quiet; INFO excludes
raw payloads; DEBUG is the only level that exposes raw model prompts/responses; and diagnostics
cannot alter primary results.

| ID | Invariant |
| -- | --------- |
| **I-001** | Zero-/negative-denominator fallbacks, byte-determinism, etc. |

## 7. Constraints (precise and measurable)

| ID | Constraint |
| -- | ---------- |
| **K-01** | All usage errors exit `2` (universal); others explicit |

## 8. Edge cases and failure semantics

| ID | Case | Semantics |
| -- | ---- | --------- |
| **E-01** | <input defect> | <deterministic outcome> |

## 9. Acceptance criteria, tests, and evals

The acceptance suite MUST include dedicated verbosity tests for:

- CLI bare `--verbose`, explicit `INFO`, explicit `DEBUG`, and invalid values;
- INFO metadata-only behavior and stdout preservation;
- DEBUG raw model-prompt/response visibility on stderr;
- GUI default `Off`, INFO metadata, and DEBUG raw-diagnostics behavior.

### 9.N {group}
| ID | Constraint |
| -- | ---------- |
| **T-NN** | description (ASCII text; KEEP `T-NN` unique — never collide ids) |

## 10. Dependencies and environment

`Python 3.12 + uv`; libraries; optional GUI/dev group; host prerequisites (ollama pull …, opt-in).

## 11. Traceability matrix (id → where realized)

| Spec id / requirement | Where realized (component / module) | Verified by (tests / evidence) |
| -- | ----- | -- |
Block `| ID | module (behavior) | test |` — one row per R/C/I/E/K/T id from above.
```

## The ID taxonomy (fixed alphabet)

| Prefix | Meaning | Example |
| ------ | ------- | ------- |
| **R-nn** | Requirement | R-14 |
| **C-nn** | Contract (interface/data) | C-08 |
| **I-nn** | Invariant | I-005 |
| **K-nn** | Constraint | K-03 |
| **E-nn** | Edge case / failure semantics | E-12 |
| **T-nn** | Test / acceptance | T-09 |
| **O-n** | Optionality (e.g. O-1 mock path, O-3 channel) | O-1 |
| **F-nnn** | Spec-review finding | F-012 (only used after a review exists) |

Papers MUST be uniquely numbered within their own family — collisions are the P1 finding's
breadline (`T-08a`/`T-08a` → rename `T-08a`/`T-08c`).

## Normative language discipline

- `MUST` / `MUST NOT` / `SHALL` / `SHALL NOT` — the normative verbs.
- `SHOULD` — a strong recommendation (a violation triggers a documented warning, not a gate).
- `MAY` — an optional behavior (a gate `MAY` exist under some flag).
- Do not emit `WILL`, `SHOULD BE ABLE TO`, `CAN` in normative rows.

## Front-matter blockquote (copy literally)

```markdown
> - **Status:** …
> - **Language:** …
> - **Curriculum source:** …
> - **Scope of this document:** …
> - **Normative language:** …
> - **Principle:** …
```

The Curriculum source contains a literal curriculum section list like `(§1 … §38)`, not a
bare filename.

## §0 Intent rules (state explicitly)

- A one-sentence **thesis quote** of the surrounding chapter (`"The evaluation suite is the
  bridge …"`), drawn word-for-word from `curriculum/weekN/chapterN.md` when available.
- Where the deterministic ↔ probabilistic boundary sits (which module owns which).
- A `**Relationship to chN**` paragraph when the lab extends a prior chapter.
- The **curriculum mapping** (rule → section list).

## Progressive-commit convention

Write the SPEC in this order of commits, each commit message prefixed `docs(chN):` and,
for the very first skeleton, `chN:` (as chapter4 did):

```bash
git add SPEC.md && git commit -m "chN: scaffold <lab-name> + instructions.txt; SPEC.md front matter + §0 + §1"
git add SPEC.md && git commit -m "docs(chN): SPEC.md §2 requirements R-01..R-NN"
git add SPEC.md && git commit -m "docs(chN): SPEC.md §3 state model + §4 contracts"
git add SPEC.md && git commit -m "docs(chN): SPEC.md §5 interfaces + §6 invariants + §7 constraints + §8 edges + §9 tests + §10 deps + §11 traceability"
```

After any accidental glyph/ASCII cleanup, `docs(chN):` commit again. The review cycle:
`review(chN):` per report-chapter made via the `spec-review` skill, and bump the
version header with the findings reintegrated as `fix(chN):`.

## Optional review-and-uplift workflow

If `spec-review` runs, follow the uplift campaign: apply P0 findings first, then P1, then
commit `docs(chN): bump SPEC.md v0.1->v0.2 (P0/P1 …; P2 hygiene deferred)`. Or only apply them
— deferring P2 findings is expressly acceptable.

## Security check before publishing

- **Every ID unique** within its letter family (no `T-08a` collision across sections).
- **Every curriculum § referenced** actually exists in `curriculum/weekN/chapterN.md`.
- **Normative verbs only** (`MUST/SHALL/SHOULD`; no `WILL`/`CAN` in normative rows).
- **Front-matter blockquote present, exactly one** (6 named fields, exact list above).
- **12-S template order** preserved (Intent→Actors→Requirements→Behavior→Contracts→
  Interfaces→Invariants→Constraints→Edges→Tests→Deps→Traceability).
- **Traceability rows** mention literal module/behavior/test ids.
- **Universal verbosity contract** is present in §5.3 and is traced to requirement, contract,
  invariant, edge-case, and acceptance-test IDs.
- CLI accepts `--verbose`, `--verbose INFO`, and `--verbose DEBUG`; omission is quiet.
- GUI defines `Off`, `INFO`, and `DEBUG`; default is `Off`.
- INFO excludes raw payloads; DEBUG is the only raw-payload level.
- CLI diagnostics go to stderr and do not alter stdout; GUI diagnostics use a dedicated view.
