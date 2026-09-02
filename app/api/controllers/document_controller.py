"""GET/POST/DELETE /documents - manage documents beyond the fixed corpus.
Business logic lives in DocumentService; this controller only handles HTTP
concerns (parsing the upload, raising HTTPException for bad input)."""
from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.schemas import DocumentDeleteResponse, DocumentSummary, DocumentUploadResponse
from app.api.services.document_service import DocumentService

router = APIRouter()
_service = DocumentService()


@router.get("/documents", response_model=list[DocumentSummary])
def list_documents() -> list[DocumentSummary]:
    return [
        DocumentSummary(
            document_id=e.document_id,
            title=e.title,
            version=e.version,
            effective_date=e.effective_date,
            owner=e.owner,
            classification=e.classification,
            supersedes=e.supersedes,
            file_name=e.file_name,
        )
        for e in _service.list_documents()
    ]


@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(..., description="The PDF to ingest"),
    document_id: str | None = Form(None, description="Defaults to the file name without extension"),
    title: str | None = Form(None, description="Defaults to document_id"),
    version: str = Form("1.0"),
    effective_date: date | None = Form(None, description="Defaults to today"),
    owner: str = Form("Uploaded"),
    classification: str = Form("Internal"),
    supersedes: str | None = Form(None),
) -> DocumentUploadResponse:
    """Saves the PDF, upserts its manifest entry, and ingests it. Metadata
    fields are optional; set them explicitly if this document needs to
    participate in conflict/version resolution."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf files are supported.")

    result = _service.upload_document(
        file_name=file.filename,
        file_bytes=await file.read(),
        document_id=document_id,
        title=title,
        version=version,
        effective_date=effective_date,
        owner=owner,
        classification=classification,
        supersedes=supersedes,
    )
    return DocumentUploadResponse(
        document_id=result.document_id,
        file_name=result.file_name,
        chunks_created=result.chunks_created,
        table_chunks=result.table_chunks,
        elapsed_seconds=result.elapsed_seconds,
        replaced_previous=result.replaced_previous,
    )


@router.delete("/documents/{document_id}", response_model=DocumentDeleteResponse)
def delete_document(document_id: str) -> DocumentDeleteResponse:
    if not _service.delete_document(document_id):
        raise HTTPException(status_code=404, detail=f"No document with id '{document_id}'.")
    return DocumentDeleteResponse(document_id=document_id, deleted=True)
