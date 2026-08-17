"""Plain-text extraction per supported document mime type."""

import io

from pypdf import PdfReader

from core.constants import SUPPORTED_MIME_TYPES

__all__ = ["SUPPORTED_MIME_TYPES", "extract_text"]


def extract_text(content: bytes, mime: str) -> str:
    """Extract plain text from a document's raw bytes, given its mime type.

    Purpose: normalizes txt/md/pdf into a single plain-text string for the chunker,
        so nothing downstream needs to know about file formats.
    Inputs: content — the document's raw bytes (from Document.content, stored in
        Postgres rather than a local filesystem path — see
        docs/private/ARCHITECTURE_LEDGER.md's Phase 6 entry for why); mime — one of
        SUPPORTED_MIME_TYPES (the API layer rejects anything else before enqueueing).
    Outputs: the document's full extracted text.
    Complexity: O(content size); PDF extraction is O(pages).
    Failure cases: raises ValueError for an unsupported mime type (should be
        unreachable given the API's upload validation — a defensive check, not the
        primary guard); raises pypdf's own exceptions on a corrupt PDF.
    """
    if mime == "application/pdf":
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if mime in ("text/plain", "text/markdown"):
        return content.decode("utf-8", errors="replace")
    raise ValueError(f"unsupported mime type: {mime}")
