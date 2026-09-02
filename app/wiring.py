"""Composition root: the one place that knows how to build concrete objects
from Settings and wire them together. main.py and api/routes.py both call
into here and never construct a concrete class themselves - that's what
keeps them free to depend only on interfaces (RagPipeline, IngestionPipeline).
"""
from functools import lru_cache

from app.config import settings
from app.generation.generator import AnswerGenerator
from app.generation.llm import OllamaChatClient
from app.ingestion.chunker import SectionChunker
from app.ingestion.loader import load_manifest
from app.ingestion.pipeline import IngestionPipeline
from app.pipeline.rag_pipeline import RagPipeline
from app.retrieval.embeddings import OllamaEmbedder
from app.retrieval.evidence_analyzer import EvidenceAnalyzer
from app.retrieval.reranker import NoOpReranker
from app.retrieval.retriever import Retriever
from app.retrieval.vector_store import ChromaVectorStore
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


def build_ingestion_pipeline() -> IngestionPipeline:
    return IngestionPipeline(
        documents_dir=settings.documents_dir,
        manifest_path=settings.manifest_path,
        chunker=SectionChunker(max_chars=settings.chunk_max_chars),
        vector_store=_vector_store(),
    )


@lru_cache
def build_rag_pipeline() -> RagPipeline:
    manifest_entries = list(load_manifest(settings.manifest_path).values())
    return RagPipeline(
        classifier=InputClassifier(),
        retriever=Retriever(vector_store=_vector_store(), top_k=settings.top_k),
        reranker=NoOpReranker(),
        version_resolver=VersionResolver(manifest_entries),
        evidence_analyzer=EvidenceAnalyzer(
            similarity_threshold=settings.similarity_threshold,
            ambiguity_margin=settings.ambiguity_margin,
        ),
        sanitizer=ContextSanitizer(),
        generator=AnswerGenerator(
            chat_client=OllamaChatClient(model=settings.ollama_llm_model, host=settings.ollama_host)
        ),
        output_guard=OutputGuard(),
        as_of_date=settings.as_of_date,
    )
