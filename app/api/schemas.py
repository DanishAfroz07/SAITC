"""Pydantic request/response models for the HTTP API (separate from the
internal domain models in app.models)."""
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
    citations: list[CitationResponse]


class IngestResponse(BaseModel):
    documents_processed: int
    chunks_created: int
    table_chunks: int
    elapsed_seconds: float


class DocumentUploadResponse(BaseModel):
    document_id: str
    file_name: str
    chunks_created: int
    table_chunks: int
    elapsed_seconds: float
    replaced_previous: bool


class DocumentSummary(BaseModel):
    document_id: str
    title: str
    version: str
    effective_date: date
    owner: str
    classification: str
    supersedes: str | None
    file_name: str


class DocumentDeleteResponse(BaseModel):
    document_id: str
    deleted: bool


class HealthResponse(BaseModel):
    status: str
