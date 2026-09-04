"""Classifies what retrieval found into one outcome - sufficient /
insufficient / conflicting / ambiguous - so the response strategy is a
testable decision, not implicit LLM behaviour.

Two deliberately simple heuristics (limitations, see README):
1. Conflict detection uses a hand-maintained registry of document pairs
   known to disagree (KNOWN_CONFLICT_PAIRS) - not automated contradiction
   detection.
2. Ambiguity detection is a within-document section-diversity proxy, not
   semantic reasoning about the question.
"""
import re
from dataclasses import dataclass

from app.models import EvidenceAssessment, EvidenceOutcome, RetrievalConfidence, RetrievedChunk

_TOP_LEVEL_SECTION_RE = re.compile(r"^\s*(\d+)")
_DOCUMENT_HEADER_SECTION = "Document header"


def _top_level_section(section: str) -> str:
    """The leading section number, e.g. '2' from '2. File and storage
    limits'. Section numbers are only meaningful within their own document -
    HR-PRO-011's "1. Purpose" has nothing to do with HR-POL-002's "4.1
    Purpose and scope" just because both start with a digit - so this is
    only ever compared per-document, never across documents (see
    _looks_ambiguous)."""
    match = _TOP_LEVEL_SECTION_RE.match(section)
    return match.group(1) if match else section

KNOWN_CONFLICT_PAIRS: list[frozenset[str]] = [
    frozenset({"LEG-TRM-004", "SUP-FAQ-001"}),
]


class EvidenceAnalyzer:
    def __init__(
        self,
        similarity_threshold: float,
        ambiguity_min_sections: int = 2,
        ambiguity_window: int = 4,
        ambiguity_max_query_words: int = 5,
        conflict_confidence_threshold: float = 0.70,
        high_confidence_score: float = 0.78,
        medium_confidence_score: float = 0.68,
    ) -> None:
        self._similarity_threshold = similarity_threshold
        self._ambiguity_min_sections = ambiguity_min_sections
        self._ambiguity_window = ambiguity_window
        # Evidence-based: a document's internal section-diversity alone
        # can't tell "genuinely different kinds of thing" (Q8: rate limit
        # vs storage limit) apart from "different facets of one coherent
        # topic" (Q12: FIN-POL-007's booking/accommodation/claiming-costs
        # sections, all "travel booking rules") - both look identical in
        # shape (same document, several distinct top-level sections). What
        # actually differs is the QUESTION: Q8 is 4 words with no qualifying
        # noun, Q12 is 11 words that already name exactly what's wanted. A
        # short, underspecified question is what's actually ambiguous; a
        # long one that already names its topics isn't, no matter how the
        # retrieved sections are numbered. See README.md.
        self._ambiguity_max_query_words = ambiguity_max_query_words
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

    def assess(self, query: str, chunks: list[RetrievedChunk]) -> EvidenceAssessment:
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

        if self._looks_ambiguous(query, non_superseded):
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

    def _looks_ambiguous(self, query: str, chunks: list[RetrievedChunk]) -> bool:
        # A question that already names what it wants (Q12: "expense
        # approval thresholds and travel booking rules") isn't ambiguous no
        # matter how its retrieved sections are numbered - see __init__.
        if len(query.split()) > self._ambiguity_max_query_words:
            return False

        top = chunks[: self._ambiguity_window]
        if len(top) < self._ambiguity_min_sections:
            return False

        # Grouped PER DOCUMENT on purpose (see _top_level_section docstring):
        # Q1's supporting cross-references (HR-PRO-011, HR-POL-005 alongside
        # the primary HR-POL-002) used to falsely count as "diverse topics"
        # under a global section-string count, when they're really just
        # multiple documents supporting one coherent answer. What genuinely
        # signals ambiguity (Q8: "rate limit" vs "storage limit") is ONE
        # document contributing several distinct top-level sections.
        # "Document header" is excluded - it's the same boilerplate
        # metadata block on every document, never a genuine second topic,
        # and it was co-occurring with real content chunks from the same
        # document often enough to falsely trigger this (assignment Q4).
        sections_by_doc: dict[str, set[str]] = {}
        for c in top:
            section = _top_level_section(c.chunk.section)
            if section == _DOCUMENT_HEADER_SECTION:
                continue
            sections_by_doc.setdefault(c.chunk.document_id, set()).add(section)
        max_distinct_sections = max((len(s) for s in sections_by_doc.values()), default=0)
        # No score-closeness check here on purpose: once a single document
        # genuinely offers 2+ different kinds of thing (rate limit vs
        # storage limit), a real score gap between them doesn't mean the
        # lower-scoring one isn't a valid reading of the question - a score
        # gap of 0.66/0.62 was enough to wrongly disqualify Q8 under the
        # margin check this used to have. See README.md.
        return max_distinct_sections >= self._ambiguity_min_sections
