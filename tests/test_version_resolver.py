from datetime import date

from app.models import Chunk, DocumentMetadata, RetrievedChunk
from app.retrieval.version_resolver import VersionResolver

OLD = DocumentMetadata(
    document_id="SALES-PL-2025",
    title="Price List",
    version="1.0",
    effective_date=date(2025, 1, 1),
    owner="Commercial",
    classification="External",
    supersedes=None,
    file_name="old.pdf",
)
NEW = DocumentMetadata(
    document_id="SALES-PL-2026",
    title="Price List",
    version="2.0",
    effective_date=date(2026, 3, 1),
    owner="Commercial",
    classification="External",
    supersedes="SALES-PL-2025 v1.0",
    file_name="new.pdf",
)


def _retrieved(metadata: DocumentMetadata) -> RetrievedChunk:
    chunk = Chunk(
        chunk_id="x",
        document_id=metadata.document_id,
        section="s",
        text="t",
        is_table=False,
        metadata=metadata,
    )
    return RetrievedChunk(chunk=chunk, score=0.9)


def test_older_document_is_tagged_superseded_once_successor_is_effective():
    resolver = VersionResolver([OLD, NEW])
    chunks = [_retrieved(OLD), _retrieved(NEW)]
    resolver.tag_superseded(chunks, as_of_date=date(2026, 8, 27))
    assert chunks[0].chunk.superseded is True
    assert chunks[1].chunk.superseded is False


def test_successor_not_yet_effective_leaves_old_document_current():
    resolver = VersionResolver([OLD, NEW])
    chunks = [_retrieved(OLD)]
    resolver.tag_superseded(chunks, as_of_date=date(2025, 6, 1))
    assert chunks[0].chunk.superseded is False


def test_same_id_version_bump_with_no_separate_document_is_ignored():
    # HR-POL-002 v4.1 "supersedes HR-POL-002 v3.6" - same document_id, and no
    # separate v3.6 document exists in the corpus, so there is nothing to tag.
    current = DocumentMetadata(
        document_id="HR-POL-002",
        title="Leave Policy",
        version="4.1",
        effective_date=date(2026, 1, 1),
        owner="People Operations",
        classification="Internal",
        supersedes="HR-POL-002 v3.6",
        file_name="hr.pdf",
    )
    resolver = VersionResolver([current])
    chunks = [_retrieved(current)]
    resolver.tag_superseded(chunks, as_of_date=date(2026, 8, 27))
    assert chunks[0].chunk.superseded is False
