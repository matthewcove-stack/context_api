from __future__ import annotations

import hashlib

from app.storage.db import canonicalize_url


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def compute_source_id(*, topic_key: str, kind: str, base_url: str) -> str:
    canonical_base = canonicalize_url(base_url)
    seed = f"{topic_key.strip().lower()}|{kind.strip().lower()}|{canonical_base}"
    return f"src_{_sha256(seed)}"


def compute_document_id(
    *,
    source_id: str,
    canonical_url: str,
    external_id: str | None = None,
) -> str:
    source = source_id.strip()
    url = canonicalize_url(canonical_url)
    external = (external_id or "").strip().lower()
    if url:
        # Canonical URL is primary dedupe identity for web content.
        seed = f"{source}|{url}"
    else:
        seed = f"{source}|{external}"
    return f"doc_{_sha256(seed)}"


def compute_chunk_id(*, document_id: str, ordinal: int, content: str) -> str:
    normalized_content = " ".join(content.split())
    content_hash = _sha256(normalized_content)
    seed = f"{document_id.strip()}|{int(ordinal)}|{content_hash}"
    return f"chk_{_sha256(seed)}"
