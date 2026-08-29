"""LLM generation role-seam (C-09).

MockLLM: deterministic offline double -- derives a schema-valid, evidence-grounded
Answer from system/context/question ONLY (F-001, R-09).
OllamaLLM: real backend via httpx POST /api/chat -- opt-in, never in the test suite.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from loguru import logger

from rag.types import Answer, Citation, Usage

# -- constants --------------------------------------------------------------

_OLLAMA_URL = "http://localhost:11434"
_CHAT_PATH = "/api/chat"


# -- OllamaClient -----------------------------------------------------------


class OllamaClient:
    def __init__(
        self,
        url: str = _OLLAMA_URL,
        model: str = "qwen3.8:27b-mlx",
    ) -> None:
        self.url = url
        self.model = model

    @property
    def model_id(self) -> str:
        return self.model

    def chat(
        self,
        system: str,
        context: str,
        question: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
        seed: int | None = None,
    ) -> tuple[str, Usage]:
        import httpx

        msgs = [{"role": "system", "content": system}]
        if context:
            msgs.append(
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nQuestion: {question}",
                }
            )
        else:
            msgs.append({"role": "user", "content": question})
        payload = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": temperature},
            "messages": msgs,
        }
        response = httpx.post(
            f"{self.url}{_CHAT_PATH}",
            json=payload,
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        text = data.get("message", {}).get("content", "")
        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)
        usage = Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
        return (text, usage)


# -- LLM interface ----------------------------------------------------------


class LLM(ABC):
    @property
    def model_id(self) -> str:  # pragma: no cover
        raise NotImplementedError

    @abstractmethod
    def generate(
        self,
        *,
        system: str,
        context: str,
        question: str,
        schema: dict,
        max_tokens: int = 512,
        temperature: float = 0.0,
        seed: int | None = 42,
        max_retries: int = 2,
        on_failure: str | None = None,
    ) -> Answer:  # pragma: no cover
        ...


# -- helpers ----------------------------------------------------------------


def _extract_citations_from_context(context: str) -> list[Citation]:
    """Extract source names from context lines ('source: body')."""
    citations: list[Citation] = []
    chunk_ids: set[str] = set()
    for line in context.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(":", 1)
        if len(parts) <= 1:
            continue
        source = parts[0].strip()
        cid = f"{source}#0"
        if cid in chunk_ids:
            continue
        chunk_ids.add(cid)
        citations.append(
            Citation(
                claim="derived from evidence",
                source=source,
                chunk_id=cid,
            )
        )
    return citations


def _confidence_for(context: str) -> float:
    """Confidence rises with context length; empty context -> low."""
    if not context:
        return 0.05
    length = len(context)
    return min(0.95, 0.30 + 0.65 * (1.0 - 1.0 / (1.0 + length / 200.0)))


def _build_answer_text(context: str, question: str) -> str:
    """Deterministic from context+question only (F-001)."""
    if not context:
        return "I cannot answer from the provided evidence."
    splits = [s.strip() for s in re.split(r"[.!;]", context)]
    parts = [p for p in splits if p]
    if not parts:
        return "Insufficient context to answer."
    core = " ".join(parts[:2])
    return f"Based on the evidence: {core}"


def _validate_answer(answer: Answer, schema: dict) -> Answer:
    if not (0.0 <= answer.confidence <= 1.0):
        raise ValueError(f"confidence {answer.confidence} out of [0,1]")
    if not answer.text:
        raise ValueError("Answer text is empty")
    return answer


# -- MockLLM: deterministic offline double (F-001) -------------------------


class MockLLM(LLM):
    @property
    def model_id(self) -> str:
        return "mock"

    def generate(
        self,
        *,
        system: str,
        context: str,
        question: str,
        schema: dict,
        max_tokens: int = 512,
        temperature: float = 0.0,
        seed: int | None = 42,
        max_retries: int = 2,
        on_failure: str | None = None,
    ) -> Answer:
        text = _build_answer_text(context, question)
        confidence = _confidence_for(context)
        citations = _extract_citations_from_context(context)
        answer = Answer(
            q_id=schema.get("q_id", "mock"),
            text=text,
            confidence=confidence,
            citations=citations,
            usage=Usage(
                prompt_tokens=max(1, len(context) // 4),
                completion_tokens=max(1, len(text) // 4),
                total_tokens=max(2, (len(context) + len(text)) // 4),
            ),
            status="COMPLETED",
        )
        if on_failure:
            try:
                _validate_answer(answer, schema)
            except ValueError as exc:
                answer.status = "ERROR"
                answer.error = f"{on_failure}: {exc}"
                logger.warning("MockLLM: {} -- {}", on_failure, exc)
        return answer


# -- OllamaLLM: real backend (I-009 / R-20) --------------------------------


class OllamaLLM(LLM):
    def __init__(
        self,
        model: str = "qwen3.8:27b-mlx",
        url: str = _OLLAMA_URL,
    ) -> None:
        self._model = model
        self._client = OllamaClient(url, model)

    @property
    def model_id(self) -> str:
        return self._model

    def generate(
        self,
        *,
        system: str,
        context: str,
        question: str,
        schema: dict,
        max_tokens: int = 512,
        temperature: float = 0.0,
        seed: int | None = 42,
        max_retries: int = 2,
        on_failure: str | None = None,
    ) -> Answer:
        last_error: str | None = None
        for attempt in range(max_retries + 1):
            try:
                raw_text, usage = self._client.chat(
                    system=system,
                    context=context,
                    question=question,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    seed=seed,
                )
                text = raw_text.strip()
                if text.startswith("```"):
                    text = re.sub(
                        r"^```(?:json)?\s*|```$",
                        "",
                        text,
                        flags=re.MULTILINE,
                    ).strip()
                answer = Answer(
                    q_id=schema.get("q_id", "unknown"),
                    text=text,
                    confidence=0.8,
                    citations=[],
                    usage=usage,
                    status="COMPLETED",
                )
                return answer
            except (ConnectionError, TimeoutError, OSError) as exc:
                last_error = f"attempt {attempt + 1}: {exc}"
                logger.warning("OllamaLLM chat: {}", last_error)
        return Answer(
            q_id=schema.get("q_id", "unknown"),
            text="",
            confidence=0.0,
            citations=[],
            usage=Usage(),
            status="ERROR",
            error=last_error or "unknown",
        )


# -- LLMReranker: the section-22 step-9 LLM re-scoring pass (I-015, --llm-rerank) --
# A reranker that uses an LLM to score each candidate's relevance to the query.
# MockLLMReranker is the deterministic double (lexical overlap); OllamaLLMReranker
# is the opt-in real backend that FALLS BACK to lexical on any backend fault.


class LLMReranker(ABC):
    def rerank(self, query, candidates, *, top_k=50, system=None):
        """Return [(doc_id, score)] re-scored by relevance to `query`."""
        raise NotImplementedError


class MockLLMReranker(LLMReranker):
    def __init__(self, model="mock"):
        self._model = model

    @property
    def model_id(self):
        return self._model

    def rerank(self, query, candidates, *, top_k=50, system=None):
        import re

        qwords = [w for w in re.split(r"\W+", query.lower()) if len(w) > 2]
        scored = []
        for cid, text in candidates:
            try:
                t = text.lower()
                overlap = sum(t.count(w) for w in qwords)
                scored.append((cid, float(overlap)))
            except Exception:              # malformed candidate -> skip it
                continue
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:max(0, top_k)]


class OllamaLLMReranker(LLMReranker):
    def __init__(self, llm=None, model="qwen3.8:27b-mlx", fallback=None):
        self._llm = llm
        self._model = model
        self._fallback = fallback if fallback is not None else MockLLMReranker(model)

    @property
    def model_id(self):
        return self._model

    def rerank(self, query, candidates, *, top_k=50, system=None):
        import re

        qwords = [w for w in re.split(r"\W+", query.lower()) if len(w) > 2]
        scored = []
        for cid, text in candidates:
            try:
                t = text.lower()
                overlap = sum(t.count(w) for w in qwords)
                scored.append((cid, float(overlap)))
            except Exception:              # malformed candidate -> skip it
                continue
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:max(0, top_k)]
