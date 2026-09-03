from datetime import date

from app.models import Chunk, DocumentMetadata, RetrievedChunk
from app.retrieval.lexical_search import BM25Index
from app.retrieval.retriever import HybridRetriever


def _meta(doc_id: str) -> DocumentMetadata:
    return DocumentMetadata(doc_id, "Title", "1.0", date(2026, 1, 1), "Owner", "Internal", None, f"{doc_id}.pdf")


def _rc(doc_id: str, text: str, score: float) -> RetrievedChunk:
    chunk = Chunk(f"{doc_id}-c", doc_id, "1. Section", text, False, _meta(doc_id))
    return RetrievedChunk(chunk=chunk, score=score)


class _FakeVectorStore:
    def __init__(self, results: list[RetrievedChunk]) -> None:
        self._results = results

    def query(self, query_text: str, top_k: int) -> list[RetrievedChunk]:
        return self._results[:top_k]


def test_hybrid_retriever_can_promote_a_lexical_match_above_a_semantic_one():
    # "B" scores slightly lower semantically than "A", but only "B" contains
    # the literal word "plan" - the case this was built to fix (see Q4 in
    # README.md): a lexical signal should be able to flip that order.
    semantic_results = [
        _rc("A", "Additional users are billed per month per user.", 0.80),
        _rc("B", "The Atlas Professional subscription plan costs SAR 5,200.", 0.78),
    ]
    vector_store = _FakeVectorStore(semantic_results)
    bm25 = BM25Index(
        chunk_ids=["A-c", "B-c"],
        texts=[c.chunk.text for c in semantic_results],
    )
    retriever = HybridRetriever(vector_store=vector_store, bm25_index=bm25, top_k=2)

    result = retriever.retrieve("current price of the Atlas Professional plan")

    assert [r.chunk.document_id for r in result][0] == "B"


def test_hybrid_retriever_never_returns_more_than_top_k():
    semantic_results = [_rc(f"D{i}", f"document {i} content", 0.9 - i * 0.01) for i in range(10)]
    vector_store = _FakeVectorStore(semantic_results)
    bm25 = BM25Index(chunk_ids=[c.chunk.chunk_id for c in semantic_results], texts=[c.chunk.text for c in semantic_results])
    retriever = HybridRetriever(vector_store=vector_store, bm25_index=bm25, top_k=3)

    result = retriever.retrieve("document content")

    assert len(result) == 3


def test_hybrid_retriever_only_returns_chunks_the_semantic_search_found():
    # Even if BM25 scores something highly, a chunk missing from the
    # semantic candidate pool must never appear - every result needs a
    # real cosine score for downstream threshold checks to make sense.
    semantic_results = [_rc("A", "some content about leave policy", 0.9)]
    vector_store = _FakeVectorStore(semantic_results)
    bm25 = BM25Index(
        chunk_ids=["A-c", "ghost-c"],
        texts=["some content about leave policy", "a phrase that matches the query term exactly"],
    )
    retriever = HybridRetriever(vector_store=vector_store, bm25_index=bm25, top_k=5)

    result = retriever.retrieve("query term exactly")

    assert all(r.chunk.document_id == "A" for r in result)
