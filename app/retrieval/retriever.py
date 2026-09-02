"""Retrieves the top-k candidate chunks for a query. Deliberately thin: it
owns nothing except "ask the vector store for the top-k", so it can be unit
tested against a fake store without spinning up Chroma or Ollama.
"""
from app.models import RetrievedChunk
from app.retrieval.vector_store import ChromaVectorStore


class Retriever:
    def __init__(self, vector_store: ChromaVectorStore, top_k: int) -> None:
        self._vector_store = vector_store
        self._top_k = top_k

    def retrieve(self, query: str) -> list[RetrievedChunk]:
        return self._vector_store.query(query, self._top_k)
