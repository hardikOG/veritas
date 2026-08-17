"""POST /documents, GET /documents/:id — the ingestion pipeline's HTTP surface."""

import hashlib
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import get_db
from core.constants import EXTENSION_TO_MIME, SUPPORTED_MIME_TYPES, TASK_INGEST_DOCUMENT
from core.logging import get_logger
from models import Chunk, Document
from worker.celery_app import celery_app

logger = get_logger("veritas.api")
router = APIRouter()


def _resolve_mime(upload: UploadFile) -> str:
    """Determine a supported mime type for an upload, falling back to its extension.

    Purpose: browsers/clients don't always send an accurate Content-Type for .md
        files in particular (often `application/octet-stream` or blank); the file
        extension is a reliable enough fallback for the three supported formats.
    Inputs: upload — the incoming UploadFile.
    Outputs: one of SUPPORTED_MIME_TYPES.
    Complexity: O(1).
    Failure cases: raises HTTPException(422) if neither the declared content type nor
        the extension is recognized.
    """
    if upload.content_type in SUPPORTED_MIME_TYPES:
        return upload.content_type
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix in EXTENSION_TO_MIME:
        return EXTENSION_TO_MIME[suffix]
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"unsupported file type (must be txt/md/pdf): {upload.content_type}",
    )


@router.post("/documents", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(file: UploadFile, db: Session = Depends(get_db)) -> dict[str, str]:
    """Upload a document, storing it and enqueueing async ingestion.

    Purpose: the entry point to Phase 1's pipeline. Idempotent on file content — a
        byte-identical re-upload returns the existing document instead of enqueueing
        a duplicate ingestion, whatever that document's current status.
    Inputs: file — multipart upload, txt/md/pdf (by content-type, falling back to
        extension); db — injected session.
    Outputs: {"id", "status"}, HTTP 202. status reflects the existing or newly
        created document's current status ('queued' for a genuinely new upload).
    Complexity: O(file size) to hash and store.
    Failure cases: HTTPException(422) for an unsupported file type.
    """
    mime = _resolve_mime(file)
    content = await file.read()
    checksum = hashlib.sha256(content).hexdigest()

    existing = db.execute(
        select(Document).where(Document.checksum == checksum)
    ).scalar_one_or_none()
    if existing is not None:
        return {"id": str(existing.id), "status": existing.status}

    document = Document(
        filename=file.filename or checksum,
        mime=mime,
        content=content,
        status="queued",
        checksum=checksum,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # Dispatched by task name, not by importing the task function, so the api
    # process never needs ingestion/embedding's heavy ML dependencies installed —
    # see worker/celery_app.py.
    celery_app.send_task(TASK_INGEST_DOCUMENT, args=[str(document.id)])
    logger.info(
        "document enqueued for ingestion",
        extra={"extra_fields": {"document_id": str(document.id), "filename": document.filename}},
    )

    return {"id": str(document.id), "status": document.status}


@router.get("/documents/{document_id}")
async def get_document(document_id: UUID, db: Session = Depends(get_db)) -> dict[str, object]:
    """Report a document's ingestion status and chunk count.

    Purpose: lets a client poll ingestion progress after POST /documents.
    Inputs: document_id — path param; db — injected session.
    Outputs: {"id", "filename", "status", "chunk_count"}.
    Complexity: O(1) plus a COUNT query over chunks.
    Failure cases: HTTPException(404) if no such document exists.
    """
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    chunk_count = db.execute(
        select(func.count()).select_from(Chunk).where(Chunk.document_id == document.id)
    ).scalar_one()
    return {
        "id": str(document.id),
        "filename": document.filename,
        "status": document.status,
        "chunk_count": chunk_count,
    }
