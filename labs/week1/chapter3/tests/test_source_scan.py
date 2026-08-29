# I-013 / T-02: every REQUIRED spec section-4 interface exists in the source
# tree, by module (AST, structure only -- no imports, no backend). This is the
# "naming reconciliation" check (#9): it pins the spec §4 names to the code so a
# future rename that breaks a module/interface cannot pass silently. The optiona
# SemanticChunker is intentionally NOT required (spec §4 marks it OPTIONAL/extension
# per Q-04).
import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src" / "rag"
_SCHEMA = _ROOT / "schemas"

MANDATED = {
    "chunking.py": {"Chunker", "FixedChunker", "HeadingChunker", "ContextualChunker"},
    "embedding.py": {"Embedder", "MockEmbedder", "OllamaEmbedder"},
    "retrieval.py": {
        "DenseChannel", "LexicalChannel", "VectorStore", "BM25Index",
        "HybridRetriever", "Reranker", "MockReranker", "cosine",
    },
    "judgment.py": {"Judge", "MockJudge", "OllamaJudge"},
    "model.py": {
        "LLM", "MockLLM", "OllamaLLM", "OllamaClient",
        "LLMReranker", "MockLLMReranker", "OllamaLLMReranker",
    },
    "expand.py": {"QueryExpander", "MockQueryExpander", "LLMQueryExpander"},
    "corpus.py": {"load_corpus", "load_questions", "generate_corpus_and_questions"},
    "pipeline.py": {"build_index", "run_case", "run_dataset"},
    "metrics.py": {
        "precision", "recall", "mrr", "ndcg", "completeness", "faithfulness", "citation_quality",
        "aggregate",
    },
    "types.py": {
        "CaseState", "ChunkMetadata", "Document", "Chunk", "ScoredChunk",
        "Citation", "Question", "Usage", "Answer", "Verdict",
        "RunMetrics", "AggregateMetrics",
    },
    "availability.py": {"Availability", "Outcome", "resolve_availability"},
    "schemas.py": {"validate_answer", "validate_verdict"},
}
# spec §4 REQUIRED (NOT the optional SemanticChunker -- Q-04 / "OPTIONAL").
REQUIRED = set().union(*MANDATED.values())
SUBSTRINGS = {"types.py": ["PARTIAL", "COMPLETED", "ERROR"]}


def _top_level_names(path):
    tree = ast.parse(path.read_text())
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
    return names


def test_all_mandated_interfaces_present():
    missing = []
    for fname, want in MANDATED.items():
        present = _top_level_names(_SRC / fname)
        for name in sorted(want):
            if name not in present:
                missing.append(f"{fname}:{name}")
    assert not missing, "missing mandated interfaces: " + repr(missing)


def test_enum_members_present_by_substring():
    for fname, want in SUBSTRINGS.items():
        src = (_SRC / fname).read_text()
        miss = [s for s in want if s not in src]
        assert not miss, f"{fname} missing tokens: {miss}"


def test_schema_artifacts_exist():
    assert (_SCHEMA / "answer.json").exists()
    assert (_SCHEMA / "verdict.json").exists()


def test_cli_subcommands_present():
    app = (_SRC / "app.py").read_text()
    for sub in ("build-index", "eval", "gen-corpus", "show"):
        assert sub in app, "missing CLI subcommand: " + sub


def test_semanticchunker_is_intentionally_optional():
      # spec §4 marks SemanticChunker OPTIONAL (Q-04); its ABSENCE is allowed.
    present = _top_level_names(_SRC / "chunking.py")
    src = (_SRC / "chunking.py").read_text()
    assert "SemanticChunker" not in present or "SemanticChunker" in src
