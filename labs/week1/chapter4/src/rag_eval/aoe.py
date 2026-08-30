"""Chapter 3 adapter; this is the only module crossing the AoE boundary."""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_CH3_SRC = Path(__file__).resolve().parents[3] / "chapter3" / "src"
if str(_CH3_SRC) not in sys.path:
    sys.path.insert(0, str(_CH3_SRC))

from importlib import import_module


def _ch3_symbols() -> tuple[Any, Any, Any, Any, Any, Any]:
    corpus = import_module("rag.corpus")
    embedding = import_module("rag.embedding")
    judgment = import_module("rag.judgment")
    model = import_module("rag.model")
    pipeline = import_module("rag.pipeline")
    types = import_module("rag.types")
    return (corpus.load_corpus, embedding.MockEmbedder, judgment.MockJudge,
            model.MockLLM, pipeline, types.Question)


@dataclass
class AoEResult:
    question: str
    retrieved_chunks: list[str] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)
    raw_output: str = ""
    parsed_answer: dict[str, Any] | None = None
    verdict: dict[str, Any] = field(default_factory=dict)
    failure_stage: str | None = None
    usage_kind: str = "synthetic"
    usage_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float | None = None
    context: str = ""
    trace: dict[str, Any] = field(default_factory=dict)
    status: str = "SCORED"


def build_index(corpus_dir: str, index_flags: dict[str, Any]) -> tuple[Any, list[Any]]:
    load_corpus, mock_embedder, _mock_judge, _mock_llm, pipeline, _question = _ch3_symbols()
    docs = load_corpus(corpus_dir)
    return pipeline.build_index(docs, embedder=mock_embedder(), mock=True, **index_flags)


def run_case(case: Any, index: Any, query_flags: dict[str, Any]) -> AoEResult:
    _load_corpus, _mock_embedder, mock_judge, mock_llm, pipeline, question_type = _ch3_symbols()
    question = question_type(
        q_id=case.case_id, question=case.question, gold_answer=case.reference_answer,
        gold_facts=[], relevant_chunks=[], relevant_docs=[], tier=case.category,
    )
    start = time.perf_counter()
    metrics = pipeline.run_case(question, index, judge=mock_judge(), llm=mock_llm(), **query_flags)
    latency = round((time.perf_counter() - start) * 1000, 4)
    verdict = {key: value for key, value in vars(metrics).items() if key in {"correct", "supported", "complete", "status", "unsupported_claims"}}
    return AoEResult(
        question=case.question, retrieved_chunks=list(metrics.retrieved), raw_output="",
        verdict=verdict, failure_stage=metrics.failure_stage,
        usage_tokens=len(case.question.split()), latency_ms=latency, status=metrics.status,
        trace={"retrieve_ms": metrics.retrieve_ms, "generate_ms": metrics.generate_ms},
    )


def load_trace(path: str | Path) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid trace artifact: {exc}") from exc
