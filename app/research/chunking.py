from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List

from app.research.ids import compute_chunk_id


_HEADING_RE = re.compile(r"^(#{1,6}\s+.+|[A-Z][A-Z0-9 /:&-]{4,}|[0-9]+(\.[0-9]+)*\s+.+)$")


def _paragraphs(text: str) -> List[str]:
    paragraphs = re.split(r"\n{2,}", text)
    return [paragraph.strip() for paragraph in paragraphs if paragraph.strip()]


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_heading(paragraph: str) -> bool:
    compact = paragraph.strip()
    if not compact or len(compact) > 120:
        return False
    return bool(_HEADING_RE.match(compact))


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", _normalize_whitespace(text))
    return [part.strip() for part in parts if part.strip()]


def _carryover_overlap(text: str, *, target_chars: int) -> str:
    sentences = _split_sentences(text)
    if len(sentences) <= 1:
        return _normalize_whitespace(text)[-target_chars:].strip()
    carried: List[str] = []
    current = 0
    for sentence in reversed(sentences):
        extra = len(sentence) + (1 if carried else 0)
        if carried and current + extra > target_chars:
            break
        carried.insert(0, sentence)
        current += extra
    return " ".join(carried).strip()


def _split_oversized_paragraph(paragraph: str, *, max_chars: int) -> List[str]:
    compact = paragraph.strip()
    if len(compact) <= max_chars:
        return [compact]
    sentences = _split_sentences(compact)
    if len(sentences) <= 1:
        slices = [compact[idx : idx + max_chars].strip() for idx in range(0, len(compact), max_chars)]
        return [slice_text for slice_text in slices if slice_text]
    pieces: List[str] = []
    current: List[str] = []
    current_size = 0
    for sentence in sentences:
        next_size = current_size + len(sentence) + (1 if current else 0)
        if current and next_size > max_chars:
            pieces.append(" ".join(current).strip())
            current = [sentence]
            current_size = len(sentence)
            continue
        if not current and len(sentence) > max_chars:
            pieces.extend(_split_oversized_paragraph(sentence, max_chars=max_chars))
            current = []
            current_size = 0
            continue
        current.append(sentence)
        current_size = next_size
    if current:
        pieces.append(" ".join(current).strip())
    return [piece for piece in pieces if piece]


def chunk_document(
    *,
    document_id: str,
    text: str,
    max_chars: int = 1200,
    overlap_chars: int = 160,
) -> List[Dict[str, Any]]:
    paragraphs = _paragraphs(text)
    if not paragraphs:
        return []

    buckets: List[Dict[str, Any]] = []
    current: List[str] = []
    current_size = 0
    heading_path: List[str] = []

    def flush_bucket() -> None:
        nonlocal current, current_size
        if not current:
            return
        content = "\n\n".join(current).strip()
        if not content:
            current = []
            current_size = 0
            return
        buckets.append(
            {
                "content": content,
                "heading_path": heading_path[-3:],
                "tags": [part.lower() for part in heading_path[-3:]],
            }
        )
        overlap = _carryover_overlap(content, target_chars=max(0, overlap_chars))
        current = [overlap] if overlap else []
        current_size = len(overlap)

    for paragraph in paragraphs:
        compact = paragraph.strip()
        if _is_heading(compact):
            if current:
                flush_bucket()
            heading_path = (heading_path + [compact])[-4:]
            continue
        for piece in _split_oversized_paragraph(compact, max_chars=max_chars):
            next_size = current_size + len(piece) + (2 if current else 0)
            if current and next_size > max_chars:
                flush_bucket()
                next_size = current_size + len(piece) + (2 if current else 0)
            current.append(piece)
            current_size = next_size
    flush_bucket()

    chunks: List[Dict[str, Any]] = []
    for idx, bucket in enumerate(buckets, start=1):
        content = str(bucket["content"])
        chunk_id = compute_chunk_id(document_id=document_id, ordinal=idx, content=content)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        chunks.append(
            {
                "chunk_id": chunk_id,
                "ordinal": idx,
                "content": content,
                "content_hash": content_hash,
                "chunk_meta": {
                    "heading_path": list(bucket.get("heading_path") or []),
                    "tags": list(bucket.get("tags") or []),
                },
            }
        )
    return chunks
