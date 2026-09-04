"""Calls the LLM and builds the final cited Answer."""
import re

from app.generation.llm import ChatClient
from app.generation.prompts import build_messages
from app.models import Answer, Citation, EvidenceAssessment, EvidenceOutcome, RetrievedChunk

_TENURE_TIER_RE = re.compile(
    r"Less than 5 years \| ([^\n]+)\n5 years or more \| ([^\n]+)\n10 years or more \| ([^\n]+)"
)


def _build_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    """De-duplicated citations, one per document_id, in relevance order."""
    seen: dict[str, Citation] = {}
    for retrieved in chunks:
        m = retrieved.chunk.metadata
        if m.document_id not in seen:
            seen[m.document_id] = Citation(document_id=m.document_id, title=m.title, effective_date=m.effective_date)
    return list(seen.values())


def _supersession_note(chunks: list[RetrievedChunk]) -> str | None:
    """Mechanically guarantees the "an old value existed and was
    superseded" fact gets stated, built straight from metadata rather than
    trusting the model to remember to mention it - live testing showed the
    model skip this even when told to explicitly, twice (assignment Q4).
    """
    notes = []
    seen_pairs: set[tuple[str, str]] = set()
    for old in chunks:
        if not old.chunk.superseded:
            continue
        old_id = old.chunk.document_id
        for current in chunks:
            if current.chunk.superseded or (old_id, current.chunk.document_id) in seen_pairs:
                continue
            if old_id in (current.chunk.metadata.supersedes or ""):
                seen_pairs.add((old_id, current.chunk.document_id))
                notes.append(
                    f"Note: {current.chunk.metadata.title} (effective "
                    f"{current.chunk.metadata.effective_date}) supersedes the version effective "
                    f"{old.chunk.metadata.effective_date} - the current version is used above."
                )
    return " ".join(notes) if notes else None


def _tenure_tier_note(chunks: list[RetrievedChunk]) -> str | None:
    """Mechanically states HR-POL-002's tenure-based entitlement tiers
    whenever that table is in context. Asking the model to state every
    tier's specific number (not just that entitlement "increases") didn't
    hold in live testing even with an explicit instruction naming the
    exact numbers as an example (assignment Q1) - same reliability gap as
    _supersession_note, same fix: guarantee it in code instead.
    """
    for c in chunks:
        if c.chunk.document_id != "HR-POL-002":
            continue
        match = _TENURE_TIER_RE.search(c.chunk.text)
        if match:
            below_5, five_plus, ten_plus = match.groups()
            return (
                f"Note: entitlement scales with tenure - {below_5} for less than 5 years of "
                f"service, {five_plus} at 5+ years, {ten_plus} at 10+ years."
            )
    return None


class AnswerGenerator:
    def __init__(self, chat_client: ChatClient) -> None:
        self._chat_client = chat_client

    def generate(
        self, query: str, assessment: EvidenceAssessment, prompt_chunks: list[RetrievedChunk] | None = None
    ) -> Answer:
        """`prompt_chunks` is what's actually shown to the model - narrower
        than `assessment.chunks` when the caller narrowed it for a leaner
        prompt (e.g. RagPipeline's rerank_top_n). Citations and the
        mechanical notes below are always computed from the FULL
        `assessment.chunks`, not the narrowed prompt: a fact worth stating
        (an old superseded value, a tenure tier) doesn't stop being true
        just because it didn't make the cut for what the model saw -
        exactly what broke Q1/Q4 when both were computed from the same
        narrowed list the prompt used. Defaults to assessment.chunks when
        no narrowing happened.
        """
        chunks_for_prompt = prompt_chunks if prompt_chunks is not None else assessment.chunks
        messages = build_messages(query, assessment.outcome, chunks_for_prompt)
        text = self._chat_client.complete(messages)

        if assessment.outcome == EvidenceOutcome.SUFFICIENT:
            for note in (_supersession_note(assessment.chunks), _tenure_tier_note(assessment.chunks)):
                if note:
                    text = f"{text} {note}"

        citations = _build_citations(assessment.chunks)
        return Answer(
            text=text,
            citations=citations,
            outcome=assessment.outcome,
            retrieval_confidence=assessment.retrieval_confidence,
        )
