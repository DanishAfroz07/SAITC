"""Persistent Chroma-backed store for embedded document chunks.

Metadata (document_id, version, effective_date, supersedes, classification,
section, is_table) travels with every chunk into Chroma, so it survives the
round trip back out at query time - the corpus README is explicit that
metadata must "reach your retrieval layer", and this is where that happens.
"""
from datetime import date
from pathlib import Path

import chromadb

from app.models import Chunk, DocumentMetadata, RetrievedChunk
from app.retrieval.embeddings import Embedder


class ChromaVectorStore:
    def __init__(self, persist_dir: Path, collection_name: str, embedder: Embedder) -> None:
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection_name = collection_name
        self._collection = self._client.get_or_create_collection(
            name=collection_name, metadata={"hnsw:space": "cosine"}
        )
        self._embedder = embedder

    def reset(self) -> None:
        """Drops and recreates the collection - ingestion always starts clean
        so re-running it never leaves stale chunks behind."""
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name, metadata={"hnsw:space": "cosine"}
        )

    def add_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        embeddings = self._embedder.embed([c.text for c in chunks])
        self._collection.add(
            ids=[c.chunk_id for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[self._to_metadata_dict(c) for c in chunks],
        )

    def query(self, query_text: str, top_k: int) -> list[RetrievedChunk]:
        query_embedding = self._embedder.embed_one(query_text)
        result = self._collection.query(query_embeddings=[query_embedding], n_results=top_k)
        return self._to_retrieved_chunks(result)

    @staticmethod
    def _to_metadata_dict(chunk: Chunk) -> dict:
        m = chunk.metadata
        return {
            "document_id": m.document_id,
            "title": m.title,
            "version": m.version,
            "effective_date": m.effective_date.isoformat(),
            "owner": m.owner,
            "classification": m.classification,
            "supersedes": m.supersedes or "",
            "file_name": m.file_name,
            "section": chunk.section,
            "is_table": chunk.is_table,
        }

    @classmethod
    def _to_retrieved_chunks(cls, result: dict) -> list[RetrievedChunk]:
        if not result["ids"] or not result["ids"][0]:
            return []

        retrieved: list[RetrievedChunk] = []
        ids = result["ids"][0]
        documents = result["documents"][0]
        metadatas = result["metadatas"][0]
        distances = result["distances"][0]

        for chunk_id, text, meta, distance in zip(ids, documents, metadatas, distances):
            metadata = DocumentMetadata(
                document_id=meta["document_id"],
                title=meta["title"],
                version=meta["version"],
                effective_date=date.fromisoformat(meta["effective_date"]),
                owner=meta["owner"],
                classification=meta["classification"],
                supersedes=meta["supersedes"] or None,
                file_name=meta["file_name"],
            )
            chunk = Chunk(
                chunk_id=chunk_id,
                document_id=meta["document_id"],
                section=meta["section"],
                text=text,
                is_table=meta["is_table"],
                metadata=metadata,
            )
            # Chroma's cosine "distance" is (1 - cosine similarity); invert it
            # back to a similarity score so thresholds elsewhere read naturally.
            retrieved.append(RetrievedChunk(chunk=chunk, score=1.0 - distance))
        return retrieved
