from datetime import date

from app.models import Chunk, DocumentMetadata, RetrievedChunk
from app.retrieval.reranker import LLMReranker, NoOpReranker


class _FakeChatClient:
    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, messages) -> str:
        return self._response


def _meta(doc_id: str) -> DocumentMetadata:
    return DocumentMetadata(doc_id, "Title", "1.0", date(2026, 1, 1), "Owner", "Internal", None, f"{doc_id}.pdf")


def _rc(doc_id: str) -> RetrievedChunk:
    chunk = Chunk(f"{doc_id}-c", doc_id, "1. Section", f"text for {doc_id}", False, _meta(doc_id))
    return RetrievedChunk(chunk=chunk, score=0.5)


def test_noop_reranker_keeps_order():
    chunks = [_rc("A"), _rc("B"), _rc("C")]
    result = NoOpReranker().rerank("q", chunks)
    assert result == chunks


def test_llm_reranker_reorders_by_model_response():
    chunks = [_rc("A"), _rc("B"), _rc("C")]  # labels A, B, C in this order
    reranker = LLMReranker(_FakeChatClient("C,A,B"))
    result = reranker.rerank("q", chunks)
    assert [c.chunk.document_id for c in result] == ["C", "A", "B"]


def test_llm_reranker_appends_labels_missing_from_response():
    chunks = [_rc("A"), _rc("B"), _rc("C")]
    reranker = LLMReranker(_FakeChatClient("B"))  # model only mentions B
    result = reranker.rerank("q", chunks)
    assert [c.chunk.document_id for c in result] == ["B", "A", "C"]


def test_llm_reranker_falls_back_to_original_order_on_unparseable_response():
    chunks = [_rc("A"), _rc("B")]
    reranker = LLMReranker(_FakeChatClient("I cannot help with that."))
    result = reranker.rerank("q", chunks)
    assert result == chunks


def test_llm_reranker_falls_back_when_chat_client_raises():
    class _RaisingChatClient:
        def complete(self, messages):
            raise RuntimeError("connection refused")

    chunks = [_rc("A"), _rc("B")]
    reranker = LLMReranker(_RaisingChatClient())
    result = reranker.rerank("q", chunks)
    assert result == chunks


def test_llm_reranker_skips_call_for_single_chunk():
    chunks = [_rc("A")]

    class _ExplodingChatClient:
        def complete(self, messages):
            raise AssertionError("should not be called for a single chunk")

    result = LLMReranker(_ExplodingChatClient()).rerank("q", chunks)
    assert result == chunks
