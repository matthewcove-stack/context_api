from __future__ import annotations

from io import BytesIO
from typing import Any, Dict

from pypdf import PdfReader


def extract_pdf_text(content_bytes: bytes) -> Dict[str, Any]:
    if not content_bytes:
        return {"text": "", "method": "pypdf", "warnings": ["empty_pdf_bytes"]}
    try:
        reader = PdfReader(BytesIO(content_bytes))
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text.strip())
        return {"text": "\n\n".join(pages).strip(), "method": "pypdf", "warnings": []}
    except Exception as exc:  # pragma: no cover - defensive runtime path
        return {"text": "", "method": "pypdf", "warnings": [f"pdf_extract_failed:{exc}"]}
