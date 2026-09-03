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


class RetrievalConfidence(str, Enum):
    """How strongly the retrieved evidence matched the question - NOT a
    probability that the generated answer is factually correct. Only
    meaningful when the system actually commits to one answer (SUFFICIENT);
    every other outcome is NOT_APPLICABLE by definition, since the whole
    point of those outcomes is that the system isn't confidently picking one
    answer. See README for a real example where this is HIGH and the answer
    is still wrong - retrieval finding the right passage and the model
    reasoning about it correctly are two different things."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class EvidenceAssessment:
    outcome: EvidenceOutcome
    chunks: list[RetrievedChunk]
    reason: str
    retrieval_confidence: RetrievalConfidence = RetrievalConfidence.NOT_APPLICABLE


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
    retrieval_confidence: RetrievalConfidence = RetrievalConfidence.NOT_APPLICABLE


class InputVerdict(str, Enum):
    SAFE = "safe"
    INJECTION_ATTEMPT = "injection_attempt"
    OUT_OF_SCOPE = "out_of_scope"
