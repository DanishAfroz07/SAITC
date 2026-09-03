"""Composition root: builds concrete objects from Settings and wires them
together. The API controllers and the CLI depend only on RagPipeline /
IngestionPipeline, never on a concrete class - this is the one place that
constructs them.
"""
from functools import lru_cache

from app.config import settings
from app.generation.generator import AnswerGenerator
from app.generation.llm import ChatClient, OllamaChatClient
from app.ingestion.chunker import SectionChunker
from app.ingestion.loader import load_manifest
from app.ingestion.pipeline import IngestionPipeline
from app.rag_pipeline import RagPipeline
from app.retrieval.evidence_analyzer import EvidenceAnalyzer
from app.retrieval.lexical_search import BM25Index
from app.retrieval.reranker import LLMReranker, NoOpReranker, Reranker
from app.retrieval.retriever import HybridRetriever, Retriever
from app.retrieval.vector_store import ChromaVectorStore, OllamaEmbedder
from app.retrieval.version_resolver import VersionResolver
from app.safety.classifier import InputClassifier
from app.safety.guardrails import ContextSanitizer, OutputGuard


@lru_cache
def _embedder() -> OllamaEmbedder:
    return OllamaEmbedder(model=settings.ollama_embed_model, host=settings.ollama_host)


@lru_cache
def _vector_store() -> ChromaVectorStore:
    return ChromaVectorStore(
        persist_dir=settings.chroma_dir,
        collection_name=settings.collection_name,
        embedder=_embedder(),
    )


@lru_cache
def _chat_client() -> ChatClient:
    return OllamaChatClient(model=settings.ollama_llm_model, host=settings.ollama_host)


def _reranker() -> Reranker:
    return LLMReranker(_chat_client()) if settings.rerank_enabled else NoOpReranker()


def _bm25_index() -> BM25Index:
    """Rebuilt fresh each call (cheap - no Ollama call, ~123 chunks) rather
    than cached, so an uploaded or deleted document is reflected immediately
    - same reasoning as build_rag_pipeline() not caching manifest_entries."""
    chunks = _vector_store().get_all_chunks()
    return BM25Index(chunk_ids=[c.chunk_id for c in chunks], texts=[c.text for c in chunks])


def _retriever():
    if settings.hybrid_search_enabled:
        return HybridRetriever(vector_store=_vector_store(), bm25_index=_bm25_index(), top_k=settings.top_k)
    return Retriever(vector_store=_vector_store(), top_k=settings.top_k)


def get_vector_store() -> ChromaVectorStore:
    """Public accessor used by the upload/delete endpoints."""
    return _vector_store()


def build_ingestion_pipeline() -> IngestionPipeline:
    return IngestionPipeline(
        documents_dir=settings.documents_dir,
        manifest_path=settings.manifest_path,
        chunker=SectionChunker(max_chars=settings.chunk_max_chars),
        vector_store=_vector_store(),
    )


def build_rag_pipeline() -> RagPipeline:
    """Not cached: manifest is re-read on every call so an uploaded or
    deleted document is reflected immediately. Cheap - only the embedder,
    vector store and chat client (cached above) are expensive to build."""
    manifest_entries = list(load_manifest(settings.manifest_path).values())
    return RagPipeline(
        classifier=InputClassifier(),
        retriever=_retriever(),
        reranker=_reranker(),
        rerank_top_n=settings.rerank_top_n,
        version_resolver=VersionResolver(manifest_entries),
        evidence_analyzer=EvidenceAnalyzer(
            similarity_threshold=settings.similarity_threshold,
            ambiguity_margin=settings.ambiguity_margin,
            ambiguity_min_sections=settings.ambiguity_min_sections,
            conflict_confidence_threshold=settings.conflict_confidence_threshold,
            high_confidence_score=settings.high_confidence_score,
            medium_confidence_score=settings.medium_confidence_score,
        ),
        sanitizer=ContextSanitizer(),
        generator=AnswerGenerator(chat_client=_chat_client()),
        output_guard=OutputGuard(),
        as_of_date=settings.as_of_date,
    )
