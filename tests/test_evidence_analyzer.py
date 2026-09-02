from datetime import date

from app.models import Chunk, DocumentMetadata, EvidenceOutcome, RetrievedChunk
from app.retrieval.evidence_analyzer import EvidenceAnalyzer


def _meta(doc_id: str) -> DocumentMetadata:
    return DocumentMetadata(
        document_id=doc_id,
        title="Title",
        version="1.0",
        effective_date=date(2026, 1, 1),
        owner="Owner",
        classification="Internal",
        supersedes=None,
        file_name=f"{doc_id}.pdf",
    )


def _rc(doc_id: str, section: str, score: float) -> RetrievedChunk:
    chunk = Chunk(
        chunk_id=f"{doc_id}-{section}",
        document_id=doc_id,
        section=section,
        text="text",
        is_table=False,
        metadata=_meta(doc_id),
    )
    return RetrievedChunk(chunk=chunk, score=score)


def test_low_score_is_insufficient():
    analyzer = EvidenceAnalyzer(similarity_threshold=0.5, ambiguity_margin=0.05)
    result = analyzer.assess([_rc("A", "1. X", 0.2)])
    assert result.outcome == EvidenceOutcome.INSUFFICIENT


def test_known_conflict_pair_is_flagged():
    analyzer = EvidenceAnalyzer(similarity_threshold=0.3, ambiguity_margin=0.05)
    chunks = [_rc("LEG-TRM-004", "2. Refund windows by plan", 0.8), _rc("SUP-FAQ-001", "Plans and billing", 0.75)]
    result = analyzer.assess(chunks)
    assert result.outcome == EvidenceOutcome.CONFLICTING
    assert len(result.chunks) == 2  # both sides retained, never collapsed


def test_clear_single_topic_match_is_sufficient():
    analyzer = EvidenceAnalyzer(similarity_threshold=0.3, ambiguity_margin=0.05)
    chunks = [_rc("HR-POL-002", "4.2 Annual leave entitlement", 0.9), _rc("HR-POL-002", "4.2 Annual leave entitlement", 0.85)]
    result = analyzer.assess(chunks)
    assert result.outcome == EvidenceOutcome.SUFFICIENT


def test_scattered_close_scores_across_sections_is_ambiguous():
    analyzer = EvidenceAnalyzer(similarity_threshold=0.3, ambiguity_margin=0.1)
    chunks = [
        _rc("PROD-DOC-009", "1. API rate limits", 0.60),
        _rc("PROD-DOC-009", "2. File and storage limits", 0.58),
        _rc("PROD-DOC-009", "3. Request and payload limits", 0.57),
    ]
    result = analyzer.assess(chunks)
    assert result.outcome == EvidenceOutcome.AMBIGUOUS


def test_superseded_chunks_are_excluded_from_ambiguity_check():
    chunks = [
        _rc("A", "1. X", 0.9),
        _rc("B", "2. Y", 0.85),
    ]
    chunks[1].chunk.superseded = True
    analyzer = EvidenceAnalyzer(similarity_threshold=0.3, ambiguity_margin=0.5)
    result = analyzer.assess(chunks)
    assert result.outcome == EvidenceOutcome.SUFFICIENT
