"""Loads the corpus manifest and enumerates source PDF files.

Single responsibility: know how to find documents and their declared
metadata. Nothing here reads PDF content - that's parser.py's job.
"""
import json
from datetime import date
from pathlib import Path

from app.models import DocumentMetadata


def load_manifest(manifest_path: Path) -> dict[str, DocumentMetadata]:
    """Returns manifest entries keyed by file name.

    The manifest is the source of truth for metadata (per the corpus README:
    "you may parse it from the PDF or read it from this file"). We read it
    from here; parser.py's in-PDF header check exists only to catch authoring
    mistakes, never to override this.
    """
    raw = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    entries: dict[str, DocumentMetadata] = {}
    for doc in raw["documents"]:
        entries[doc["file"]] = DocumentMetadata(
            document_id=doc["document_id"],
            title=doc["title"],
            version=doc["version"],
            effective_date=date.fromisoformat(doc["effective_date"]),
            owner=doc["owner"],
            classification=doc["classification"],
            supersedes=doc.get("supersedes"),
            file_name=doc["file"],
        )
    return entries


def iter_pdf_files(documents_dir: Path) -> list[Path]:
    """Yields every PDF in the documents directory, sorted for determinism."""
    return sorted(Path(documents_dir).glob("*.pdf"))
