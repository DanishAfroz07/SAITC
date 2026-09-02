"""Formats de-duplicated citations from retrieved chunks, in first-seen
(i.e. relevance) order.
"""
from app.models import Citation, RetrievedChunk


def build_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    seen: dict[str, Citation] = {}
    for retrieved in chunks:
        metadata = retrieved.chunk.metadata
        if metadata.document_id not in seen:
            seen[metadata.document_id] = Citation(
                document_id=metadata.document_id,
                title=metadata.title,
                effective_date=metadata.effective_date,
            )
    return list(seen.values())
