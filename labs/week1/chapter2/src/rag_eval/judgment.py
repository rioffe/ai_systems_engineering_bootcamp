"""C-06 the Judge -- the second probabilistic role: LLM-as-judge (SPEC R-06/R-09).

Two implementations behind one interface (R-01):

* ``MockJudge`` -- a deterministic, offline double (R-14) that derives a schema-valid
    verdict from the **ground truth**: the intersection of the question's ``relevant_docs``
    and the context's ``provenance``, plus the answer's citations. This lets the automated
    suite measure the *metric math* (R-07/08/09) without a model in the loop.
* ``OllamaJudge`` -- the real backend: it asks ``qwen3.8:27b-mlx`` (the same model as
    generation by default, Q-03) to emit the verdict schema, validating like ch1 C-05.

Hallucination math (I-007/R-09): a *foreign* citation -- a doc id the answer cites that is
absent from the context -- counts as one unsupported claim out of the total cited; an
all-supported answer and a zero-claim answer both yield a 0.0 rate downstream in aggregate.
A verdict that exhausts its parse/validation retries is ``Verdict(status="ERROR")`` (E-10)
and never an unvalidated dict (I-010).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

from .model import OllamaClient
from .schemas import (
    DEFAULT_MAX_RETRIES,
    VERDICT_SCHEMA,
    build_retry_directive,
    generate_structured,
)
from .types import Answer, Context, Question, Verdict

# The judge system prompt (ch1 style): "emit the verdict schema as JSON".
_VERDICT_SYSTEM = (
    "Judge a grounded RAG answer. Using ONLY the retrieved documents visible in the "
    "context, decide: correct (does the answer answer the question?), supported (is every "
    "factual claim grounded in the context?), complete (are all facts in the relevant "
    "documents reflected?). Respond with a SINGLE valid JSON object (no prose, no fences) "
    'of the form {"correct": bool, "supported": bool, "complete": bool, '
    '"unsupported_claims": array of strings (claims not traceable to a provided doc), '
    '"total_factual_claims": integer >= 0, "rationale": string}.'
)


class Judge(ABC):
    """A Judge produces a grounded, structured §19/§20 verdict via the schema gate.

    Subclasses implement ``_raw`` (the actual verdict-emitting call); ``judge`` owns the
    shared parse -> validate -> error-informed-retry loop over ``VERDICT_SCHEMA``. The
    per-attempt inputs are stashed on ``_inputs`` for the deterministic ``MockJudge``.
    """

    @property
    @abstractmethod
    def model_id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def _raw(self, sys_prompt: str, user_prompt: str, **_k: object) -> str:
        raise NotImplementedError

    def judge(
        self,
        *,
        question: Question,
        context: Context,
        answer: Answer,
        max_retries: int = DEFAULT_MAX_RETRIES,
        on_failure: str | None = None,
    ) -> Verdict:
        # parse -> validate -> error-informed-retry over VERDICT_SCHEMA (ch1 C-05).
        self._inputs = (question, context, answer)
        base = _VERDICT_SYSTEM + (f"\n{on_failure}" if on_failure else "")
        last_directive: str | None = None

        def prompt_for_attempt(attempt: int, last):
            nonlocal last_directive
            if last is not None and not last.ok:
                last_directive = build_retry_directive(VERDICT_SCHEMA, last)
            user = _judge_user(question, context, answer, last_directive)
            return self._raw(base, user)

        structured = generate_structured(
            prompt_for_attempt, VERDICT_SCHEMA, max_retries=max_retries
        )
        q_id = question.q_id
        if not structured.ok:
            return Verdict(
                q_id=q_id,
                correct=None,
                supported=None,
                complete=None,
                unsupported_claims=[],
                total_factual_claims=0,
                rationale="",
                status="ERROR",
            )
        data = structured.data  # structured.ok implies data present (I-010)
        assert data is not None
        total = data.get("total_factual_claims", 0)
        try:
            total = int(total)
        except (TypeError, ValueError):
            total = 0  # defensive; the schema already bounds this to an int >= 0
        return Verdict(
            q_id=q_id,
            correct=bool(data.get("correct")),
            supported=bool(data.get("supported")),
            complete=bool(data.get("complete")),
            unsupported_claims=[str(c) for c in data.get("unsupported_claims", [])],
            total_factual_claims=total,
            rationale=str(data.get("rationale", "")),
            status="JUDGED",
        )


class MockJudge(Judge):
    """The deterministic double: verdicts come from the ground truth, not a model."""

    def __init__(self, seed: int | None = 42) -> None:
        self._inputs: tuple[Question, Context, Answer] | None = None
        self._seed = seed

    @property
    def model_id(self) -> str:
        return ""  # a deterministic role has no model id (Q-03)

    def _raw(self, sys_prompt: str, user_prompt: str, **_k: object) -> str:
        # A schema-valid verdict dict from ground truth (deterministic, I-010).
        return json.dumps(_mock_verdict(self._inputs))


class OllamaJudge(Judge):
    """The real judge: the same model as generation by default (Q-03), emitting the
    verdict schema. Fatal transport faults (E-11/E-12) propagate to the CLI."""

    def __init__(
        self,
        name: str,
        client: OllamaClient | None = None,
        model_id: str | None = None,
    ) -> None:
        self._name = name
        self._client = client if client is not None else OllamaClient()
        self._id_ = model_id or name
        self._inputs: tuple[Question, Context, Answer] | None = None

    @property
    def model_id(self) -> str:
        return self._id_

    def _raw(self, sys_prompt: str, user_prompt: str, **_k: object) -> str:
        # Fatal transport faults (E-11/E-12) propagate out of judge() to the CLI; parse
        # / validation failures are handled by the surrounding generate_structured loop.
        text, _usage = self._client.chat(self._name, sys_prompt, user_prompt)
        return text


def _mock_verdict(inputs: tuple[Question, Context, Answer] | None) -> dict:
    # Deterministic verdict from ground truth (R-14/R-15). `supported` is True only when
    # every cited claim is traceable to a provided doc; a foreign citation is one
    # unsupported claim (E-08 / T-08a); `total_factual_claims` is the §20 denominator.
    if inputs is None:
        return {
            "correct": False,
            "supported": False,
            "complete": False,
            "unsupported_claims": [],
            "total_factual_claims": 0,
            "rationale": "no inputs",
        }
    question, context, answer = inputs
    provenance = set(context.provenance)
    relevant = set(question.relevant_docs)
    sources = list(answer.sources)
    foreign = [s for s in sources if s not in provenance]
    grounded = [s for s in sources if s in provenance]
    unsupported_claims = [f"cites {s} (doc id absent from context)" for s in foreign]
    total = len(sources)
    complete = bool(relevant) and relevant.issubset(provenance)
    supported = len(foreign) == 0 and bool(answer.text.strip())
    correct = complete and supported and len(grounded) > 0
    rationale = (
        "grounded claims "
        + f"{len(grounded)}; unsupported {len(foreign)}/{total}; "
        + f"complete={complete}; supported={supported}"
    )
    return {
        "correct": correct,
        "supported": supported,
        "complete": complete,
        "unsupported_claims": unsupported_claims,
        "total_factual_claims": total,
        "rationale": rationale,
    }


def _judge_user(
    question: Question,
    context: Context,
    answer: Answer,
    directive: str | None,
) -> str:
    # The judge sees the question, the context it was grounded in, and the answer under
    # judgment -- NOT the gold answer (that would leak the eval into the judge).
    parts = [
        "QUESTION " + question.question,
        "RETRIEVED CONTEXT:\n" + context.prompt,
        f"ANSWER UNDER JUDGMENT: {answer.text}\n(cited sources: {answer.sources})",
    ]
    if directive:
        parts.append(f"RETRY DIRECTIVE (fix the previous attempt): {directive}")
    return "\n\n".join(parts)


__all__ = [
    "VERDICT_SCHEMA",
    "Judge",
    "MockJudge",
    "OllamaJudge",
    "_mock_verdict",
]
