# I-013 / T-02: the section-1 interfaces exist in the source tree. Top-level
# names are parsed via AST (structure only, no imports); enum members / string
# tokens are checked by substring. Deterministic + offline-safe.
import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src" / "rag"
_SCHEMA = _ROOT / "schemas"

MANDATED = {
    "retrieval.py": {
        "DenseChannel", "LexicalChannel", "VectorStore", "BM25Index",
        "HybridRetriever", "Reranker", "MockReranker", "cosine",
        },
    "pipeline.py": {"build_index", "run_case", "run_dataset"},
    "model.py": {
        "LLM", "MockLLM", "OllamaLLM", "OllamaClient",
        "LLMReranker", "MockLLMReranker", "OllamaLLMReranker",
        },
    "judgment.py": {"Judge", "MockJudge", "OllamaJudge"},
    "metrics.py": {
        "aggregate", "precision", "recall", "mrr", "ndcg",
        "completeness", "faithfulness", "citation_quality",
        },
    "types.py": {
        "RunMetrics", "CaseState", "Answer", "Verdict",
        "Document", "Question", "ScoredChunk", "Usage",
        },
    "availability.py": {"Availability", "Outcome", "resolve_availability"},
    "schemas.py": {"validate_answer", "validate_verdict"},
}
SUBSTRINGS = {
    "types.py": ["PARTIAL", "COMPLETED", "ERROR"],
}


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
        path = _SRC / fname
        present = _top_level_names(path)
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
