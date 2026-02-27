from __future__ import annotations

from app.research.pdf_extract import extract_pdf_text


def test_extract_pdf_text_handles_empty_bytes() -> None:
    result = extract_pdf_text(b"")
    assert result["text"] == ""
    assert result["method"] == "pypdf"
    assert result["warnings"]


def test_extract_pdf_text_handles_invalid_pdf_bytes() -> None:
    result = extract_pdf_text(b"not-a-real-pdf")
    assert result["text"] == ""
    assert result["method"] == "pypdf"
    assert result["warnings"]
