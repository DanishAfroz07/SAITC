"""Reorders retrieved chunks by relevance using the chat LLM itself
(listwise reranking) - one extra Ollama call per query, asking the model to
read all candidates and order them, instead of trusting embedding-similarity
rank alone. NoOpReranker keeps the interface usable with reranking disabled.
"""
import logging
import re
from typing import Protocol

from app.generation.llm import ChatClient, ChatMessage
from app.models import RetrievedChunk

logger = logging.getLogger(__name__)

_PROMPT = """Rank the passages below by how relevant they are to the question, most relevant \
first. Reply with ONLY the passage labels in order, comma-separated (e.g. "C,A,B"). No other text.

Question: {query}

Passages:
{passages}"""


class Reranker(Protocol):
    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]: ...


class NoOpReranker:
    """Keeps retrieval order unchanged - used when reranking is disabled."""

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return chunks


class LLMReranker:
    """Asks the chat model to reorder candidates by relevance. Falls back to
    the original order if the model's reply can't be parsed, or if the call
    fails - reranking is a quality improvement, not something a query should
    fail over."""

    def __init__(self, chat_client: ChatClient) -> None:
        self._chat_client = chat_client

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if len(chunks) <= 1:
            return chunks

        labels = [chr(ord("A") + i) for i in range(len(chunks))]
        passages = "\n\n".join(f"[{label}] {c.chunk.text[:400]}" for label, c in zip(labels, chunks))
        prompt = _PROMPT.format(query=query, passages=passages)

        try:
            response = self._chat_client.complete([ChatMessage("user", prompt)])
            order = self._parse_order(response, labels)
        except Exception:
            logger.warning("Reranker call failed; keeping original retrieval order.", exc_info=True)
            return chunks

        if not order:
            return chunks

        by_label = dict(zip(labels, chunks))
        reranked = [by_label[label] for label in order if label in by_label]
        leftover = [c for label, c in zip(labels, chunks) if label not in order]
        return reranked + leftover

    @staticmethod
    def _parse_order(response: str, labels: list[str]) -> list[str]:
        valid = set(labels)
        seen: list[str] = []
        for ch in re.findall(r"[A-Z]", response.upper()):
            if ch in valid and ch not in seen:
                seen.append(ch)
        return seen
