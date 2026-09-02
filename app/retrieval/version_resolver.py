"""Tags chunks as superseded once a formal successor document (per the
manifest's `supersedes` field) is effective as of the as-of date - e.g.
SALES-PL-2025 -> superseded once SALES-PL-2026 takes effect.

Only handles this kind of dated supersession. A conflict between two
documents that don't supersede each other (e.g. LEG-TRM-004 vs SUP-FAQ-001)
is resolved by a precedence statement in the text, not by dates - that's
EvidenceAnalyzer's job instead.
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
    """Builds a document_id -> successor map from the manifest. Ignores a
    same-ID version bump (e.g. "HR-POL-002 v3.6") since only the current
    version's chunks exist to tag."""

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
