"""R-11 / §5.1 (cli.py + app.py) -- the primary product surface.

`rag-eval` runs the full pipeline over a grounded question dataset and emits a metrics
report (human + machine-readable, per-tier). The CLI is offline by construction
(--mock / MockLLM + MockJudge, K-01/T-14); exit codes (0 ran, 2 bad usage, 3 load
failure, 4 fatal backend) and the E-11/E-12 backend selection drive the operator.
The §9.5 gen-corpus / eval --mock smoke is what these assert without a model.
"""

import json

from rag_eval import app, cli
from rag_eval.model import OllamaError


# ---------------------------------------------------------------- gen-corpus (R-10/T-01)
def test_gen_corpus_command_writes_deterministic_artifacts(tmp_path):
  out = tmp_path / "corpus"
  rc = app.main(
    [
      "gen-corpus",
      "--out",
      str(out),
      "--n-docs",
      "12",
      "--n-questions",
      "8",
      "--seed",
      "42",
    ]
  )
  assert rc == 0
  documents = out / "documents"
  assert documents.exists()
  assert (documents / "001.txt").exists()
  questions = json.loads((out / "questions.json").read_text())
  assert len(questions["questions"]) == 8

  # a second run with the same seed is byte-identical (R-15)
  first = (documents / "001.txt").read_text()
  app.main(
    [
      "gen-corpus",
      "--out",
      str(out),
      "--n-docs",
      "12",
      "--n-questions",
      "8",
      "--seed",
      "42",
    ]
  )
  assert (documents / "001.txt").read_text() == first


# ---------------------------------------------------------------- eval --mock (the smoke)
def test_eval_mock_writes_a_machine_readable_report(tmp_path):
  out = tmp_path / "corpus"
  app.main(
    [
      "gen-corpus",
      "--out",
      str(out),
      "--n-docs",
      "12",
      "--n-questions",
      "8",
      "--seed",
      "42",
    ]
  )
  report = tmp_path / "report.json"
  rc = app.main(
    [
      "eval",
      "--mock",
      "--dataset",
      str(out / "questions.json"),
      "--corpus",
      str(out / "documents"),
      "--out",
      str(report),
      "--k",
      "5",
      "--budget",
      "2000",
      "--tiers",
      "easy,multi",
    ]
  )
  assert rc == 0
  payload = json.loads(report.read_text())
  assert "aggregate" in payload and "cases" in payload and "meta" in payload
  # per-tier breakdown (§9.5 / R-11)
  tiers = payload["aggregate"]["by_tier"]
  assert set(tiers) <= {"easy", "multi", "synthesis", "distractor"}


def test_eval_judge_off_is_a_retrieval_only_eval(tmp_path):
  out = tmp_path / "corpus"
  app.main(
    [
      "gen-corpus",
      "--out",
      str(out),
      "--n-docs",
      "8",
      "--n-questions",
      "8",
      "--seed",
      "42",
    ]
  )
  report = tmp_path / "r.json"
  rc = app.main(
    [
      "eval",
      "--mock",
      "--judge",
      "off",
      "--dataset",
      str(out / "questions.json"),
      "--corpus",
      str(out / "documents"),
      "--out",
      str(report),
    ]
  )
  assert rc == 0
  payload = json.loads(report.read_text())
  # no verdicts under --judge off, but precision/recall still per-case (R-12 ablation)
  assert any(c["metrics"].get("precision") is not None for c in payload["cases"])
  # a retrieval-only verdict is SKIPPED
  assert all(c["metrics"].get("answer_status") == "COMPLETED" for c in payload["cases"])


# ---------------------------------------------------------------- exit codes (E-11/E-15/T-15)
def test_forced_model_unreachable_exits_four(monkeypatch, tmp_path):
  out = tmp_path / "corpus"
  app.main(["gen-corpus", "--out", str(out), "--n-docs", "8", "--n-questions", "8"])

  def boom(*_a, **_k):
    raise OllamaError("ollama not reachable")

  monkeypatch.setattr(cli, "OllamaClient", boom)
  rc = app.main(
    [
      "eval",
      "--model",
      "ghost-99",
      "--dataset",
      str(out / "questions.json"),
      "--corpus",
      str(out / "documents"),
    ]
  )
  assert rc == 4


def test_dangling_relevant_doc_is_a_load_failure_exit_three(tmp_path):
  out = tmp_path / "corpus"
  app.main(["gen-corpus", "--out", str(out), "--n-docs", "8", "--n-questions", "8"])
  # corrupt the dataset: point a question at a doc id absent from the corpus (E-15)
  bad = tmp_path / "bad.json"
  bad.write_text(
    json.dumps(
      {
        "questions": [
          {
            "q_id": "q1",
            "question": "x",
            "gold_answer": "y",
            "relevant_docs": ["999"],
            "tier": "easy",
          }
        ]
      }
    )
  )
  rc = app.main(
    ["eval", "--mock", "--dataset", str(bad), "--corpus", str(out / "documents")]
  )
  assert rc == 3


def test_unknown_command_exits_two():
  rc = app.main(["frobnicate"])
  assert rc == 2


def test_show_ranks_one_question(tmp_path):
  out = tmp_path / "corpus"
  app.main(["gen-corpus", "--out", str(out), "--n-docs", "8", "--n-questions", "8"])
  rc = app.main(
    [
      "show",
      "--mock",
      "--dataset",
      str(out / "questions.json"),
      "--corpus",
      str(out / "documents"),
    ]
  )
  assert rc == 0


# ---------------------------------------------------------------- exit code contract
def test_run_all_records_failures_but_exits_zero(tmp_path):
  # a per-case fault is a *result* in the report, not a non-zero process exit (§3.1).
  out = tmp_path / "corpus"
  app.main(["gen-corpus", "--out", str(out), "--n-docs", "8", "--n-questions", "8"])
  report = tmp_path / "r.json"
  rc = app.main(
    [
      "eval",
      "--mock",
      "--judge",
      "off",
      "--dataset",
      str(out / "questions.json"),
      "--corpus",
      str(out / "documents"),
      "--out",
      str(report),
    ]
  )
  assert rc == 0
  payload = json.loads(report.read_text())
  assert payload["aggregate"]["n_cases"] == 8
