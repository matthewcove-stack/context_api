from __future__ import annotations

import argparse
import os

from app.research.embeddings import resolve_embedding_runtime
from app.research.worker import _embed_existing_document
from app.storage.db import create_db_engine, list_research_documents_for_reembed


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-embed stored research documents with the active embedding model.")
    parser.add_argument("--topic-key", required=True)
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    embedding_model_id = os.getenv("RESEARCH_EMBEDDING_MODEL", "text-embedding-3-small").strip()
    embedding_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    runtime = resolve_embedding_runtime(model=embedding_model_id, api_key=embedding_api_key)
    if runtime.get("mode") != "openai":
        raise RuntimeError(f"refusing re-embed with non-openai runtime: {runtime}")

    engine = create_db_engine(database_url)
    rows = list_research_documents_for_reembed(
        engine,
        topic_key=args.topic_key.strip().lower(),
        embedding_model_id=embedding_model_id,
        limit=max(args.limit, 1),
    )
    processed = 0
    failed = 0
    for row in rows:
        extracted_text = str(row.get("extracted_text") or "").strip()
        if not extracted_text:
            continue
        try:
            _embed_existing_document(
                engine,
                document_id=str(row["document_id"]),
                extracted_text=extracted_text,
                embedding_model_id=embedding_model_id,
                embedding_api_key=embedding_api_key,
                chunk_max_chars=int(os.getenv("RESEARCH_CHUNK_MAX_CHARS", "1200")),
            )
            processed += 1
        except Exception as exc:
            failed += 1
            print({"document_id": str(row["document_id"]), "status": "failed", "error": str(exc)})
    print(
        {
            "topic_key": args.topic_key.strip().lower(),
            "embedding_model_id": embedding_model_id,
            "requested_limit": max(args.limit, 1),
            "processed": processed,
            "failed": failed,
        }
    )


if __name__ == "__main__":
    main()
