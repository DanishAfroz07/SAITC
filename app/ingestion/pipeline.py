"""Orchestrates one ingestion run: load manifest -> extract -> chunk -> embed
-> store. This is the only place that sequences those steps; each step's own
module knows nothing about the others.
"""
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from app.ingestion.chunker import SectionChunker
from app.ingestion.loader import iter_pdf_files, load_manifest
from app.ingestion.parser import cross_check_metadata, extract_text
from app.retrieval.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)


@dataclass
class IngestionReport:
    documents_processed: int
    chunks_created: int
    table_chunks: int
    elapsed_seconds: float


class IngestionPipeline:
    def __init__(
        self,
        documents_dir: Path,
        manifest_path: Path,
        chunker: SectionChunker,
        vector_store: ChromaVectorStore,
    ) -> None:
        self._documents_dir = documents_dir
        self._manifest_path = manifest_path
        self._chunker = chunker
        self._vector_store = vector_store

    def run(self) -> IngestionReport:
        start = time.perf_counter()
        manifest = load_manifest(self._manifest_path)
        self._vector_store.reset()

        documents_processed = 0
        chunks_created = 0
        table_chunks = 0

        for pdf_path in iter_pdf_files(self._documents_dir):
            metadata = manifest.get(pdf_path.name)
            if metadata is None:
                logger.warning("Skipping %s: not present in manifest.", pdf_path.name)
                continue

            text = extract_text(pdf_path)
            cross_check_metadata(text, metadata)

            chunks = self._chunker.chunk(text, metadata)
            self._vector_store.add_chunks(chunks)

            documents_processed += 1
            chunks_created += len(chunks)
            table_chunks += sum(1 for c in chunks if c.is_table)

        report = IngestionReport(
            documents_processed=documents_processed,
            chunks_created=chunks_created,
            table_chunks=table_chunks,
            elapsed_seconds=time.perf_counter() - start,
        )
        logger.info(
            "Ingested %d documents into %d chunks (%d table chunks) in %.2fs",
            report.documents_processed,
            report.chunks_created,
            report.table_chunks,
            report.elapsed_seconds,
        )
        return report
