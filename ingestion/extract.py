"""Plain-text extraction per supported document mime type."""

from pathlib import Path

from pypdf import PdfReader

from core.constants import SUPPORTED_MIME_TYPES

__all__ = ["SUPPORTED_MIME_TYPES", "extract_text"]


def extract_text(storage_path: str, mime: str) -> str:
    """Extract plain text from a stored document, given its mime type.

    Purpose: normalizes txt/md/pdf into a single plain-text string for the chunker,
        so nothing downstream needs to know about file formats.
    Inputs: storage_path — filesystem path to the stored upload; mime — one of
        SUPPORTED_MIME_TYPES (the API layer rejects anything else before enqueueing).
    Outputs: the document's full extracted text.
    Complexity: O(file size); PDF extraction is O(pages).
    Failure cases: raises ValueError for an unsupported mime type (should be
        unreachable given the API's upload validation — a defensive check, not the
        primary guard); raises FileNotFoundError/OSError if storage_path is missing;
        raises pypdf's own exceptions on a corrupt PDF.
    """
    path = Path(storage_path)
    if mime == "application/pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if mime in ("text/plain", "text/markdown"):
        return path.read_text(encoding="utf-8", errors="replace")
    raise ValueError(f"unsupported mime type: {mime}")
