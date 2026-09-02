"""HTTP surface over the same RagPipeline / IngestionPipeline the CLI uses.
Contains no business logic - only request/response translation - so the API
can never drift out of sync with what `python -m app.main chat` does.
"""
from fastapi import APIRouter, Depends

from app.api.schemas import (
    CitationResponse,
    HealthResponse,
    IngestResponse,
    QueryRequest,
    QueryResponse,
)
from app.pipeline.rag_pipeline import RagPipeline
from app.wiring import build_ingestion_pipeline, build_rag_pipeline

router = APIRouter()


def get_rag_pipeline() -> RagPipeline:
    return build_rag_pipeline()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, pipeline: RagPipeline = Depends(get_rag_pipeline)) -> QueryResponse:
    answer = pipeline.answer(request.question)
    return QueryResponse(
        answer=answer.text,
        outcome=answer.outcome.value,
        citations=[
            CitationResponse(
                document_id=c.document_id, title=c.title, effective_date=c.effective_date
            )
            for c in answer.citations
        ],
    )


@router.post("/ingest", response_model=IngestResponse)
def ingest() -> IngestResponse:
    report = build_ingestion_pipeline().run()
    return IngestResponse(
        documents_processed=report.documents_processed,
        chunks_created=report.chunks_created,
        table_chunks=report.table_chunks,
        elapsed_seconds=report.elapsed_seconds,
    )
