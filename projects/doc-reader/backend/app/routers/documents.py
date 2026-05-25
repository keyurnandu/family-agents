import os
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Document
from app.schemas import DocumentListResponse, DocumentResponse
from app.utils.file_storage import delete_file, save_upload, extract_page_count

MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_BYTES", 52428800))  # 50 MB default

router = APIRouter()


class DocumentService:
    @classmethod
    def get_document(cls, doc_id: str, db: Session):
        """Look up a document by string ID. Returns None if not found or ID is non-numeric."""
        try:
            int_id = int(doc_id)
        except (ValueError, TypeError):
            return None
        return db.query(Document).filter(Document.id == int_id).first()


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a PDF document. Enforces 50 MB size limit."""
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF files are accepted.",
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the 50 MB limit ({len(contents)} bytes received).",
        )

    stored_filename, file_path = save_upload(contents, file.filename)
    page_count = extract_page_count(file_path)

    doc = Document(
        filename=stored_filename,
        original_filename=file.filename,
        file_path=file_path,
        file_size=len(contents),
        page_count=page_count,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return doc


@router.get("/", response_model=DocumentListResponse)
def list_documents(db: Session = Depends(get_db)):
    """Return all uploaded documents, newest first."""
    docs = db.query(Document).order_by(Document.uploaded_at.desc()).all()
    return DocumentListResponse(documents=docs, total=len(docs))


def _parse_range_header(range_header: str, file_size: int):
    """
    Parse a Range header value (e.g. 'bytes=0-1023').
    Returns (start, end) as inclusive byte positions.
    Raises ValueError for syntactically or semantically invalid ranges.
    Returns None if the range unit is not 'bytes'.
    """
    if not range_header or not range_header.startswith("bytes="):
        return None
    range_spec = range_header[len("bytes="):]
    # Only handle single range (no multi-range support)
    if "," in range_spec:
        return None
    parts = range_spec.split("-")
    if len(parts) != 2:
        raise ValueError("Invalid range format")
    start_str, end_str = parts[0].strip(), parts[1].strip()
    if start_str == "" and end_str == "":
        raise ValueError("Invalid range: both start and end are empty")
    if start_str == "":
        # Suffix range: last N bytes
        suffix = int(end_str)
        start = max(0, file_size - suffix)
        end = file_size - 1
    elif end_str == "":
        start = int(start_str)
        end = file_size - 1
    else:
        start = int(start_str)
        end = int(end_str)
    if start > end:
        raise ValueError("Invalid range: start > end")
    if start >= file_size:
        raise ValueError("Range not satisfiable: start >= file_size")
    end = min(end, file_size - 1)
    return start, end


@router.get("/{doc_id}/file")
def serve_file(doc_id: str, request: Request, db: Session = Depends(get_db)):
    """Stream the PDF file for in-browser rendering, with HTTP Range request support."""
    doc = DocumentService.get_document(doc_id, db)
    if not doc:
        return JSONResponse(
            status_code=404,
            content={"detail": "Document not found", "code": "DOCUMENT_NOT_FOUND"},
        )
    if not os.path.exists(doc.file_path):
        return JSONResponse(
            status_code=404,
            content={"detail": "File not found on disk", "code": "FILE_NOT_FOUND"},
        )

    file_size = os.path.getsize(doc.file_path)
    range_header = request.headers.get("Range") or request.headers.get("range")

    if range_header:
        try:
            result = _parse_range_header(range_header, file_size)
        except ValueError:
            # RFC 7233 §4.4 — 416 with Content-Range: bytes */total
            return Response(
                status_code=416,
                content=b"Range Not Satisfiable",
                headers={"content-range": f"bytes */{file_size}"},
                media_type="text/plain",
            )

        if result is not None:
            start, end = result
            length = end - start + 1

            with open(doc.file_path, "rb") as f:
                f.seek(start)
                data = f.read(length)

            return Response(
                content=data,
                status_code=206,
                media_type="application/pdf",
                headers={
                    "content-range": f"bytes {start}-{end}/{file_size}",
                    "content-length": str(length),
                    "content-disposition": f'inline; filename="{doc.filename}"',
                    "accept-ranges": "bytes",
                },
            )
        # Unrecognised range unit — fall through to full response

    # Full file response — advertise range support on every response (RFC 7233 §2.3)
    return FileResponse(
        doc.file_path,
        media_type="application/pdf",
        headers={
            "content-disposition": f'inline; filename="{doc.filename}"',
            "accept-ranges": "bytes",
        },
    )


@router.get("/{doc_id}", response_model=DocumentResponse)
def get_document(doc_id: int, db: Session = Depends(get_db)):
    """Fetch a single document by ID."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    """Delete a document and its file from disk."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    delete_file(doc.file_path)
    db.delete(doc)
    db.commit()