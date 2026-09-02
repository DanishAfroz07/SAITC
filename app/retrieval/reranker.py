"""Optional reranking stage (listed as an optional extra in the assignment).

Defined as a Protocol so the pipeline depends on "something that can rerank",
never on a specific implementation (Open/Closed: a cross-encoder reranker
could be added later as a second class implementing the same interface,
without changing RagPipeline at all). NoOpReranker is the default and keeps
retrieval order unchanged - it exists so the pipeline always has a reranking
seam to call, even when nothing is plugged into it.
"""
from typing import Protocol

from app.models import RetrievedChunk


class Reranker(Protocol):
    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]: ...


class NoOpReranker:
    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return chunks
