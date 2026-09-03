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
    # Evidence-based, not guessed: live testing against the real embedding
    # model (nomic-embed-text) showed a totally irrelevant query ("What was
    # the company's revenue in 2025?") still scored 0.61 against unrelated
    # document headers - comfortably clearing a 0.35 threshold and causing
    # a false CONFLICTING classification instead of INSUFFICIENT. 0.62 was
    # verified to exclude that noise while still keeping every genuinely
    # relevant chunk seen in testing. See README.md.
    similarity_threshold: float = 0.62
    ambiguity_margin: float = 0.03
    # Also evidence-based: at 3, this false-triggered AMBIGUOUS on broad but
    # perfectly answerable questions ("What is the annual leave policy?"),
    # because one document's several sections (entitlement, accrual, carry-
    # over) look like "multiple sections" even though they're all facets of
    # one coherent answer, not competing candidates the way PROD-DOC-009's
    # distinct limit types genuinely are. Raised until that stopped
    # happening in live testing.
    ambiguity_min_sections: int = 5
    # Evidence-based: a genuine conflict pair scored 0.784/0.763 live, while
    # an unrelated question's incidental co-retrieval of one conflict-pair
    # member scored only 0.664 - enough to falsely trigger CONFLICTING
    # before this gate existed. See EvidenceAnalyzer and README.md.
    conflict_confidence_threshold: float = 0.70
    # Retrieval-confidence tiers shown alongside a SUFFICIENT answer, not a
    # measure of whether the answer is factually correct - see
    # RetrievalConfidence in app/models.py. Calibrated against real scores:
    # clean single-topic matches scored 0.73-0.79 live.
    high_confidence_score: float = 0.78
    medium_confidence_score: float = 0.68
    chunk_max_chars: int = 1200

    # Hybrid (semantic + BM25) search - see app/retrieval/retriever.py:HybridRetriever.
    # Default set based on live verification; see README.md for the result.
    hybrid_search_enabled: bool = False

    # Reranking: implemented (app/retrieval/reranker.py) but off by default -
    # this corpus is small enough that semantic retrieval alone ranks
    # cleanly; see README.md for the reasoning.
    rerank_enabled: bool = False
    rerank_top_n: int = 4

    api_host: str = "0.0.0.0"
    api_port: int = 8000


settings = Settings()
