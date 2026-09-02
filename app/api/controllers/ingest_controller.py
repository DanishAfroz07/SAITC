"""POST /ingest - full corpus re-ingestion. IngestionPipeline is the
service here; this controller only translates request/response."""
from fastapi import APIRouter

from app.api.schemas import IngestResponse
from app.wiring import build_ingestion_pipeline

router = APIRouter()


@router.post("/ingest", response_model=IngestResponse)
def ingest() -> IngestResponse:
    """Re-ingests every PDF in data/documents/, wiping and rebuilding the
    vector store. Use /documents/upload to add a single new PDF instead."""
    report = build_ingestion_pipeline().run()
    return IngestResponse(
        documents_processed=report.documents_processed,
        chunks_created=report.chunks_created,
        table_chunks=report.table_chunks,
        elapsed_seconds=report.elapsed_seconds,
    )
