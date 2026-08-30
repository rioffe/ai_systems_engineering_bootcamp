# pyright: reportMissingImports=false

from pathlib import Path

from rag_eval.aoe import build_index, run_case
from rag_eval.dataset import load_dataset

ROOT = Path(__file__).parents[1]


def test_adapter_runs_chapter3_mock_path_without_gold_in_prompt():
    dataset = load_dataset(ROOT / "tests/fixtures/golden-5.json", corpus_ids={"doc#0", "other#0"})
    index = build_index(str(ROOT / "documents"), {"chunk_size": 50, "overlap": 0})
    result = run_case(dataset.cases[0], index, {"top_k": 5, "top_n": 10})
    assert result.usage_kind == "synthetic"
    assert result.question == dataset.cases[0].question
    assert result.retrieved_chunks
    assert "reference_answer" not in result.trace
