"""Classifies what retrieval found into one outcome - sufficient /
insufficient / conflicting / ambiguous - so the response strategy is a
testable decision, not implicit LLM behaviour.

Two deliberately simple heuristics (limitations, see README):
1. Conflict detection uses a hand-maintained registry of document pairs
   known to disagree (KNOWN_CONFLICT_PAIRS) - not automated contradiction
   detection.
2. Ambiguity detection is a score-spread + section-diversity proxy, not
   semantic reasoning about the question.
"""
from dataclasses import dataclass

from app.models import EvidenceAssessment, EvidenceOutcome, RetrievedChunk

KNOWN_CONFLICT_PAIRS: list[frozenset[str]] = [
    frozenset({"LEG-TRM-004", "SUP-FAQ-001"}),
]


class EvidenceAnalyzer:
    def __init__(
        self,
        similarity_threshold: float,
        ambiguity_margin: float,
        ambiguity_min_sections: int = 3,
        ambiguity_window: int = 4,
    ) -> None:
        self._similarity_threshold = similarity_threshold
        self._ambiguity_margin = ambiguity_margin
        self._ambiguity_min_sections = ambiguity_min_sections
        self._ambiguity_window = ambiguity_window

    def assess(self, chunks: list[RetrievedChunk]) -> EvidenceAssessment:
        relevant = [c for c in chunks if c.score >= self._similarity_threshold]
        if not relevant:
            return EvidenceAssessment(
                outcome=EvidenceOutcome.INSUFFICIENT,
                chunks=[],
                reason="No retrieved chunk cleared the similarity threshold.",
            )

        # Prefer current chunks for topic/ambiguity checks, but fall back to
        # everything relevant if every hit happens to be superseded - a stale
        # answer is still better than none.
        current = [c for c in relevant if not c.chunk.superseded] or relevant

        doc_ids = {c.chunk.document_id for c in current}
        if any(pair.issubset(doc_ids) for pair in KNOWN_CONFLICT_PAIRS):
            return EvidenceAssessment(
                outcome=EvidenceOutcome.CONFLICTING,
                chunks=relevant,
                reason="Retrieved chunks span a document pair known to conflict.",
            )

        if self._looks_ambiguous(current):
            return EvidenceAssessment(
                outcome=EvidenceOutcome.AMBIGUOUS,
                chunks=current,
                reason="Top matches span distinct sections with no clear best match.",
            )

        return EvidenceAssessment(
            outcome=EvidenceOutcome.SUFFICIENT,
            chunks=current,
            reason="A clear best match was found.",
        )

    def _looks_ambiguous(self, chunks: list[RetrievedChunk]) -> bool:
        top = chunks[: self._ambiguity_window]
        if len(top) < self._ambiguity_min_sections:
            return False
        sections = {c.chunk.section for c in top}
        if len(sections) < self._ambiguity_min_sections:
            return False
        # min/max rather than positional top[0]/top[-1]: chunks may have been
        # reordered by a reranker, so the list isn't guaranteed sorted by score.
        scores = [c.score for c in top]
        return (max(scores) - min(scores)) < self._ambiguity_margin
