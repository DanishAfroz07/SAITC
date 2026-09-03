"""Calls the LLM and builds the final cited Answer."""
from app.generation.llm import ChatClient
from app.generation.prompts import build_messages
from app.models import Answer, Citation, EvidenceAssessment, RetrievedChunk


def _build_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    """De-duplicated citations, one per document_id, in relevance order."""
    seen: dict[str, Citation] = {}
    for retrieved in chunks:
        m = retrieved.chunk.metadata
        if m.document_id not in seen:
            seen[m.document_id] = Citation(document_id=m.document_id, title=m.title, effective_date=m.effective_date)
    return list(seen.values())


class AnswerGenerator:
    def __init__(self, chat_client: ChatClient) -> None:
        self._chat_client = chat_client

    def generate(self, query: str, assessment: EvidenceAssessment) -> Answer:
        messages = build_messages(query, assessment)
        text = self._chat_client.complete(messages)
        citations = _build_citations(assessment.chunks)
        return Answer(
            text=text,
            citations=citations,
            outcome=assessment.outcome,
            retrieval_confidence=assessment.retrieval_confidence,
        )
