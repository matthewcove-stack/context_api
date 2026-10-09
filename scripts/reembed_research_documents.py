from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.research.embeddings import EmbeddingProviderError, resolve_embedding_runtime
from app.research.worker import _embed_existing_document
from app.storage.db import create_db_engine, list_research_documents_for_reembed


def emit_report(report: dict, *, exit_status: int) -> None:
    """Keep repair diagnostics available when publication never starts."""
    print(json.dumps(report))
    report_dir = os.getenv("BRIEF_PUBLISH_REPORT_DIR", "").strip()
    if not report_dir:
        return
    temporary_path = None
    try:
        directory = Path(report_dir)
        directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        artifact = dict(report, phase="embedding-repair", exit_status=exit_status)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as output:
            temporary_path = Path(output.name)
            json.dump(artifact, output, indent=2)
            output.write("\n")
        temporary_path.replace(directory / f"embedding-repair-{timestamp}-{os.getpid()}.json")
    except OSError:
        # Reporting must not mask the original provider status or trigger retry.
        print("Unable to write embedding repair report; see stdout diagnostics.", file=sys.stderr)
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def main() -> int:
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
        except EmbeddingProviderError as exc:
            emit_report({
                "status": "blocked-provider", "provider_code": exc.code,
                "http_status": exc.status, "action": exc.action,
                "selected": len(rows), "processed": processed, "failed": failed + 1,
                "remaining": len(rows) - processed - failed - 1,
            }, exit_status=exc.exit_status)
            return exc.exit_status
        except Exception as exc:
            failed += 1
            print(json.dumps({"document_id": str(row["document_id"]), "status": "failed", "error": str(exc)}))
    exit_status = 1 if failed else 0
    emit_report(
        {
            "topic_key": args.topic_key.strip().lower(),
            "embedding_model_id": embedding_model_id,
            "requested_limit": max(args.limit, 1),
            "selected": len(rows),
            "processed": processed,
            "failed": failed,
        }, exit_status=exit_status
    )
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())

