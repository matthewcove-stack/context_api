from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.storage.db import replace_intel_sections, upsert_intel_articles


def _default_fixture_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "intel"


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.endswith("Z"):
            cleaned = f"{cleaned[:-1]}+00:00"
        try:
            return datetime.fromisoformat(cleaned)
        except ValueError:
            return None
    return None


def _require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Fixture missing required string field: {field}")
    return value.strip()


def _ensure_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def load_fixture_bundle(bundle: str, fixture_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    if bundle != "default":
        raise ValueError(f"Unknown fixture_bundle: {bundle}")
    fixture_dir = fixture_dir or _default_fixture_dir()
    if not fixture_dir.exists():
        raise FileNotFoundError(f"Fixture directory not found: {fixture_dir}")
    files = sorted(fixture_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No fixture files found in {fixture_dir}")
    fixtures: List[Dict[str, Any]] = []
    for path in files:
        with path.open("r", encoding="utf-8") as handle:
            fixtures.append(json.load(handle))
    return fixtures


def _normalize_fixture(fixture: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    metadata = fixture.get("metadata") or {}
    article_id = _require_str(metadata.get("article_id") or fixture.get("article_id"), "metadata.article_id")
    url = _require_str(metadata.get("url") or fixture.get("url"), "metadata.url")
    title = _require_str(metadata.get("title") or fixture.get("title"), "metadata.title")
    publisher = metadata.get("publisher") or fixture.get("publisher")
    author = metadata.get("author") or fixture.get("author")
    published_at = _parse_datetime(metadata.get("published_at") or fixture.get("published_at"))
    topics = _ensure_list(metadata.get("topics") or fixture.get("topics"))
    summary = fixture.get("summary") or ""
    signals = _ensure_list(fixture.get("signals"))
    outline = _ensure_list(fixture.get("outline"))
    outbound_links = _ensure_list(fixture.get("outbound_links"))
    sections = _ensure_list(fixture.get("sections"))

    article_row = {
        "article_id": article_id,
        "url": url,
        "title": title,
        "publisher": publisher,
        "author": author,
        "published_at": published_at,
        "topics": topics,
        "summary": summary,
        "signals": signals,
        "outline": outline,
        "outbound_links": outbound_links,
    }
    return article_row, sections


def ingest_intel_fixtures(
    engine: Any,
    *,
    bundle: str = "default",
    fixture_dir: Optional[Path] = None,
) -> List[str]:
    fixtures = load_fixture_bundle(bundle, fixture_dir)
    article_rows: List[Dict[str, Any]] = []
    sections_by_article: Dict[str, List[Dict[str, Any]]] = {}
    for fixture in fixtures:
        article_row, sections = _normalize_fixture(fixture)
        article_id = article_row["article_id"]
        article_rows.append(article_row)
        sections_by_article[article_id] = sections

    ingested_ids = upsert_intel_articles(engine, items=article_rows)
    for article_id in ingested_ids:
        replace_intel_sections(
            engine,
            article_id=article_id,
            sections=sections_by_article.get(article_id, []),
        )
    return ingested_ids
