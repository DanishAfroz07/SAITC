"""Resolves supersession chains across documents, using manifest metadata only.

This module answers exactly one question: "has this document been formally
superseded by a newer one, as of the as-of date?" (e.g. SALES-PL-2025 was
superseded by SALES-PL-2026 on 2026-03-01). It deliberately does NOT try to
adjudicate conflicts between two documents that do not supersede each other
(e.g. LEG-TRM-004 vs SUP-FAQ-001 on Enterprise refund windows) - that kind of
conflict is resolved by a precedence statement written into the document
text itself ("this schedule prevails"), not by comparing dates, so it belongs
to EvidenceAnalyzer instead.
"""
import re
from datetime import date

from app.models import DocumentMetadata, RetrievedChunk

_LEADING_DOCUMENT_ID_RE = re.compile(r"^([A-Z]+-[A-Z]+-\d+)")


def _extract_predecessor_id(supersedes: str | None) -> str | None:
    if not supersedes:
        return None
    match = _LEADING_DOCUMENT_ID_RE.match(supersedes.strip())
    return match.group(1) if match else None


class VersionResolver:
    """Builds a document_id -> successor map from the manifest, restricted to
    predecessors that are themselves present as separate documents in the
    corpus (a same-ID version bump like "HR-POL-002 v3.6" has no chunks of
    its own to tag, since only the current version was supplied)."""

    def __init__(self, manifest_entries: list[DocumentMetadata]) -> None:
        known_ids = {entry.document_id for entry in manifest_entries}
        self._superseded_by: dict[str, DocumentMetadata] = {}
        for entry in manifest_entries:
            predecessor_id = _extract_predecessor_id(entry.supersedes)
            if predecessor_id and predecessor_id != entry.document_id and predecessor_id in known_ids:
                self._superseded_by[predecessor_id] = entry

    def tag_superseded(self, chunks: list[RetrievedChunk], as_of_date: date) -> list[RetrievedChunk]:
        for retrieved in chunks:
            successor = self._superseded_by.get(retrieved.chunk.document_id)
            if successor is not None and successor.effective_date <= as_of_date:
                retrieved.chunk.superseded = True
        return chunks
