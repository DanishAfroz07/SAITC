"""Extracts text from PDFs and cross-checks it against manifest metadata.

The corpus is text-based (per the corpus README), so plain text extraction
via PyMuPDF is sufficient - no OCR needed.
"""
import logging
import re
from pathlib import Path

import pymupdf

from app.models import DocumentMetadata

logger = logging.getLogger(__name__)

_HEADER_PATTERN = re.compile(
    r"Document ID:?\s*(?P<document_id>\S+).*?"
    r"Version:?\s*(?P<version>\S+)",
    re.DOTALL,
)


def extract_text(pdf_path: Path) -> str:
    """Extracts and concatenates text from every page of a text-based PDF."""
    with pymupdf.open(pdf_path) as doc:
        return "\n".join(page.get_text() for page in doc)


def cross_check_metadata(text: str, manifest_entry: DocumentMetadata) -> None:
    """Logs a warning if the in-PDF header block disagrees with the manifest.

    The manifest always wins (see loader.load_manifest) - this exists only to
    surface authoring mistakes during ingestion, not to change behaviour.
    """
    match = _HEADER_PATTERN.search(text)
    if not match:
        logger.warning(
            "No metadata header found in %s; relying on manifest only.",
            manifest_entry.file_name,
        )
        return
    if match.group("document_id") != manifest_entry.document_id:
        logger.warning(
            "Document ID mismatch in %s: PDF header says %s, manifest says %s",
            manifest_entry.file_name,
            match.group("document_id"),
            manifest_entry.document_id,
        )
    if match.group("version") != manifest_entry.version:
        logger.warning(
            "Version mismatch in %s: PDF header says %s, manifest says %s",
            manifest_entry.file_name,
            match.group("version"),
            manifest_entry.version,
        )
