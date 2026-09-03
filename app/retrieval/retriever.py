"""Retrieval strategies. Both classes expose the same `retrieve(query)`
shape, so RagPipeline depends on "a retriever", not on which one.
"""
from app.models import RetrievedChunk
from app.retrieval.lexical_search import BM25Index, reciprocal_rank_fusion
from app.retrieval.vector_store import ChromaVectorStore


class Retriever:
    """Semantic-only: the top-k chunks by embedding similarity."""

    def __init__(self, vector_store: ChromaVectorStore, top_k: int) -> None:
        self._vector_store = vector_store
        self._top_k = top_k

    def retrieve(self, query: str) -> list[RetrievedChunk]:
        return self._vector_store.query(query, self._top_k)


class HybridRetriever:
    """Semantic + lexical (BM25), combined by reciprocal rank fusion. A
    literal term match (e.g. "plan" in a section heading the query names)
    can out-vote a close embedding-similarity call that goes the wrong way -
    see README.md for the concrete case this was built to fix.

    Only reorders chunks the semantic search already found - BM25 acts as a
    tie-breaking signal over that candidate pool, not a second independent
    source of chunks, so every result still carries a real cosine score.
    """

    def __init__(self, vector_store: ChromaVectorStore, bm25_index: BM25Index, top_k: int) -> None:
        self._vector_store = vector_store
        self._bm25_index = bm25_index
        self._top_k = top_k
        self._candidate_k = max(top_k * 3, 15)

    def retrieve(self, query: str) -> list[RetrievedChunk]:
        semantic = self._vector_store.query(query, self._candidate_k)
        lexical = self._bm25_index.search(query, self._candidate_k)

        semantic_by_id = {rc.chunk.chunk_id: rc for rc in semantic}
        fused_ids = reciprocal_rank_fusion(
            [
                [rc.chunk.chunk_id for rc in semantic],
                [chunk_id for chunk_id, _ in lexical],
            ]
        )

        result: list[RetrievedChunk] = []
        for chunk_id in fused_ids:
            if chunk_id in semantic_by_id:
                result.append(semantic_by_id[chunk_id])
            if len(result) >= self._top_k:
                break
        return result
