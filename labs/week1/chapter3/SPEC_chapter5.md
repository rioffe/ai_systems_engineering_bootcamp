## 4. Interfaces / contracts

### C-01 Corpus, documents, chunks, and §7 metadata

```python
@dataclass
class ChunkMetadata:             # §7 — part of every Chunk; a document's fields propagate to its chunks
    chunk_id: str               # "doc_id#i" — stable, e.g. "policy-17#0"; unique in the corpus
    doc_id: str
    title: str | None = None
    section: str | None = None            # e.g. "4.2 Business-Class Airfare"
    domain: str | None = None            # coarse category (travel / finance / …) -> distractor grouping + provenance
    author: str | None = None
    created_at: str | None = None        # ISO date YYYY-MM-DD
    updated_at: str | None = None        # ISO date
    version: int | float | None = None   # authority/version for §16 conflict + §17 recency
    access_level: str = "employee"

@dataclass
class Document:
    doc_id: str             # stable id, equals the `documents/` filename stem by default ("policy-17", "001")
    text: str               # full document text
    metadata: ChunkMetadata # §7 fields (title/section/…); section-aware split carries `section` per chunk

@dataclass
class Chunk:                 # the retrieval unit (§5)
    chunk_id: str
    text: str                 # the chunk's *own* text (shown to the LLM, cited)
    context: str | None       # §12 contextual prefix: "Document: {title} / Section: {section}\n{original}"
    embed_text: str           # what the Embedder *sees* (§12): context-prefixed when --contextual on; else == text
    meta: ChunkMetadata
    tokens: int               # est_tokens(embed_text)   (same formula as ch2 O-2, I-006)
    position: int             # 0-based order within its document

@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float             # the *combined* ranking score (hybrid when --hybrid, else the winning channel)
    semantic: float = 0.0    # raw dense (cosine) component score
    lexical: float = 0.0     # raw BM25 component score (when --hybrid)
    rerank: float | None = None   # reranker output when --rerank on (R-05)
    rank: int                # 1-based position in the *final* ranked list

def load_corpus(path: str) -> list[Document]:
      """Load `documents/NNN.txt` (or a single .jsonl) into Document[] with §7 metadata. doc_id =
    filename stem by default. Raises on a malformed entry / missing metadata a downstream tier needs
    (E-01/E-15). Pure, no LLM/network."""

def generate_corpus_and_questions(out_dir, n_docs=100, n_questions=25, seed=42,
                                  failure_mode_docs=None) -> None:
      """Deterministically write the ~100-doc, *sectioned* corpus under out_dir/documents/ (each doc
    carries §7 metadata) AND a grounded `questions.json` (§1 R-13) with the §14–§19 failure-mode tiers.
    A seeded generator authors the `question <-> relevant_chunks` + `gold_answer` mapping, and the
    `failure_mode_docs` (a few *hand-authored* conflicting/outdated/distractor/injection documents,
    E-08/E-09/E-13) are merged in so the conflict/recency/distractor/injection tiers are real.
    Seeded => byte-identical files (R-18)."""
```

**Tiers (§14–§19, R-13).** `Question.tier` is one of `easy`, `multi`, `chunking`, `distractor`, `conflict`, `recency`, `injection`. Meanings: *easy* = 1 relevant chunk;
*multi* = §19 multi-hop, ≥2 mutually-relevant chunks (A and B and C); *chunking* = §14 the rule's *governing condition* is split by a boundary (§5); *distractor* = §15
lexically-similar-but-irrelevant docs present; *conflict* = §16 two policies disagree, resolved by `version` / `updated_at`; *recency* = §17 several dated versions,
newest wins; *injection* = §18 an adversarial payload in *retrievable* evidence.

### C-02 Embedding + vector store + cosine (dense + the deterministic double)

- **Embedder (O-1, the dense seam).**

```python
class Embedder(ABC):
    @property
    def model_id(self) -> str: ...                 # e.g. "nomic-embed-text" or "mock"
    @property
    def dim(self) -> int: ...                      # fixed embedding dimension (real: model-native; mock: D_mock)

    @abstractmethod
    def embed(self, text: str) -> tuple[float, ...]: ...   # -> L2-normalized vector in R^dim

class OllamaEmbedder(Embedder):   # real: POST /api/embed {model: nomic-embed-text} -> embedding[0]
    # only module that names an /api/embed shape (I-002 / T-02 analog)
class MockEmbedder(Embedder):     # deterministic double -> hashed bag-of-words (O-1)
```

**O-1 — `MockEmbedder` (the deterministic dense vector, the crux of offline-testable RAG).**
For text, the mock vector is a *hashed bag of words* — fully deterministic and process-independent:

```python
tokens  = tokenize(text)                  # lowercase; split on [^\w']+; drop empty (same as ch2 BM25 tokenizer)
v       = [0.0] * D_mock                  # D_mock = 256 (default; K-03)
for t in tokens:
    idx = fnv1a32(t) mod D_mock           # FNV-1a 32-bit, NOT Python's built-in hash (which is per-process)
    v[idx] += 1.0                         # term frequency (collision ok — it is a probe, not a map)
norm  = sqrt(sum(x*x for x in v)) or 1.0
return tuple(x / norm for x in v)         # L2-normalized  => cosine == dot on unit vectors
```

`fnv1a32` is the documented, seed-independent hash (offset basis `0x811c9dc5`, prime `0x01000193`).
Because embeddings are hashed bag-of-words, **shared vocabulary ⇒ non-zero cosine**; the mock gives a
*meaningful* dense ranking (not garbage), which is what lets T-03/T-04 assert dense+hybrid **behavior**
without any embed model. The real `OllamaEmbedder` is swapped in for the opt-in smoke (§9.5);
the interface (`embed(text) -> unit vector`) is identical, so nothing downstream changes. (The
tokenizer is O-1a; the tie-break for equal cosine is O-1b.)

- **VectorStore + cosine + the top-k contract.**

```python
class VectorStore:
    def __init__(self, dim: int) -> None: ...                       # in-memory (no external DB; R-02)
    def insert(self, scored_or_chunk, vector: tuple[float, ...]) -> None: ...  # index time
    def search(self, q_vec: tuple[float, ...], k: int) -> list[ScoredChunk]: ...  # query time

def cosine(a, b) -> float:    # O-2 math, I-002
    return dot(a,b) / ((norm(a)*norm(b)) or 1.0)    # 0.0 on a zero vector (guard, E-02)
```

`search` returns up to `k` chunks by **descending cosine**; ties broken by `chunk_id` ascending
(O-1b) so the ranking is byte-reproducible (R-18). An empty store or a query with no positive
similarity returns `[]` (E-02), never `None`.

- **Lexical (BM25) channel for hybrid (ch2 C-02 formula, reused).**

```python
class BM25Index:
    def search(self, query: str, k: int) -> list[ScoredChunk]: ...   # O-1 ch2 exact formulas
```

`score(q,d)` and `idf(t)` are the ch2 O-1 formulas with the same tokenizer (O-1a); k1=1.5, b=0.75
(defaults, K-03). This gives hybrid retrieval its *lexical* signal (ch3 §8): exact identifiers,
names, numbers, error codes, unusual terminology where dense is weak.

### C-03 Chunking (information architecture — §5/§6/§14)

```python
class Chunker(ABC):
    @abstractmethod
    def chunk(self, doc: Document, *, overlap: int = 0) -> list[Chunk]: ...

class FixedChunker(Chunker):    # size + overlap characters/words (the naïve baseline, §5)
class HeadingChunker(Chunker):  # split on heading markers (## / Article / Section), never across a heading (§6)
class ContextualChunker(Chunker):  # wraps another strategy; sets Chunk.context (§12) and embed_text prefix
class SemanticChunker(Chunker):  # OPTIONAL/extension (Q-04): embed sentences, cut at low-cosine gaps

def boundary_guard(strategy, doc, overlap) -> list[Chunk]:
    """§14/R-03: when the configured size/overlap would split a sentence or a "rule + its governing
  condition" across a boundary, PREFER the overlap-safe / sentence-boundary unit and set a per-chunk
  `split_risk=True` flag (observable, E-05). The guard never silently orphans a condition."""
```

```text
Default strategy (K-03):
   --strategy heading    # §6: heading-aware is the DEFAULT (§6 "follow semantic structure")
   --strategy fixed      # the §5 naïve baseline, for the chunk-boundary experiment (§14)
   --contextual on       # §12 wraps the chosen strategy and sets embed_text = context + text
   --overlap 200         # overlapping window so a condition split at the boundary is recoverable
   --chunk-size 800      # characters (estimate); heading-aware ignores absolute size, cuts on structure
```

**Boundary semantics (I-013, §14).** `FixedChunker.size` cuts characters but `boundary_guard` pulls a
cut up to the nearest sentence end within `overlap`; if *no* sentence boundary is within `overlap` of
the hard position, it keeps the larger unit and flags `split_risk=True` rather than severing the
condition. The `chunking` tier (§14) feeds a document whose single rule + condition is *designed* to
lie across a boundary at the naïve `size`, then T-21 shows `--contextual`/`--overlap` recovers both
halves while `--strategy fixed --overlap 0` *fails* the answer — the *measurable* demonstration of
§14/§6.

### C-04 Hybrid retrieval (§8 — combine complementary channels)

```python
@dataclass
class HybridConfig:
    alpha: float = 0.5           # weight on the semantic channel; (1-alpha) on the lexical channel (R-04)
    s_sem_norm: str = "minmax"   # per-query normalization of the dense channel into [0,1]
    s_lex_norm: str = "minmax"   # per-query normalization of the BM25 channel into [0,1]
    combine: str = "linear"      # linear blend (default); "rrf" is a documented alt (Q-01)

class HybridRetriever:
    def __init__(self, store: VectorStore, bm25: BM25Index, *, cfg: HybridConfig | None = None):
    def retrieve(self, q_vec: tuple[float, ...], query: str, *, candidates: int) -> list[ScoredChunk]:
       """Score each candidate on BOTH channels, NORMALIZE each channel per-query to [0,1]
   (O-3), then blend per R-04: score = alpha*s_sem + (1-alpha)*s_lex. Ties broken by chunk_id
  asc (O-1b). Returns the top `candidates` by blended score. `alpha=1` = pure dense; `alpha=0`
   = pure lexical. Deterministic on the mock embedder (R-18/I-002)."""
```

**O-3 — per-channel normalization.** Each channel's raw scores (`cosine` in `-1..1`; BM25 in `0..`
unbounded) are min-max-scaled to `[0,1]` *over the query's own candidate set* before blending, so
the alpha weight is commensurable, not a ratio against incomparable scales. A query with a single
candidate normalizes to `score=1.0` for it (degenerate, documented, E-03). This is the exact thing
that makes “+hybrid” a *measurable* change rather than a rescale artifact (§22/§21).

### C-05 Reranking (§9 — fast recall, then precise rerank)

```python
class Reranker(ABC):
      @abstractmethod
    def rerank(self, query: str, candidates: list[ScoredChunk], *, top_k: int) -> list[ScoredChunk]:
       """Given the fast top-N (`len(candidates) >= top_k`), return a precise top-k re-rank
   (descending `ScoredChunk.rerank`). `top_k <= len(candidates)` ALWAYS (E-16)."""

class MockReranker(Reranker):     # deterministic default
   """`rerank(q)` = 0.6*coverage(q, chunk.text) + 0.4*normalized_cosine, where
   coverage = (query terms present in chunk) / (unique query terms). Reproducible (R-18/I-002)."""
class LLMReranker(Reranker):      # opt-in: ask qwen3.8:27b-mlx to score each candidate 0..1 (real)
```

The reranker is the *precision* half of the §9 “retrieve broadly, then apply an expensive
model” plan: the retriever (dense/hybrid) optimizes **recall** over top-N; the reranker re-orders
for **precision** over top-k. With `--rerank off` the reranker is a passthrough and the final
ranking equals the retriever output (the baseline for the “+reranking” diff in §22).

### C-06 Query expansion / multi-query retrieval (§10/§11)

```python
class QueryExpander(ABC):
      @abstractmethod
    def expand(self, query: str, *, n: int) -> list[str]: ...    # q -> {q1..qn}; the ORIGINAL is q1

class MockQueryExpander(QueryExpander):    # deterministic default
   """Templates + a fixed synonym map (business class -> premium cabin, airfare, ...), seeded.
  n expansions incl. the original. No LLM; byte-identical under a fixed seed (R-18)."""
class LLMQueryExpander(QueryExpander):      # opt-in: LLM generates `n` phrasings

def multi_query(expander, retriever, query, *, n: int, candidates: int, *, merge: str = "union") -> list[ScoredChunk]:
      """For each expansion q_i: r_i = retriever.retrieve(q_i, candidates). Merge:
   `union` = dedupe by chunk_id, keep the MAX blended score seen (ties chunk_id asc). Default merge
  (documented, R-06). `n=1` collapses to the single-query path. Expansion raises recall but adds
  noise (§10/§11) — the `distractor` tier (§15) is where that trade is *felt* (measured, E-09)."""
```

Expansion is a *probabilistic* stage in principle (an LLM-generated `q_i` can miss concepts, invent
assumptions, or add redundancy, §11), but its **default** is the deterministic `MockQueryExpander`
(R-20); the `--expand` / `--llm-expand` flags govern which. The `multi`/`synthesis` tier (§19
multi-hop) is the regime where expansion pays off (a multi-concept question whose answer spans
`A and B and C`).

### C-07 Contextual retrieval (§12 — enrich chunks *before* embedding)

```python
def contextualize(doc: Document, chunk: Chunk) -> Chunk:
      """Set chunk.context = f'Document: {title}\nSection: {section}\n\n' + chunk.text ;
   chunk.embed_text = chunk.context + chunk.text. Applied at INDEX TIME (§3.1), so the embedding
  carries document context even though a bare `The limit is $5,000.` would be meaningless alone (R-07).
  The ORIGINAL chunk.text (not the prefix) is what is handed to the LLM and what is cited."""
```

The query is embedded in its **plain** form (§3.3); only *indexed chunks* are contextualized.
This preserves meaning for fragmented documents (§12). With `--contextual off`, `embed_text ==`
`chunk.text` (equivalent to `ContextualChunker` being a no-op).

### C-08 Citation generation + grounding gate (§13/§21, R-08/R-21)

```python
@dataclass
class Citation:
    claim: str                 # a discrete factual claim drawn from the answer (§13)
    source: str                # doc_id
    chunk_id: str              # the chunk that evidences the claim
    section: str | None = None

class Citer:
   """Given the assembled Context (provenance) + the LLM Answer,:
   1 GROUNDING GATE (I-003): drop any cited chunk_id/source NOT in Context.provenance; if any dropped,
    set Citer.grounding_violation=True, force the row's `supported` to False and count the dropped
    ids as unsupported (§13 anti-hallucination; enforced in the harness, NOT trusted to the model, R-08).
   2 CLAIM EXTRACTION: split Answer.text into claims (deterministic sentence/semicolon split; the
    MockJudge enumerates the same set so the math is reproducible — I-014 / T-08a).
   3 INJECTION SCAN (E-13/R-21): keyword/regex over *retrieved* evidence for a payload pattern
    ("ignore previous instructions", "reveal", ...). On a hit: set row `injection_warning=True`
    and record the offending chunk_id; the verdict treats the retrieved payload as DATA (it may never
    change the system's behaviour or the system prompt — §18 trust boundary."""
```

The `MockJudge` and the real Judge both operate on the **Citer's** claim list, so `supported` /
`unsupported_claims` / faithfulness are *independently reproducible from evidence* (skill §16: be
suspicious of a metric the evaluated component supplies).

### C-09 LLM interface (the generation role-seam — R-09/R-17/R-20)

```python
class LLM(ABC):
    @property
    def model_id(self) -> str: ...             # e.g. "qwen3.8:27b-mlx" or "mock"

    @abstractmethod
    def generate(self, *, system: str, context: str, question: str, schema: dict,
                 max_tokens: int = 512, temperature: float = 0.0, seed: int | None = 42,
                 max_retries: int = 2, on_failure: str | None = None) -> Answer:
         """Produce a STRUCTURED, CITED answer by prompting the model to emit the answer schema
   object (below). Validate like ch1/ch2 C-05: strip the optional `json` fence -> json.loads -> jsonschema
    -> accept/reject-with-retry (I-010). On exhaustion: Answer(status="ERROR"); first failure reason
  recorded. `citations[].chunk_id` MUST reference ids that appear in `context` (I-003 is enforced by the
  Citer in the harness, NOT trusted to the model — R-08)."""

class OllamaLLM(LLM):      # the real backend; POST /api/chat -> qwen3.8:27b-mlx (ch2 C-05 shape)
class MockLLM(LLM):        # deterministic offline double: derives a schema-valid, GROUND-TRUTH-FIT Answer
                           # from question + assembled context so the T-suite asserts the CITER/JUDGE MATH
                           # without a model.
```

`OllamaLLM` is the single module that names an Ollama URL/model shape in the *generation* path
(reused from ch2's `OllamaClient`: httpx, `/api/chat`, NDJSON, `prompt_eval_count`/`eval_count` ->
`Usage`); a source scan T-02 (R-20) confirms it lives only in `model.py`/`judgment.py`/`embedding.py`
and that `retrieval/context/metrics/corpus/expand/rerank/citation` name neither `Ollama` nor `httpx`.

### C-10 Judge interface (LLM-as-judge — R-10/R-12)

```python
class Judge(ABC):
    @property
    def model_id(self) -> str: ...             # may be "" (deterministic) or a model id

    @abstractmethod
    def judge(self, *, question: Question, context: Context, answer: Answer,
              claims: list[str], gold_facts: list[str],
              max_retries: int = 2, on_failure: str | None = None) -> Verdict: ...

class OllamaJudge(Judge):    # real: asks qwen3.8:27b-mlx to emit the verdict schema (R-10)
class MockJudge(Judge):      # deterministic: verdicts derived from ground truth (intersection of
                             # question.relevant_chunks, Citer claims, gold_facts) so the suite asserts
                             # the METRIC MATH without a model.
```

The judge operates on the **Citer's** `claims` list (§13) and on `gold_facts` (the answer's
*expected* facts, from the question record) so that *completeness* and *citation quality* are
computable from evidence, not asserted by the model being judged (skill §16 warning on
self-supplied metrics).

### C-11 Record types (§15 ch2 analog) + metrics math (§20/§21, R-11/R-12)

```python
@dataclass
class Question:
    q_id: str
    question: str
    gold_answer: str
    gold_facts: list[str]             # discrete expected facts -> completeness denom (§21)
    relevant_chunks: list[str]        # R-13 ground truth (TP/recall universe)
    relevant_docs: list[str]          # doc_ids (coarser; for report / citation check)
    tier: str                         # one of the 7 tiers (§C-01 Tiers block)

# Answer schema (JSON-Schema, additionalProperties:false; produced by LLM, validated like ch1 C-05):
#   { "answer": str(minLength1), "confidence": number[0,1],
#      "citations": array<{claim:str, source:str, chunk_id:str, section:str?}>, "status": str }
@dataclass
class Answer:
    q_id: str
    text: str
    confidence: float               # [0,1]
    citations: list[Citation]       # C-08; grounding-checked by the Citer (I-003)
    usage: "Usage"                 # ch1 C-01 usage (prompt/completion/total tokens)
    status: str                    # "COMPLETED" | "ERROR"

# Verdict schema (JSON-Schema; produced by Judge, validated):
#   { "correct": bool, "supported": bool, "complete": bool,
#      "unsupported_claims": array[str], "total_factual_claims": integer(min0),
#      "faithfulness": number[0,1], "completeness": number[0,1],
#      "citation_quality": number[0,1], "injection_warning": bool, "grounding_violation": bool,
#      "which_doc_decided": str|null, "rationale": str, "status": str }
@dataclass
class Verdict:
    q_id: str
    correct: bool
    supported: bool                 # every claim traceable to retrieved context
    complete: bool                  # all gold_facts reflected
    unsupported_claims: list[str]
    total_factual_claims: int       # >= 0; faithfulness denominator
    faithfulness: float
    completeness: float
    citation_quality: float
    injection_warning: bool         # R-21 / §18
    grounding_violation: bool       # I-003 / R-08 (a foreign citation was dropped)
    which_doc_decided: str | None   # R-22: which metadata field resolved conflict/recency
    rationale: str
    status: str                     # "JUDGED" | "ERROR" | "SKIPPED"
```

**Metrics — retrieval (§20, R-11).** For a query with ground truth `G` and retrieved top-k `R_k`:

$$
\text{Precision}@k = \frac{|G\cap R_k|}{|R_k|}\quad
\text{Recall}@k = \frac{|G\cap R_k|}{|G|}\quad
\text{MRR} = \frac{1}{\operatorname{rank}(\text{first }g\in R_k)} \;(0 \text{ if none})
$$

$$
\text{AP}_q = \frac{1}{|G|}\sum_{i:R_i\in G} \text{Precision}@i \qquad
\text{MAP} = \frac{1}{|Q|}\sum_q \text{AP}_q
$$

$$
\text{DCG}@k = \sum_{i=1}^{k}\frac{\text{rel}(R_i)}{\log_2(i+1)}\quad
\text{IDCG}@k = \text{DCG of the ideal order}\quad
\text{NDCG}@k = \frac{\text{DCG}@k}{\text{IDCG}@k}
$$

**Metrics — generation (§21, R-12).** Over judged rows:

$$
\text{faithfulness} = \frac{\text{supported claims}}{\text{total\_factual\_claims}}\quad
\text{completeness} = \frac{\text{reflected gold\_facts}}{|gold\_facts|}\quad
\text{citation\_quality} = \frac{\text{relevant citations}}{\text{total citations}}
$$

**No-division-by-zero (I-007 analog, the metric guards):** `Precision@k=None` when `|R_k|=0`;
`Recall@k=None` when `|G|=0`; `MRR=0.0` when no relevant doc is retrieved; `NDCG@k=None` when
`IDCG@k=0`; `faithfulness=0.0` / `completeness=0.0` / `citation_quality=0.0` when the respective
denominator is 0. A row with no retrieval output contributes nothing to a mean (the mean is over
non-None values only).

**§20/§21 worked examples (pin the T-suite by assertion — I-001):**

- **Retrieval (binary relevance).** `G={c1,c3,c5}`, `R_5=[c1,c8,c3,c9,c5]`, `k=5`:
     `TP=3`, `precision@5=3/5=0.60`, `recall@5=3/3=1.0`,
    `MRR=1/rank(c1)=1.0`,
    `DCG@5 = 1/log2(2) + 1/log2(4) + 1/log2(6) = 1.0 + 0.5 + 0.38685 = 1.88685`,
    `IDCG@5 = 1/log2(2) + 1/log2(3) + 1/log2(4) = 1.0 + 0.63093 + 0.5 = 2.13093`,
    `NDCG@5 = 1.88685 / 2.13093 = 0.88547` (about 0.885). (T-05a)
- **Multi-query AP/MAP.** `q1: R=[r1(y),r2,r3(y),r4,r5], G={r1,r3}` -> `AP=(P@1+P@3)/2=(1+2/3)/2=0.83333`,
    `MRR=1.0`; `q2: R=[s1,s2(y)], G={s2}` -> `AP=0.5`, `MRR=0.5`.
   Hence `MRR=mean(1.0,0.5)=0.75`, `MAP=mean(0.83333,0.5)=0.66667`. (T-05b)
- **Generation guards.** A verdict with `total_factual_claims=4, unsupported=1` ->
    `faithfulness=3/4=0.75`; `|gold_facts|=4, reflected=3` -> `completeness=0.75`;
    `citations=5, relevant=4` -> `citation_quality=0.8`; a verdict with `total_factual_claims=0` ->
    `faithfulness=0.0` (I-007). (T-08a)

**Aggregate (I-012 analog).** `by_tier` carries one sub-aggregate per populated tier; `by_capability`
carries one per toggled stage in §22 (metadata/hybrid/rerank/expand/contextual/citations) so a
*+hybrid* diff is a row-to-row comparison of aggregate P/R/MAP/NDCG (R-14 per-capability diff). Means
are over non-None rows only.

### C-12 Pipeline (run_case / run_dataset / build_index — R-14/R-15)

```python
def build_index(docs: list[Document], *, strategy: str, contextual: bool,
                embedder: Embedder, overlap: int, chunk_size: int) -> tuple[VectorStore, BM25Index]:
     """Index-time (§3.1): for each doc -> Chunker(chunk) -> contextualize -> embed -> insert, plus
  build BM25Index. Deterministic on MockEmbedder (I-002)."""

def run_case(question: Question, index, *, hybrid: bool, alpha: float, rerank: bool,
             top_n: int, top_k: int, expand: bool, n_expand: int, contextual: bool,
             judge: Judge | None, llm: LLM, cfg) -> RunMetrics:
     """Query-time (§3.2) state machine: RETRIEVE -> (EXPAND) -> (RERANK) -> CONTEXT -> CITE ->
  GENERATE -> (JUDGE) -> metrics. Any stage fault -> terminal ERROR/PARTIAL with failure_stage
   (R-15) but a COMPLETE retrieval diagnosis if RETRIEVING cleared (§3.2 transition rules)."""

@dataclass
class RunMetrics:
    q_id: str
    tier: str
     # retrieval (populated iff cleared RETRIEVING; R-11)
    retrieved: list[str]           # chunk_ids ranked
    expected: list[str]            # == question.relevant_chunks
    precision: float | None
    recall: float | None
    mrr: float | None
     # ap / ndcg are dataset-level (aggregate()); per-row AP/ndcg kept for the diff
    ap: float | None
    ndcg: float | None
    capability_flags: dict[str, bool]    # which §22 stages were on for THIS row (by_capability diff)
    context_tokens: int
    truncated: bool
     # generation + judge (populated if that stage ran; R-12)
    answer_status: str
    correct: bool | None
    supported: bool | None
    complete: bool | None
    faithfulness: float | None
    completeness: float | None
    citation_quality: float | None
    unsupported_claims: list[str]
    injection_warning: bool
    grounding_violation: bool
    which_doc_decided: str | None
     # diagnostics / timing
    failure_stage: str | None       # None | retrieval|expansion|reranking|context|generation|judging (R-15)
    retrieve_ms: float
    rerank_ms: float
    generate_ms: float
    total_latency_ms: float
    status: str                     # "SCORED" | "PARTIAL" | "ERROR"   (§3.2)
```

---

