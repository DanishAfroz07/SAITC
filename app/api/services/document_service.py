"""Business logic for the document upload/list/delete endpoints - the one
part of the API that isn't already a pipeline (RagPipeline handles /query,
IngestionPipeline handles /ingest; those ARE the "service" layer for those
two routes, so there's no separate wrapper for them - see README).

Takes plain values (bytes, strings), not UploadFile/HTTPException, so it's
usable and testable outside of FastAPI.
"""
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.config import settings
from app.ingestion.loader import list_manifest_entries, remove_manifest_entry, upsert_manifest_entry
from app.models import DocumentMetadata
from app.wiring import build_ingestion_pipeline, get_vector_store


@dataclass
class UploadResult:
    document_id: str
    file_name: str
    chunks_created: int
    table_chunks: int
    elapsed_seconds: float
    replaced_previous: bool


class DocumentService:
    def list_documents(self) -> list[DocumentMetadata]:
        return list_manifest_entries(settings.manifest_path)

    def upload_document(
        self,
        file_name: str,
        file_bytes: bytes,
        document_id: str | None,
        title: str | None,
        version: str,
        effective_date: date | None,
        owner: str,
        classification: str,
        supersedes: str | None,
    ) -> UploadResult:
        resolved_id = document_id or Path(file_name).stem
        metadata = DocumentMetadata(
            document_id=resolved_id,
            title=title or resolved_id,
            version=version,
            effective_date=effective_date or date.today(),
            owner=owner,
            classification=classification,
            supersedes=supersedes,
            file_name=file_name,
        )

        settings.documents_dir.mkdir(parents=True, exist_ok=True)
        destination = settings.documents_dir / metadata.file_name
        destination.write_bytes(file_bytes)

        previous = upsert_manifest_entry(settings.manifest_path, metadata)
        if previous is not None and previous.file_name != metadata.file_name:
            (settings.documents_dir / previous.file_name).unlink(missing_ok=True)

        report = build_ingestion_pipeline().run_single(destination, metadata)

        return UploadResult(
            document_id=metadata.document_id,
            file_name=metadata.file_name,
            chunks_created=report.chunks_created,
            table_chunks=report.table_chunks,
            elapsed_seconds=report.elapsed_seconds,
            replaced_previous=previous is not None,
        )

    def delete_document(self, document_id: str) -> bool:
        """Returns False if no such document existed."""
        removed = remove_manifest_entry(settings.manifest_path, document_id)
        if removed is None:
            return False
        get_vector_store().delete_by_document_id(document_id)
        (settings.documents_dir / removed.file_name).unlink(missing_ok=True)
        return True
