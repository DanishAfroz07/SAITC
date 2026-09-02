"""Embedding client. Defined as a Protocol so the vector store depends on
"something that can embed text", not specifically on Ollama - a production
swap to a hosted embedding API would only touch this file.
"""
from typing import Protocol

import ollama


class Embedder(Protocol):
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
