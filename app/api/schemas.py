"""Pydantic request/response contracts for the HTTP API. Kept separate from
app.models on purpose: this is the API's own boundary and can change shape
(versioning, renamed fields) independently of the internal domain model.
"""
from datetime import date

from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str


class CitationResponse(BaseModel):
    document_id: str
    title: str
    effective_date: date


class QueryResponse(BaseModel):
    answer: str
    outcome: str
    citations: list[CitationResponse]


class IngestResponse(BaseModel):
    documents_processed: int
    chunks_created: int
    table_chunks: int
    elapsed_seconds: float


class HealthResponse(BaseModel):
    status: str
