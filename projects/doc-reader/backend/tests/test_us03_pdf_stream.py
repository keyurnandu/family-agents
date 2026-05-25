"""
US-03-01 — Backend tests: GET /documents/{id}/file
TDD: These tests MUST FAIL until Sam implements the endpoint.
"""
import io
import os
import uuid
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# ── Import the app ────────────────────────────────────────────────────────────
from app.main import app

client = TestClient(app)

# ── Fixtures ──────────────────────────────────────────────────────────────────

FAKE_PDF_BYTES = b"%PDF-1.4 fake pdf content for testing"
FAKE_FILENAME  = "quarterly_report.pdf"


def _make_doc(doc_id: str, filename: str = FAKE_FILENAME, file_path: str = None):
    """Return a minimal mock document ORM object."""
    doc = MagicMock()
    doc.id       = doc_id
    doc.filename = filename
    doc.file_path = file_path or f"uploads/{doc_id}.pdf"
    return doc


# ── 200 — Happy path ──────────────────────────────────────────────────────────

class TestPdfStreamSuccess:
    def test_returns_200_for_valid_document(self, tmp_path):
        doc_id  = str(uuid.uuid4())
        pdf_file = tmp_path / f"{doc_id}.pdf"
        pdf_file.write_bytes(FAKE_PDF_BYTES)
        doc = _make_doc(doc_id, file_path=str(pdf_file))
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=doc):
            response = client.get(f"/documents/{doc_id}/file")
        assert response.status_code == 200

    def test_content_type_is_application_pdf(self, tmp_path):
        doc_id  = str(uuid.uuid4())
        pdf_file = tmp_path / f"{doc_id}.pdf"
        pdf_file.write_bytes(FAKE_PDF_BYTES)
        doc = _make_doc(doc_id, file_path=str(pdf_file))
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=doc):
            response = client.get(f"/documents/{doc_id}/file")
        assert "application/pdf" in response.headers.get("content-type", "")

    def test_content_disposition_is_inline_with_filename(self, tmp_path):
        doc_id  = str(uuid.uuid4())
        pdf_file = tmp_path / f"{doc_id}.pdf"
        pdf_file.write_bytes(FAKE_PDF_BYTES)
        doc = _make_doc(doc_id, filename="my_report.pdf", file_path=str(pdf_file))
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=doc):
            response = client.get(f"/documents/{doc_id}/file")
        disposition = response.headers.get("content-disposition", "")
        assert disposition == 'inline; filename="my_report.pdf"'

    def test_response_body_contains_pdf_bytes(self, tmp_path):
        doc_id  = str(uuid.uuid4())
        pdf_file = tmp_path / f"{doc_id}.pdf"
        pdf_file.write_bytes(FAKE_PDF_BYTES)
        doc = _make_doc(doc_id, file_path=str(pdf_file))
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=doc):
            response = client.get(f"/documents/{doc_id}/file")
        assert response.content == FAKE_PDF_BYTES

    def test_content_length_matches_file_size(self, tmp_path):
        doc_id  = str(uuid.uuid4())
        pdf_file = tmp_path / f"{doc_id}.pdf"
        pdf_file.write_bytes(FAKE_PDF_BYTES)
        doc = _make_doc(doc_id, file_path=str(pdf_file))
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=doc):
            response = client.get(f"/documents/{doc_id}/file")
        assert int(response.headers.get("content-length", 0)) == len(FAKE_PDF_BYTES)

    def test_accept_ranges_header_present(self, tmp_path):
        doc_id  = str(uuid.uuid4())
        pdf_file = tmp_path / f"{doc_id}.pdf"
        pdf_file.write_bytes(FAKE_PDF_BYTES)
        doc = _make_doc(doc_id, file_path=str(pdf_file))
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=doc):
            response = client.get(f"/documents/{doc_id}/file")
        assert response.headers.get("accept-ranges") == "bytes"

    def test_uses_file_response_not_in_memory(self, tmp_path):
        doc_id  = str(uuid.uuid4())
        pdf_file = tmp_path / f"{doc_id}.pdf"
        pdf_file.write_bytes(FAKE_PDF_BYTES)
        doc = _make_doc(doc_id, file_path=str(pdf_file))
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=doc):
            response = client.get(f"/documents/{doc_id}/file")
        has_length = "content-length" in response.headers
        has_transfer = "transfer-encoding" in response.headers
        assert has_length or has_transfer

    def test_streaming_response_is_binary(self, tmp_path):
        doc_id  = str(uuid.uuid4())
        pdf_file = tmp_path / f"{doc_id}.pdf"
        pdf_file.write_bytes(FAKE_PDF_BYTES)
        doc = _make_doc(doc_id, file_path=str(pdf_file))
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=doc):
            response = client.get(f"/documents/{doc_id}/file")
        assert isinstance(response.content, bytes)


# ── 404 — Document not in database ───────────────────────────────────────────

class TestPdfStreamDocumentNotFound:
    def test_returns_404_when_document_missing_from_db(self):
        doc_id = str(uuid.uuid4())
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=None):
            response = client.get(f"/documents/{doc_id}/file")
        assert response.status_code == 404

    def test_error_body_has_document_not_found_detail(self):
        doc_id = str(uuid.uuid4())
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=None):
            response = client.get(f"/documents/{doc_id}/file")
        body = response.json()
        assert body["detail"] == "Document not found"
        assert body["code"]   == "DOCUMENT_NOT_FOUND"

    def test_invalid_uuid_returns_404(self):
        response = client.get("/documents/not-a-real-id/file")
        assert response.status_code == 404


# ── 404 — File deleted from disk ─────────────────────────────────────────────

class TestPdfStreamFileNotFound:
    def test_returns_404_when_file_missing_from_disk(self):
        doc_id = str(uuid.uuid4())
        doc    = _make_doc(doc_id, file_path="/tmp/does_not_exist_ever.pdf")
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=doc):
            response = client.get(f"/documents/{doc_id}/file")
        assert response.status_code == 404

    def test_error_body_has_file_not_found_detail(self):
        doc_id = str(uuid.uuid4())
        doc    = _make_doc(doc_id, file_path="/tmp/does_not_exist_ever.pdf")
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=doc):
            response = client.get(f"/documents/{doc_id}/file")
        body = response.json()
        assert body["detail"] == "File not found on disk"
        assert body["code"]   == "FILE_NOT_FOUND"


# ── 206 — HTTP Range requests ─────────────────────────────────────────────────

class TestPdfStreamRangeRequests:
    def test_returns_206_for_range_request(self, tmp_path):
        doc_id  = str(uuid.uuid4())
        pdf_file = tmp_path / f"{doc_id}.pdf"
        pdf_file.write_bytes(FAKE_PDF_BYTES)
        doc = _make_doc(doc_id, file_path=str(pdf_file))
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=doc):
            response = client.get(f"/documents/{doc_id}/file", headers={"Range": "bytes=0-9"})
        assert response.status_code == 206

    def test_range_response_body_is_correct_slice(self, tmp_path):
        doc_id  = str(uuid.uuid4())
        pdf_file = tmp_path / f"{doc_id}.pdf"
        pdf_file.write_bytes(FAKE_PDF_BYTES)
        doc = _make_doc(doc_id, file_path=str(pdf_file))
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=doc):
            response = client.get(f"/documents/{doc_id}/file", headers={"Range": "bytes=0-9"})
        assert response.content == FAKE_PDF_BYTES[0:10]

    def test_invalid_range_returns_416(self, tmp_path):
        doc_id  = str(uuid.uuid4())
        pdf_file = tmp_path / f"{doc_id}.pdf"
        pdf_file.write_bytes(FAKE_PDF_BYTES)
        doc = _make_doc(doc_id, file_path=str(pdf_file))
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=doc):
            response = client.get(f"/documents/{doc_id}/file", headers={"Range": "bytes=99999-999999"})
        assert response.status_code == 416

    def test_content_range_header_in_206_response(self, tmp_path):
        doc_id  = str(uuid.uuid4())
        pdf_file = tmp_path / f"{doc_id}.pdf"
        pdf_file.write_bytes(FAKE_PDF_BYTES)
        doc = _make_doc(doc_id, file_path=str(pdf_file))
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=doc):
            response = client.get(f"/documents/{doc_id}/file", headers={"Range": "bytes=0-9"})
        assert "content-range" in response.headers

    # ── Tests 18-22: RFC 7233 compliance ─────────────────────────────────────

    def test_content_range_header_format_rfc7233(self, tmp_path):
        """Test 18 — Content-Range value must be exactly 'bytes start-end/total'."""
        doc_id  = str(uuid.uuid4())
        pdf_file = tmp_path / f"{doc_id}.pdf"
        pdf_file.write_bytes(FAKE_PDF_BYTES)
        doc = _make_doc(doc_id, file_path=str(pdf_file))
        total = len(FAKE_PDF_BYTES)
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=doc):
            response = client.get(f"/documents/{doc_id}/file", headers={"Range": "bytes=0-9"})
        assert response.status_code == 206
        content_range = response.headers.get("content-range", "")
        assert content_range == f"bytes 0-9/{total}"

    def test_content_length_equals_slice_size(self, tmp_path):
        """Test 19 — Content-Length must equal the number of bytes in the requested slice."""
        doc_id  = str(uuid.uuid4())
        pdf_file = tmp_path / f"{doc_id}.pdf"
        pdf_file.write_bytes(FAKE_PDF_BYTES)
        doc = _make_doc(doc_id, file_path=str(pdf_file))
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=doc):
            response = client.get(f"/documents/{doc_id}/file", headers={"Range": "bytes=0-9"})
        assert response.status_code == 206
        assert int(response.headers.get("content-length", -1)) == 10

    def test_suffix_range_returns_last_n_bytes(self, tmp_path):
        """Test 20 — bytes=-8 must return the last 8 bytes with correct Content-Range."""
        doc_id  = str(uuid.uuid4())
        pdf_file = tmp_path / f"{doc_id}.pdf"
        pdf_file.write_bytes(FAKE_PDF_BYTES)
        doc = _make_doc(doc_id, file_path=str(pdf_file))
        total = len(FAKE_PDF_BYTES)
        expected_start = total - 8
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=doc):
            response = client.get(f"/documents/{doc_id}/file", headers={"Range": "bytes=-8"})
        assert response.status_code == 206
        assert response.content == FAKE_PDF_BYTES[-8:]
        content_range = response.headers.get("content-range", "")
        assert content_range == f"bytes {expected_start}-{total - 1}/{total}"

    def test_open_ended_range_returns_from_offset_to_end(self, tmp_path):
        """Test 21 — bytes=5- must return all bytes from offset 5 to EOF."""
        doc_id  = str(uuid.uuid4())
        pdf_file = tmp_path / f"{doc_id}.pdf"
        pdf_file.write_bytes(FAKE_PDF_BYTES)
        doc = _make_doc(doc_id, file_path=str(pdf_file))
        total = len(FAKE_PDF_BYTES)
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=doc):
            response = client.get(f"/documents/{doc_id}/file", headers={"Range": "bytes=5-"})
        assert response.status_code == 206
        assert response.content == FAKE_PDF_BYTES[5:]
        content_range = response.headers.get("content-range", "")
        assert content_range == f"bytes 5-{total - 1}/{total}"

    def test_416_response_includes_content_range_with_total(self, tmp_path):
        """Test 22 — 416 response must include Content-Range: bytes */<total> per RFC 7233 s4.4."""
        doc_id  = str(uuid.uuid4())
        pdf_file = tmp_path / f"{doc_id}.pdf"
        pdf_file.write_bytes(FAKE_PDF_BYTES)
        doc = _make_doc(doc_id, file_path=str(pdf_file))
        total = len(FAKE_PDF_BYTES)
        with patch("app.routers.documents.get_db"), \
             patch("app.routers.documents.DocumentService.get_document", return_value=doc):
            response = client.get(f"/documents/{doc_id}/file", headers={"Range": "bytes=99999-999999"})
        assert response.status_code == 416
        content_range = response.headers.get("content-range", "")
        assert content_range == f"bytes */{total}"