from __future__ import annotations

import argparse
import json
import os
from typing import Any

from sqlalchemy import text

from app.research.hygiene import detect_junk_document
from app.storage.db import create_db_engine, set_research_document_suppressed


def _iter_candidates(engine: Any, *, topic_key: str) -> list[dict[str, Any]]:
    sql = """
        SELECT
            d.document_id,
            d.canonical_url,
            coalesce(d.title, '') AS title,
            coalesce(d.extracted_text, '') AS extracted_text,
            coalesce(d.summary_short, '') AS summary_short,
            d.fetch_meta,
            d.suppressed,
            d.suppression_reason,
            d.status
        FROM research_documents d
        JOIN research_sources s
          ON s.source_id = d.source_id
        WHERE s.topic_key = :topic_key
        ORDER BY coalesce(d.published_at, d.discovered_at) DESC NULLS LAST, d.updated_at DESC
    """
    with engine.begin() as conn:
        rows = conn.execute(text(sql), {"topic_key": topic_key}).mappings().all()
    return [dict(row) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description="Bulk suppress existing junk research documents.")
    parser.add_argument("--topic-key", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    engine = create_db_engine(database_url)
    rows = _iter_candidates(engine, topic_key=args.topic_key.strip().lower())

    matches: list[dict[str, Any]] = []
    for row in rows[: max(args.limit, 1)]:
        fetch_meta = row.get("fetch_meta") or {}
        reason = detect_junk_document(
            url=str(row.get("canonical_url") or ""),
            title=str(row.get("title") or ""),
            extracted_text=str(row.get("extracted_text") or ""),
            item_summary=str(row.get("summary_short") or ""),
            fetch_status=int((fetch_meta or {}).get("http_status") or 0),
            fetch_fallback=str((fetch_meta or {}).get("fallback") or ""),
        )
        if not reason:
            continue
        matches.append(
            {
                "document_id": str(row.get("document_id") or ""),
                "url": str(row.get("canonical_url") or ""),
                "title": str(row.get("title") or ""),
                "reason": reason,
                "already_suppressed": bool(row.get("suppressed") or False),
                "status": str(row.get("status") or ""),
            }
        )

    applied = 0
    if args.apply:
        for item in matches:
            if item["already_suppressed"]:
                continue
            if set_research_document_suppressed(
                engine,
                document_id=item["document_id"],
                suppressed=True,
                reason=item["reason"],
            ):
                applied += 1

    print(
        json.dumps(
            {
                "topic_key": args.topic_key,
                "candidates": len(matches),
                "applied": applied,
                "items": matches,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
