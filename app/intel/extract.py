from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

try:
    from readability import Document
except Exception:  # pragma: no cover - optional dependency
    Document = None

try:
    import trafilatura
    from trafilatura import metadata as traf_metadata
except Exception:  # pragma: no cover - optional dependency
    trafilatura = None
    traf_metadata = None

DEFAULT_MAX_CHARS = 120_000


def _get_int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _trim_text(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip()


def _extract_with_trafilatura(html: str, url: str) -> Optional[Dict[str, Any]]:
    if not trafilatura:
        return None
    extracted = trafilatura.extract(html, url=url, include_comments=False, include_tables=False)
    if not extracted:
        return None
    title = None
    author = None
    published_at = None
    if traf_metadata:
        meta = traf_metadata.extract_metadata(html)
        if meta:
            title = meta.title
            author = meta.author
            if meta.date:
                published_at = meta.date
    return {
        "title": title,
        "author": author,
        "published_at": published_at,
        "text": extracted,
        "method": "trafilatura",
        "confidence": 0.7,
        "warnings": [],
    }


def _extract_with_bs4(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = soup.title.string.strip() if soup.title and soup.title.string else None
    text = soup.get_text(separator="\n")
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return {
        "title": title,
        "author": None,
        "published_at": None,
        "text": text,
        "method": "bs4",
        "confidence": 0.4,
        "warnings": ["fallback_extractor"],
    }


def _extract_with_readability(html: str) -> Optional[Dict[str, Any]]:
    if Document is None:
        return None
    doc = Document(html)
    content_html = doc.summary()
    soup = BeautifulSoup(content_html, "html.parser")
    text = soup.get_text(separator="\n")
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return {
        "title": doc.short_title(),
        "author": None,
        "published_at": None,
        "text": text,
        "method": "readability",
        "confidence": 0.5,
        "warnings": [],
    }


def extract_readable_text(html: str, url: str) -> Dict[str, Any]:
    max_chars = _get_int_env("INTEL_EXTRACT_MAX_CHARS", DEFAULT_MAX_CHARS)
    warnings = []
    result = _extract_with_trafilatura(html, url)
    if not result:
        result = _extract_with_readability(html)
    if not result:
        result = _extract_with_bs4(html)
    text = _trim_text(result.get("text") or "", max_chars)
    if len(result.get("text") or "") > max_chars:
        warnings.append("text_truncated")
    published_at = result.get("published_at")
    if isinstance(published_at, str):
        cleaned = published_at.strip()
        if cleaned.endswith("Z"):
            cleaned = f"{cleaned[:-1]}+00:00"
        try:
            published_at = datetime.fromisoformat(cleaned)
        except ValueError:
            published_at = None
    if not isinstance(published_at, datetime):
        published_at = None
    result.update(
        {
            "text": text,
            "published_at": published_at,
            "warnings": (result.get("warnings") or []) + warnings,
        }
    )
    return result
