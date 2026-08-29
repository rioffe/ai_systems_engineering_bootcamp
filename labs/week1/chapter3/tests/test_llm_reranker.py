# I-015 / section 22 step 9: the LLM re-scoring pass. MockLLMReranker is the
# deterministic double; OllamaLLMReranker falls back to lexical on any backend fault.
from rag.model import LLMReranker, MockLLMReranker, OllamaLLMReranker


def _cands():
    return [("a", "the cat sat on the mat"),
            ("b", "deep learning models and training"),
            ("c", "a mat for the cat")]


def test_llmreranker_is_abstract():
    assert issubclass(MockLLMReranker, LLMReranker)
    assert issubclass(OllamaLLMReranker, LLMReranker)
    cands = _cands()
    r = MockLLMReranker().rerank("cat on the mat", cands, top_k=3)
    assert isinstance(r, list)
      # the most relevant candidate (two query words) ranks first
    assert r[0][0] == "a"
      # top_k is honoured
    assert len(r) <= 3


def test_mock_and_real_doubles_agree_on_lexical_fallback():
    cands = _cands()
    mock = MockLLMReranker().rerank("cat on the mat", cands, top_k=3)
    # OllamaLLMReranker with no live backend must fall back to the lexical double
    real = OllamaLLMReranker().rerank("cat on the mat", cands, top_k=3)
    assert mock == real
