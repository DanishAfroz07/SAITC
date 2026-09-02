"""POST /query - ask the assistant a question. RagPipeline is the service
here; this controller only translates request/response."""
from fastapi import APIRouter, Depends

from app.api.schemas import CitationResponse, QueryRequest, QueryResponse
from app.rag_pipeline import RagPipeline
from app.wiring import build_rag_pipeline

router = APIRouter()


def get_rag_pipeline() -> RagPipeline:
    return build_rag_pipeline()


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, pipeline: RagPipeline = Depends(get_rag_pipeline)) -> QueryResponse:
    answer = pipeline.answer(request.question)
    return QueryResponse(
        answer=answer.text,
        outcome=answer.outcome.value,
        citations=[
            CitationResponse(document_id=c.document_id, title=c.title, effective_date=c.effective_date)
            for c in answer.citations
        ],
    )
