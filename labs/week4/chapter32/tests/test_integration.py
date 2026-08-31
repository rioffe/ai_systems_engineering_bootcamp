# pyright: reportMissingImports=false
import json
import random
from pathlib import Path

from synthgen.dedup import Deduplicator
from synthgen.models import GroundTruth, Scenario
from synthgen.scenarios import ScenarioGenerator
from synthgen.spec import load_spec
from synthgen.templates import TemplateRealizer
from synthgen.truth import default_registry
from synthgen.validators import validate_candidate


def test_chapter31_adapter_calculates_truth_without_llm():
    spec = load_spec(Path("examples/mortgage.yaml"))
    scenario = ScenarioGenerator(spec).sample(random.Random(2), 0)
    truth = default_registry().get("mortgage").calculate(scenario)
    assert truth.source == "mortgage"
    assert truth.outcome in {"calculated", "payment_too_low"}


def test_template_candidate_passes_semantic_validation():
    spec = load_spec(Path("examples/mortgage.yaml"))
    scenario = ScenarioGenerator(spec).sample(random.Random(42), 0)
    truth = default_registry().get("mortgage").calculate(scenario)
    realization = TemplateRealizer().realize(scenario, truth, random.Random(1))
    result = validate_candidate(scenario, truth, realization, spec)
    assert result.valid, result.reasons


def test_deduplicator_reports_exact_and_near():
    dedup = Deduplicator(near=True)
    assert not dedup.check("What is the payment?", "a").duplicate
    assert dedup.check("What is the payment?", "b").kind == "exact"
    assert dedup.check("What is the payment", "c").kind == "near"


def test_generated_record_has_chapter31_shape(tmp_path):
    from synthgen.service import generate_dataset
    spec = load_spec(Path("examples/mortgage.yaml"))
    result = generate_dataset(spec, size=3, seed=9, output=tmp_path / "data.jsonl", report_path=tmp_path / "report.json", manifest_path=tmp_path / "manifest.json", spec_path=Path("examples/mortgage.yaml"))
    rows = [json.loads(line) for line in (tmp_path / "data.jsonl").read_text().splitlines()]
    assert len(rows) == 3
    assert {"case_id", "category", "question", "expected", "metadata"} <= rows[0].keys()
    assert result.report["complete"] is True
