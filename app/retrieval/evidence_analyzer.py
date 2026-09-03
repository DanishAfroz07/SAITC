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

from app.models import EvidenceAssessment, EvidenceOutcome, RetrievalConfidence, RetrievedChunk

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
        conflict_confidence_threshold: float = 0.70,
        high_confidence_score: float = 0.78,
        medium_confidence_score: float = 0.68,
    ) -> None:
        self._similarity_threshold = similarity_threshold
        self._ambiguity_margin = ambiguity_margin
        self._ambiguity_min_sections = ambiguity_min_sections
        self._ambiguity_window = ambiguity_window
        # Calibrated against scores actually observed in live testing: clean,
        # correct single-topic matches (e.g. Q1, Q2) scored 0.73-0.79; weaker
        # supporting chunks in multi-document answers scored 0.65-0.72. These
        # are NOT confidence-in-correctness bands - see RetrievalConfidence's
        # docstring in app/models.py for why that distinction matters.
        self._high_confidence_score = high_confidence_score
        self._medium_confidence_score = medium_confidence_score
        # Evidence-based (see README.md): a genuine conflict pair
        # (LEG-TRM-004 + SUP-FAQ-001 for a refund question) scored 0.784 and
        # 0.763 live. An unrelated pricing question incidentally pulled in
        # LEG-TRM-004 at 0.664 (its refund table happens to mention "Atlas
        # Professional" as a row label) and, without this gate, that alone
        # was enough to falsely trigger CONFLICTING for a question that had
        # nothing to do with refunds. 0.70 separates the two cleanly.
        self._conflict_confidence_threshold = conflict_confidence_threshold

    def assess(self, chunks: list[RetrievedChunk]) -> EvidenceAssessment:
        relevant = [c for c in chunks if c.score >= self._similarity_threshold]
        if not relevant:
            return EvidenceAssessment(
                outcome=EvidenceOutcome.INSUFFICIENT,
                chunks=[],
                reason="No retrieved chunk cleared the similarity threshold.",
            )

        # non_superseded is used ONLY for the internal conflict/ambiguity
        # signals below - a stale document's presence shouldn't itself
        # trigger a false conflict or ambiguity reading. The chunks actually
        # forwarded to generation are always `relevant` (every chunk that
        # cleared the threshold, superseded or not): the prompt template
        # tags superseded chunks explicitly, and the model needs to SEE a
        # superseded price/term to explain why it no longer applies, not
        # just have it silently removed before it ever reaches generation.
        non_superseded = [c for c in relevant if not c.chunk.superseded] or relevant

        # A document counts toward the known-conflict-pair check only if its
        # BEST match is a genuinely confident one - see __init__ docstring.
        best_score_by_doc: dict[str, float] = {}
        for c in non_superseded:
            doc_id = c.chunk.document_id
            best_score_by_doc[doc_id] = max(best_score_by_doc.get(doc_id, 0.0), c.score)
        confident_doc_ids = {
            doc_id for doc_id, score in best_score_by_doc.items() if score >= self._conflict_confidence_threshold
        }
        if any(pair.issubset(confident_doc_ids) for pair in KNOWN_CONFLICT_PAIRS):
            return EvidenceAssessment(
                outcome=EvidenceOutcome.CONFLICTING,
                chunks=relevant,
                reason="Retrieved chunks span a document pair known to conflict.",
            )

        if self._looks_ambiguous(non_superseded):
            return EvidenceAssessment(
                outcome=EvidenceOutcome.AMBIGUOUS,
                chunks=relevant,
                reason="Top matches span distinct sections with no clear best match.",
            )

        return EvidenceAssessment(
            outcome=EvidenceOutcome.SUFFICIENT,
            chunks=relevant,
            reason="A clear best match was found.",
            retrieval_confidence=self._confidence_for(relevant),
        )

    def _confidence_for(self, chunks: list[RetrievedChunk]) -> RetrievalConfidence:
        """Only called for SUFFICIENT - every other outcome stays
        NOT_APPLICABLE (the dataclass default), since there's no single
        committed-to answer to rate the retrieval confidence of."""
        top_score = max(c.score for c in chunks)
        if top_score >= self._high_confidence_score:
            return RetrievalConfidence.HIGH
        if top_score >= self._medium_confidence_score:
            return RetrievalConfidence.MEDIUM
        return RetrievalConfidence.LOW

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
