from __future__ import annotations

import argparse
import os
from typing import Any, Dict, List

from app.research.chunking import chunk_document
from app.research.enrichment import derive_evidence_relations, enrich_chunks, enrich_document
from app.storage.db import (
    create_db_engine,
    list_research_chunks_for_document,
    list_research_documents_for_enrichment_backfill,
    mark_research_document_enriched,
    replace_research_chunks,
    replace_research_document_insights,
    replace_research_evidence_relations,
)


def _normalize_domains(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    return []


def _prepare_chunks(*, document_id: str, extracted_text: str, stored_chunks: List[Dict[str, Any]], chunk_max_chars: int) -> List[Dict[str, Any]]:
    if stored_chunks:
        return enrich_chunks(stored_chunks)
    generated = chunk_document(
        document_id=document_id,
        text=extracted_text,
        max_chars=max(chunk_max_chars, 200),
    )
    return enrich_chunks(generated)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill reasoning metadata, evidence, and relations for research documents.")
    parser.add_argument("--topic-key", default="", help="Optional topic key filter.")
    parser.add_argument("--limit", type=int, default=250)
    parser.add_argument("--all", action="store_true", help="Process all matching documents, not just those missing reasoning fields.")
    parser.add_argument("--rechunk-missing", action="store_true", help="Persist generated chunks when a document has extracted text but no chunks.")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    engine = create_db_engine(database_url)
    chunk_max_chars = int(os.getenv("RESEARCH_CHUNK_MAX_CHARS", "1200"))
    rows = list_research_documents_for_enrichment_backfill(
        engine,
        topic_key=args.topic_key.strip().lower() or None,
        limit=max(args.limit, 1),
        only_missing_reasoning_fields=not args.all,
    )
    processed = 0
    failed = 0
    for row in rows:
        document_id = str(row.get("document_id") or "")
        extracted_text = str(row.get("extracted_text") or "").strip()
        if not document_id or not extracted_text:
            continue
        try:
            stored_chunks = list_research_chunks_for_document(engine, document_id=document_id)
            enriched_chunks = _prepare_chunks(
                document_id=document_id,
                extracted_text=extracted_text,
                stored_chunks=stored_chunks,
                chunk_max_chars=chunk_max_chars,
            )
            if args.rechunk_missing and enriched_chunks and not stored_chunks:
                replace_research_chunks(engine, document_id=document_id, chunks=enriched_chunks)
            enrichment, insights = enrich_document(
                canonical_url=str(row.get("canonical_url") or ""),
                source_name=str(row.get("source_name") or ""),
                source_class=str(row.get("source_class") or "external_primary"),
                default_decision_domains=_normalize_domains(row.get("default_decision_domains")),
                extracted_text=extracted_text,
                chunks=enriched_chunks,
                fetch_meta=dict(row.get("fetch_meta") or {}),
                extraction_meta=dict(row.get("extraction_meta") or {}),
                published_at=row.get("published_at"),
            )
            mark_research_document_enriched(
                engine,
                document_id=document_id,
                enrichment=enrichment,
            )
            insight_rows = replace_research_document_insights(
                engine,
                document_id=document_id,
                insights=insights,
            )
            replace_research_evidence_relations(
                engine,
                relations=derive_evidence_relations(insight_rows),
            )
            processed += 1
        except Exception as exc:
            failed += 1
            print({"document_id": document_id, "status": "failed", "error": str(exc)})
    print(
        {
            "topic_key": args.topic_key.strip().lower() or None,
            "requested_limit": max(args.limit, 1),
            "processed": processed,
            "failed": failed,
            "only_missing_reasoning_fields": not args.all,
            "rechunk_missing": bool(args.rechunk_missing),
        }
    )


if __name__ == "__main__":
    main()
