"""Embeds chunk text via Ollama and stores/queries it in a persistent Chroma
collection. Every chunk's metadata travels with it into Chroma so it comes
back out at query time.
"""
from datetime import date
from pathlib import Path
from typing import Protocol

import chromadb
import ollama

from app.models import Chunk, DocumentMetadata, RetrievedChunk


class Embedder(Protocol):
    """Anything that can turn text into vectors - lets ChromaVectorStore
    depend on this instead of on Ollama specifically."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def embed_one(self, text: str) -> list[float]: ...


class OllamaEmbedder:
    def __init__(self, model: str, host: str) -> None:
        self._client = ollama.Client(host=host)
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(text) for text in texts]

    def embed_one(self, text: str) -> list[float]:
        response = self._client.embeddings(model=self._model, prompt=text)
        return response["embedding"]


class ChromaVectorStore:
    def __init__(self, persist_dir: Path, collection_name: str, embedder: Embedder) -> None:
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection_name = collection_name
        self._collection = self._client.get_or_create_collection(
            name=collection_name, metadata={"hnsw:space": "cosine"}
        )
        self._embedder = embedder

    def reset(self) -> None:
        """Drops and recreates the collection, so a full ingest never leaves
        stale chunks behind."""
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

    def delete_by_document_id(self, document_id: str) -> None:
        """Removes every chunk for one document - used when re-uploading or
        deleting a document, so its old chunks don't linger."""
        self._collection.delete(where={"document_id": document_id})

    def query(self, query_text: str, top_k: int) -> list[RetrievedChunk]:
        query_embedding = self._embedder.embed_one(query_text)
        result = self._collection.query(query_embeddings=[query_embedding], n_results=top_k)
        return self._to_retrieved_chunks(result)

    def get_all_chunks(self) -> list[Chunk]:
        """Every chunk in the collection, no embedding call needed - used to
        build the lexical (BM25) index for hybrid search."""
        result = self._collection.get()
        return [
            self._chunk_from_parts(chunk_id, text, meta)
            for chunk_id, text, meta in zip(result["ids"], result["documents"], result["metadatas"])
        ]

    @staticmethod
    def _chunk_from_parts(chunk_id: str, text: str, meta: dict) -> Chunk:
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
        return Chunk(
            chunk_id=chunk_id,
            document_id=meta["document_id"],
            section=meta["section"],
            text=text,
            is_table=meta["is_table"],
            metadata=metadata,
        )

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

        ids = result["ids"][0]
        documents = result["documents"][0]
        metadatas = result["metadatas"][0]
        distances = result["distances"][0]

        retrieved: list[RetrievedChunk] = []
        for chunk_id, text, meta, distance in zip(ids, documents, metadatas, distances):
            chunk = cls._chunk_from_parts(chunk_id, text, meta)
            # Chroma's cosine "distance" is (1 - similarity); invert it back.
            retrieved.append(RetrievedChunk(chunk=chunk, score=1.0 - distance))
        return retrieved
