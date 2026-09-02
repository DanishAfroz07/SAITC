import json
from datetime import date
from pathlib import Path

import pytest

from app.ingestion.loader import (
    list_manifest_entries,
    load_manifest,
    remove_manifest_entry,
    upsert_manifest_entry,
)
from app.models import DocumentMetadata

_BASE_MANIFEST = {
    "corpus": "test",
    "purpose": "test",
    "as_of_date": "2026-08-27",
    "note": "test",
    "documents": [
        {
            "file": "existing.pdf",
            "document_id": "EXISTING-1",
            "title": "Existing",
            "version": "1.0",
            "effective_date": "2026-01-01",
            "owner": "Owner",
            "classification": "Internal",
            "supersedes": None,
        }
    ],
}


@pytest.fixture
def manifest_path(tmp_path: Path) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_BASE_MANIFEST), encoding="utf-8")
    return path


def test_upsert_adds_a_new_entry(manifest_path: Path):
    metadata = DocumentMetadata(
        document_id="NEW-1",
        title="New Doc",
        version="1.0",
        effective_date=date(2026, 8, 1),
        owner="Uploaded",
        classification="Internal",
        supersedes=None,
        file_name="new.pdf",
    )
    previous = upsert_manifest_entry(manifest_path, metadata)
    assert previous is None

    entries = load_manifest(manifest_path)
    assert "new.pdf" in entries
    assert "existing.pdf" in entries  # untouched


def test_upsert_replaces_existing_entry_with_same_document_id(manifest_path: Path):
    updated = DocumentMetadata(
        document_id="EXISTING-1",
        title="Existing v2",
        version="2.0",
        effective_date=date(2026, 8, 1),
        owner="Owner",
        classification="Internal",
        supersedes="EXISTING-1 v1.0",
        file_name="existing-v2.pdf",  # re-uploaded under a new file name
    )
    previous = upsert_manifest_entry(manifest_path, updated)

    assert previous is not None
    assert previous.file_name == "existing.pdf"

    entries = list_manifest_entries(manifest_path)
    assert len(entries) == 1  # old entry replaced, not duplicated
    assert entries[0].file_name == "existing-v2.pdf"
    assert entries[0].version == "2.0"


def test_remove_existing_entry_returns_it(manifest_path: Path):
    removed = remove_manifest_entry(manifest_path, "EXISTING-1")
    assert removed is not None
    assert removed.file_name == "existing.pdf"
    assert list_manifest_entries(manifest_path) == []


def test_remove_missing_entry_returns_none_and_leaves_manifest_untouched(manifest_path: Path):
    removed = remove_manifest_entry(manifest_path, "NOT-REAL")
    assert removed is None
    assert len(list_manifest_entries(manifest_path)) == 1
