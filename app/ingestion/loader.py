"""Reads and updates corpus_manifest.json (document metadata), and lists
PDF files on disk. Never reads PDF content - see parser.py for that.
"""
import json
from datetime import date
from pathlib import Path

from app.models import DocumentMetadata


def _entry_to_metadata(doc: dict) -> DocumentMetadata:
    return DocumentMetadata(
        document_id=doc["document_id"],
        title=doc["title"],
        version=doc["version"],
        effective_date=date.fromisoformat(doc["effective_date"]),
        owner=doc["owner"],
        classification=doc["classification"],
        supersedes=doc.get("supersedes"),
        file_name=doc["file"],
    )


def _metadata_to_entry(metadata: DocumentMetadata) -> dict:
    return {
        "file": metadata.file_name,
        "document_id": metadata.document_id,
        "title": metadata.title,
        "version": metadata.version,
        "effective_date": metadata.effective_date.isoformat(),
        "owner": metadata.owner,
        "classification": metadata.classification,
        "supersedes": metadata.supersedes,
    }


def _read_raw(manifest_path: Path) -> dict:
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))


def _write_raw(manifest_path: Path, raw: dict) -> None:
    Path(manifest_path).write_text(json.dumps(raw, indent=2), encoding="utf-8")


def load_manifest(manifest_path: Path) -> dict[str, DocumentMetadata]:
    """Manifest entries keyed by file name. This is the metadata source of
    truth (see README); parser.py's in-PDF header check only catches
    authoring mistakes, it never overrides this."""
    raw = _read_raw(manifest_path)
    return {doc["file"]: _entry_to_metadata(doc) for doc in raw["documents"]}


def list_manifest_entries(manifest_path: Path) -> list[DocumentMetadata]:
    """Manifest entries in file order - used by GET /documents."""
    raw = _read_raw(manifest_path)
    return [_entry_to_metadata(doc) for doc in raw["documents"]]


def upsert_manifest_entry(manifest_path: Path, metadata: DocumentMetadata) -> DocumentMetadata | None:
    """Adds or replaces the entry for metadata.document_id. Returns the
    entry it replaced, if any, so the caller can delete its old file."""
    raw = _read_raw(manifest_path)
    previous: DocumentMetadata | None = None
    kept = []
    for doc in raw["documents"]:
        if doc["document_id"] == metadata.document_id:
            previous = _entry_to_metadata(doc)
            continue
        kept.append(doc)
    kept.append(_metadata_to_entry(metadata))
    raw["documents"] = kept
    _write_raw(manifest_path, raw)
    return previous


def remove_manifest_entry(manifest_path: Path, document_id: str) -> DocumentMetadata | None:
    """Removes an entry by document_id. Returns it, or None if not found."""
    raw = _read_raw(manifest_path)
    removed: DocumentMetadata | None = None
    kept = []
    for doc in raw["documents"]:
        if doc["document_id"] == document_id:
            removed = _entry_to_metadata(doc)
            continue
        kept.append(doc)
    raw["documents"] = kept
    _write_raw(manifest_path, raw)
    return removed


def iter_pdf_files(documents_dir: Path) -> list[Path]:
    """Yields every PDF in the documents directory, sorted for determinism."""
    return sorted(Path(documents_dir).glob("*.pdf"))
