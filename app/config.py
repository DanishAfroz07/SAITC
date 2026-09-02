"""Central configuration. Every tunable value used anywhere in the app is
read once from the environment (via .env) into this single Settings object,
so no module reaches for os.environ directly.
"""
from datetime import date
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # The assignment's fixed "as of" date. Configurable rather than hard-coded
    # so evaluation can be re-run against a different point in time.
    as_of_date: date = date(2026, 8, 27)

    documents_dir: Path = Path("data/documents")
    manifest_path: Path = Path("data/corpus_manifest.json")
    chroma_dir: Path = Path("chroma")
    collection_name: str = "cerulean_corpus"

    ollama_host: str = "http://localhost:11434"
    ollama_llm_model: str = "llama3.2:3b"
    ollama_embed_model: str = "nomic-embed-text"

    top_k: int = 8
    similarity_threshold: float = 0.35
    ambiguity_margin: float = 0.05
    chunk_max_chars: int = 1200

    # Reranking: retrieve top_k broadly by embedding similarity, then rerank
    # and (for the sufficient-evidence case only) narrow to rerank_top_n
    # before generation - see app/rag_pipeline.py.
    rerank_enabled: bool = True
    rerank_top_n: int = 4

    api_host: str = "0.0.0.0"
    api_port: int = 8000


settings = Settings()
