"""Judge role-seam (C-10): MockJudge + OllamaJudge.

MockJudge: deterministic offline double. Derives verdicts from
   - gold_facts (the question's expected facts -- F-001)
    - claims (from the Citer's claim extraction)
    - question.relevant_chunks (citation check universe)
    - context (injection scan)
No LLM, no network, no RNG.

OllamaJudge: real path via OllamaClient.chat; opt-in, not in the test suite.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod

from loguru import logger

from rag.model import OllamaClient
from rag.types import Answer, Question, Verdict

# -- helpers ----------------------------------------------------------------


_INJECTION_PATTERNS = [
    re.compile(r"ignore previous instructions", re.IGNORECASE),
    re.compile(r"ignore all previous", re.IGNORECASE),
    re.compile(r"disregard previous", re.IGNORECASE),
    re.compile(r"reveal your system", re.IGNORECASE),
    re.compile(r"reveal the system prompt", re.IGNORECASE),
    re.compile(r"override the system", re.IGNORECASE),
    re.compile(r"you are now", re.IGNORECASE),
    re.compile(r"DANGER", re.IGNORECASE),
]


def _is_injection(claims: list[str]) -> bool:
    for claim in claims:
        for pat in _INJECTION_PATTERNS:
            if pat.search(claim):
                return True
    return False


def _token_set(s: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9$]+", s.lower()))


def _completeness(
    gold_facts: list[str],
    claims: list[str],
) -> float:
    if not gold_facts:
        return 1.0
    claim_tokens: set[str] = set()
    for c in claims:
        claim_tokens |= _token_set(c)
        claim_tokens.add(c.strip().lower())
    reflected = 0
    for gf in gold_facts:
        gf_tokens = _token_set(gf)
        if any(tok in claim_tokens for tok in gf_tokens if len(tok) > 2):
            reflected += 1
    return reflected / len(gold_facts)


def _faithfulness(
    claims: list[str],
    gold_facts: list[str],
) -> tuple[float, list[str]]:
    total = len(claims)
    if total == 0:
        return (1.0, [])
    gold_tokens = set()
    for gf in gold_facts:
        gold_tokens |= _token_set(gf)
        gold_tokens.add(gf.strip().lower())
    unsupported: list[str] = []
    for claim in claims:
        c_tokens = _token_set(claim.strip())
        if not any(tok in gold_tokens for tok in c_tokens if len(tok) > 2 and tok != "claim"):
            unsupported.append(claim)
    supported = total - len(unsupported)
    return (supported / total, unsupported)


# -- Judge interface --------------------------------------------------------


class Judge(ABC):
    @property
    def model_id(self) -> str:
        return ""

    @abstractmethod
    def judge(
        self,
        *,
        question: Question,
        context: str,
        answer: Answer,
        claims: list[str],
        gold_facts: list[str],
        max_retries: int = 2,
        on_failure: str | None = None,
    ) -> Verdict:  # pragma: no cover
        pass


# -- MockJudge ---------------------------------------------------------------


class MockJudge(Judge):
    @property
    def model_id(self) -> str:
        return "mock"

    def judge(
        self,
        *,
        question: Question,
        context: str,
        answer: Answer,
        claims: list[str],
        gold_facts: list[str],
        max_retries: int = 2,
        on_failure: str | None = None,
    ) -> Verdict:
        injection = _is_injection(claims)
        completeness = _completeness(gold_facts, claims)
        faithfulness, unsupported = _faithfulness(claims, gold_facts)
        supported = not unsupported and not injection
        verdict = Verdict(
            q_id=question.q_id,
            correct=supported,
            supported=supported,
            complete=completeness >= 1.0,
            unsupported_claims=unsupported,
            total_factual_claims=len(claims),
            faithfulness=faithfulness,
            completeness=completeness,
            citation_quality=1.0,
            injection_warning=injection,
            rationale=(
                "all claims supported by ground truth"
                if supported
                else f"{len(unsupported)} unsupported claims detected"
            ),
            status="JUDGED",
        )
        logger.debug(
            "MockJudge {} f={} c={} unsup={} inj={}",
            question.q_id,
            faithfulness,
            completeness,
            len(unsupported),
            injection,
        )
        return verdict


# -- OllamaJudge -------------------------------------------------------------


class OllamaJudge(Judge):
    def __init__(
        self,
        model: str = "qwen3.8:27b-mlx",
        url: str = "http://localhost:11434",
    ) -> None:
        self._model = model
        self._client = OllamaClient(url, model)

    @property
    def model_id(self) -> str:
        return self._model

    def judge(
        self,
        *,
        question: Question,
        context: str,
        answer: Answer,
        claims: list[str],
        gold_facts: list[str],
        max_retries: int = 2,
        on_failure: str | None = None,
    ) -> Verdict:
        system = (
            "You are a precise judge. Given a question, context, "
            "an answer, a claims list, and the gold_facts list, "
            "return a verdict with faithfulness, completeness, "
            "citation_quality, and rationale."
        )
        user = (
            f"Question: {question.question}\n"
            f"Gold facts: {gold_facts}\n"
            f"Answer: {answer.text}\n"
            f"Claims: {claims}\n"
            "Emit JSON verdict."
        )
        last_error: str | None = None
        for attempt in range(max_retries + 1):
            try:
                raw_text, _ = self._client.chat(
                    system=system,
                    context=context,
                    question=user,
                    max_tokens=512,
                    temperature=0.0,
                    seed=42,
                )
                text = raw_text.strip()
                if text.startswith("```"):
                    text = re.sub(
                        r"^```(?:json)?\s*|```$",
                        "",
                        text,
                        flags=re.MULTILINE,
                    ).strip()
                data = json.loads(text)
                verdict = Verdict(
                    q_id=question.q_id,
                    correct=bool(data.get("correct", False)),
                    supported=bool(data.get("supported", False)),
                    complete=bool(data.get("complete", False)),
                    unsupported_claims=data.get("unsupported_claims", []),
                    total_factual_claims=data.get("total_factual_claims", len(claims)),
                    faithfulness=float(data.get("faithfulness", 0.0)),
                    completeness=float(data.get("completeness", 0.0)),
                    citation_quality=float(data.get("citation_quality", 0.0)),
                    injection_warning=_is_injection(claims),
                    rationale=data.get("rationale", ""),
                    status="JUDGED",
                )
                return verdict
            except (OSError, ValueError, ConnectionError, TimeoutError) as exc:
                last_error = f"attempt {attempt + 1}: {exc}"
                logger.warning("OllamaJudge: {}", last_error)
        return Verdict(
            q_id=question.q_id,
            status="ERROR",
            rationale=last_error or "unknown",
        )
