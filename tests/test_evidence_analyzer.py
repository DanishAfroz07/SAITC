from datetime import date

from app.models import Chunk, DocumentMetadata, EvidenceOutcome, RetrievalConfidence, RetrievedChunk
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


def test_low_confidence_conflict_pair_member_does_not_falsely_trigger_conflicting():
    # Regression test for a real bug (assignment Q4): an unrelated pricing
    # question incidentally retrieved LEG-TRM-004 (its refund table happens
    # to mention "Atlas Professional" as a row label) at a low, marginal
    # score, while the real conflict-pair partner SUP-FAQ-001 wasn't
    # retrieved with any real confidence either. That must not be enough to
    # trigger CONFLICTING - only a genuinely confident match on both members
    # of a known conflict pair should (see test_known_conflict_pair_is_flagged,
    # where both score 0.75+).
    chunks = [
        _rc("SALES-PL-2026", "1. Subscription plans and additional users", 0.74),
        _rc("SALES-PL-2025", "1. Subscription plans and additional users", 0.73),
        _rc("SUP-FAQ-001", "Q: What does Atlas Professional cost?", 0.71),
        _rc("LEG-TRM-004", "2. Refund windows by plan", 0.664),  # incidental, low-confidence
    ]
    analyzer = EvidenceAnalyzer(similarity_threshold=0.62, ambiguity_margin=0.05, conflict_confidence_threshold=0.70)
    result = analyzer.assess(chunks)
    assert result.outcome != EvidenceOutcome.CONFLICTING


def test_sufficient_high_score_gets_high_confidence():
    analyzer = EvidenceAnalyzer(
        similarity_threshold=0.3, ambiguity_margin=0.05, high_confidence_score=0.78, medium_confidence_score=0.68
    )
    result = analyzer.assess([_rc("HR-POL-002", "4.2 Annual leave entitlement", 0.9)])
    assert result.outcome == EvidenceOutcome.SUFFICIENT
    assert result.retrieval_confidence == RetrievalConfidence.HIGH


def test_sufficient_middling_score_gets_medium_confidence():
    analyzer = EvidenceAnalyzer(
        similarity_threshold=0.3, ambiguity_margin=0.05, high_confidence_score=0.78, medium_confidence_score=0.68
    )
    result = analyzer.assess([_rc("HR-POL-002", "4.2 Annual leave entitlement", 0.70)])
    assert result.retrieval_confidence == RetrievalConfidence.MEDIUM


def test_sufficient_low_score_gets_low_confidence():
    analyzer = EvidenceAnalyzer(
        similarity_threshold=0.3, ambiguity_margin=0.05, high_confidence_score=0.78, medium_confidence_score=0.68
    )
    result = analyzer.assess([_rc("HR-POL-002", "4.2 Annual leave entitlement", 0.5)])
    assert result.retrieval_confidence == RetrievalConfidence.LOW


def test_non_sufficient_outcomes_have_not_applicable_confidence():
    # INSUFFICIENT: nothing cleared the threshold at all.
    analyzer = EvidenceAnalyzer(similarity_threshold=0.5, ambiguity_margin=0.05)
    result = analyzer.assess([_rc("A", "1. X", 0.2)])
    assert result.outcome == EvidenceOutcome.INSUFFICIENT
    assert result.retrieval_confidence == RetrievalConfidence.NOT_APPLICABLE

    # CONFLICTING: a confidence number would contradict the point of this
    # outcome - the system isn't committing to one answer here.
    analyzer = EvidenceAnalyzer(similarity_threshold=0.3, ambiguity_margin=0.05)
    chunks = [_rc("LEG-TRM-004", "2. Refund windows by plan", 0.8), _rc("SUP-FAQ-001", "Plans and billing", 0.75)]
    result = analyzer.assess(chunks)
    assert result.outcome == EvidenceOutcome.CONFLICTING
    assert result.retrieval_confidence == RetrievalConfidence.NOT_APPLICABLE


def test_superseded_chunk_still_reaches_generation_in_sufficient_case():
    # Regression test for a real bug: a dated-supersession case (e.g.
    # SALES-PL-2025 -> SALES-PL-2026) must still show the model the OLD
    # value, tagged superseded, so it can explain the price/term changed -
    # not silently vanish before generation ever sees it (assignment Q4).
    old = _rc("SALES-PL-2025", "1. Subscription plans", 0.7)
    old.chunk.superseded = True
    new = _rc("SALES-PL-2026", "1. Subscription plans", 0.75)

    analyzer = EvidenceAnalyzer(similarity_threshold=0.3, ambiguity_margin=0.05)
    result = analyzer.assess([old, new])

    assert result.outcome == EvidenceOutcome.SUFFICIENT
    assert len(result.chunks) == 2
    doc_ids = {c.chunk.document_id for c in result.chunks}
    assert doc_ids == {"SALES-PL-2025", "SALES-PL-2026"}
