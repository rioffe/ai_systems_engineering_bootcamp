from pathlib import Path


def test_core_files_do_not_import_aoe_or_network():
    root = Path(__file__).parents[1] / "src" / "rag_eval"
    forbidden = ("import httpx", "import ollama", "from rag", "import rag")
    for name in (
        "dataset.py",
        "schema.py",
        "evaluator.py",
        "metrics.py",
        "compare.py",
        "gates.py",
        "failure.py",
        "report.py",
    ):
        text = (root / name).read_text()
        assert not any(token in text for token in forbidden), name
