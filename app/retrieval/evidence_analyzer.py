"""Decides what retrieval actually found, before generation decides how to
respond. This is the single place that turns "here are some chunks" into one
of four outcomes - sufficient / insufficient / conflicting / ambiguous - so
that behaviour is a testable, inspectable decision rather than something left
implicit in how the LLM happens to react to a prompt.

Two heuristics are deliberately simple, and both limitations are called out
in the README rather than hidden:

1. Conflicting-document detection uses a fixed registry of document pairs
   known (by manual corpus review) to describe the same fact differently
   without one superseding the other - e.g. LEG-TRM-004 (Legal, "this
   schedule prevails") vs SUP-FAQ-001 (Customer Success FAQ, overdue for
   review) on the Atlas Enterprise refund window. A production system with
   an open-ended, changing corpus would need automated contradiction
   detection (e.g. pairwise NLI or an LLM-as-judge pass over co-retrieved
   chunks), not a hand-maintained list.

2. Ambiguity detection is a score-spread + section-diversity heuristic: if
   several top chunks come from clearly different sections with no chunk
   standing out on score, the question probably has more than one plausible
   referent (e.g. "what is the limit?" against a document with five kinds of
   limit). This is a proxy, not semantic reasoning about what "ambiguous"
   means - it will under- or over-trigger on corpora this hasn't been tuned
   against.
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
        score_spread = top[0].score - top[-1].score
        return score_spread < self._ambiguity_margin
