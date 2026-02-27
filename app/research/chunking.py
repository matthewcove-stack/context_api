from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List

from app.research.ids import compute_chunk_id


def _paragraphs(text: str) -> List[str]:
    chunks = re.split(r"\n{2,}", text)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def chunk_document(
    *,
    document_id: str,
    text: str,
    max_chars: int = 1200,
) -> List[Dict[str, Any]]:
    paragraphs = _paragraphs(text)
    if not paragraphs:
        return []

    buckets: List[str] = []
    current: List[str] = []
    current_size = 0
    for paragraph in paragraphs:
        next_size = current_size + len(paragraph) + (2 if current else 0)
        if current and next_size > max_chars:
            buckets.append("\n\n".join(current))
            current = [paragraph]
            current_size = len(paragraph)
            continue
        current.append(paragraph)
        current_size = next_size
    if current:
        buckets.append("\n\n".join(current))

    chunks: List[Dict[str, Any]] = []
    for idx, content in enumerate(buckets, start=1):
        chunk_id = compute_chunk_id(document_id=document_id, ordinal=idx, content=content)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        chunks.append(
            {
                "chunk_id": chunk_id,
                "ordinal": idx,
                "content": content,
                "content_hash": content_hash,
            }
        )
    return chunks
