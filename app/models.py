"""Domain types shared across layers (plain dataclasses, not tied to FastAPI)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


@dataclass(frozen=True)
class DocumentMetadata:
    document_id: str
    title: str
    version: str
    effective_date: date
    owner: str
    classification: str
    supersedes: str | None
    file_name: str


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    section: str
    text: str
    is_table: bool
    metadata: DocumentMetadata
    superseded: bool = False


@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float


class EvidenceOutcome(str, Enum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"
    CONFLICTING = "conflicting"
    AMBIGUOUS = "ambiguous"


@dataclass
class EvidenceAssessment:
    outcome: EvidenceOutcome
    chunks: list[RetrievedChunk]
    reason: str


@dataclass(frozen=True)
class Citation:
    document_id: str
    title: str
    effective_date: date


@dataclass
class Answer:
    text: str
    citations: list[Citation]
    outcome: EvidenceOutcome


class InputVerdict(str, Enum):
    SAFE = "safe"
    INJECTION_ATTEMPT = "injection_attempt"
    OUT_OF_SCOPE = "out_of_scope"
