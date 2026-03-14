from __future__ import annotations

import argparse
import hashlib
import logging
import os
import time
from typing import Any, Dict, List

from app.intel.fetch import fetch_url
from app.intel.extract import extract_readable_text
from app.research.chunking import chunk_document
from app.research.discovery import discover_candidate_items, extract_title_from_html, is_allowed_by_robots
from app.research.embeddings import embed_texts, resolve_embedding_runtime
from app.research.enrichment import derive_evidence_relations, enrich_chunks, enrich_document
from app.research.hygiene import detect_junk_document
from app.research.ids import compute_document_id
from app.research.pdf_extract import extract_pdf_text
from app.storage.db import (
    append_research_run_error,
    claim_next_research_ingestion_run,
    create_db_engine,
    create_research_ingestion_run,
    fail_stale_research_ingestion_runs,
    get_research_document,
    has_open_research_run_for_topic,
    list_due_research_sources,
    list_research_sources,
    mark_research_document_embedded,
    mark_research_document_enriched,
    mark_research_document_failed,
    mark_research_document_fetched,
    mark_research_document_extracted,
    mark_research_ingestion_run_finished,
    mark_research_source_failure,
    mark_research_source_success,
    replace_research_chunks,
    replace_research_document_insights,
    replace_research_evidence_relations,
    replace_research_embeddings,
    set_research_document_suppressed,
    set_research_source_polled,
    update_research_run_counters,
    upsert_research_document_seed,
)
logger = logging.getLogger(__name__)


def _safe_log(message: str, **kwargs: Any) -> None:
    logger.info(message, extra={key: value for key, value in kwargs.items() if value is not None})


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _strip_nul_bytes(value: str) -> str:
    if not value:
        return ""
    return value.replace("\x00", "")


def _fetch_with_retries(url: str) -> Dict[str, Any]:
    max_attempts = _int_env("RESEARCH_FETCH_MAX_ATTEMPTS", 3)
    backoff_base = max(_int_env("RESEARCH_FETCH_BACKOFF_S", 1), 1)
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        try:
            result = fetch_url(url)
            status = int(result.get("status_code") or 0)
            if status in {429, 500, 502, 503, 504} and attempt < max_attempts:
                time.sleep(backoff_base * attempt)
                continue
            return result
        except Exception as exc:  # pragma: no cover - defensive runtime path
            last_error = str(exc)
            if attempt < max_attempts:
                time.sleep(backoff_base * attempt)
                continue
    return {"status_code": 599, "html": "", "headers": {}, "error": last_error}


def _throttle_source(last_request_at: float | None, *, rate_limit_per_hour: int) -> float:
    if rate_limit_per_hour <= 0:
        return time.monotonic()
    min_interval = 3600.0 / float(rate_limit_per_hour)
    now = time.monotonic()
    if last_request_at is not None:
        wait = min_interval - (now - last_request_at)
        if wait > 0:
            time.sleep(wait)
    return time.monotonic()


def _embed_existing_document(
    engine: Any,
    *,
    document_id: str,
    extracted_text: str,
    embedding_model_id: str,
    embedding_api_key: str,
    chunk_max_chars: int,
) -> None:
    chunks = enrich_chunks(chunk_document(
        document_id=document_id,
        text=extracted_text,
        max_chars=max(chunk_max_chars, 200),
    ))
    if not chunks:
        raise RuntimeError("empty chunk set")
    vectors = embed_texts(
        texts=[str(chunk["content"]) for chunk in chunks],
        model=embedding_model_id,
        api_key=embedding_api_key,
    )
    if len(vectors) != len(chunks):
        raise RuntimeError("embedding vector count mismatch")
    replace_research_chunks(
        engine,
        document_id=document_id,
        chunks=chunks,
    )
    replace_research_embeddings(
        engine,
        document_id=document_id,
        embedding_model_id=embedding_model_id,
        embeddings=[
            {"chunk_id": str(chunk["chunk_id"]), "vector": vector}
            for chunk, vector in zip(chunks, vectors)
        ],
    )
    mark_research_document_embedded(
        engine,
        document_id=document_id,
        embedding_model_id=embedding_model_id,
    )


def _process_source(
    engine: Any,
    *,
    run_id: Any,
    source: Dict[str, Any],
    max_new_items: int = 0,
) -> Dict[str, Any]:
    source_id = str(source["source_id"])
    base_url = str(source.get("base_url_canonical") or source.get("base_url_original") or "")
    kind = str(source.get("kind") or "html_listing")
    robots_mode = str(source.get("robots_mode") or "strict")
    user_agent = os.getenv("INTEL_USER_AGENT", "context_api/1.0")
    max_items_default = _int_env("RESEARCH_MAX_ITEMS_PER_SOURCE", 50)
    max_items = int(source.get("max_items_per_run") or max_items_default)
    rate_limit_per_hour = int(source.get("rate_limit_per_hour") or 30)
    chunk_max_chars = _int_env("RESEARCH_CHUNK_MAX_CHARS", 1200)
    embedding_model_id = os.getenv("RESEARCH_EMBEDDING_MODEL", "text-embedding-3-small")
    embedding_api_key = os.getenv("OPENAI_API_KEY", "")
    embedding_runtime = resolve_embedding_runtime(model=embedding_model_id, api_key=embedding_api_key)
    if embedding_runtime.get("warning"):
        logger.warning("research_embedding_runtime %s", embedding_runtime["warning"])
    reembed_budget = _int_env("RESEARCH_REEMBED_MAX_PER_RUN", 25)
    reembedded = 0

    counters: Dict[str, Any] = {"seen": 0, "new": 0, "deduped": 0, "failed": 0}
    source_error = ""
    source_fetch = _fetch_with_retries(base_url)
    source_status = int(source_fetch.get("status_code") or 0)
    if source_status >= 400:
        counters["failed"] += 1
        source_error = f"source_fetch_failed status={source_status}"
        append_research_run_error(
            engine,
            run_id=run_id,
            message=f"source_fetch_failed source_id={source_id} status={source_status} url={base_url}",
        )
        set_research_source_polled(engine, source_id=source_id)
        counters["source_error"] = source_error
        return counters

    discovered = discover_candidate_items(
        kind=kind,
        raw_text=str(source_fetch.get("html") or ""),
        base_url=base_url,
        max_items=max_items,
    )
    last_request_at: float | None = None
    for item in discovered:
        if max_new_items > 0 and counters["new"] >= max_new_items:
            break
        item_url = str(item.get("url") or "").strip()
        item_title = str(item.get("title") or "").strip()
        item_summary = str(item.get("summary") or "").strip()
        if not item_url:
            continue
        counters["seen"] += 1
        if robots_mode == "strict":
            allowed = is_allowed_by_robots(url=item_url, user_agent=user_agent)
            if not allowed:
                counters["failed"] += 1
                append_research_run_error(
                    engine,
                    run_id=run_id,
                    message=f"robots_blocked source_id={source_id} url={item_url}",
                )
                source_error = "robots_blocked"
                continue

        document_id = compute_document_id(
            source_id=source_id,
            canonical_url=item_url,
            external_id=(item.get("external_id") or None),
        )
        seed_state = upsert_research_document_seed(
            engine,
            document_id=document_id,
            source_id=source_id,
            run_id=run_id,
            canonical_url=item_url,
            url_original=item_url,
            external_id=item.get("external_id") or None,
        )
        if seed_state == "deduped":
            counters["deduped"] += 1
            if reembed_budget > 0 and reembedded < reembed_budget:
                existing = get_research_document(engine, document_id=document_id)
                if existing:
                    existing_text = str(existing.get("extracted_text") or "").strip()
                    existing_model = str(existing.get("embedding_model_id") or "").strip()
                    existing_status = str(existing.get("status") or "")
                    if (
                        existing_text
                        and existing_status in {"embedded", "extracted"}
                        and existing_model != embedding_model_id
                    ):
                        try:
                            _embed_existing_document(
                                engine,
                                document_id=document_id,
                                extracted_text=existing_text,
                                embedding_model_id=embedding_model_id,
                                embedding_api_key=embedding_api_key,
                                chunk_max_chars=chunk_max_chars,
                            )
                            reembedded += 1
                            _safe_log(
                                "research_document_reembedded",
                                document_id=document_id,
                                previous_model=existing_model or "none",
                                embedding_model_id=embedding_model_id,
                            )
                        except Exception as exc:
                            counters["failed"] += 1
                            append_research_run_error(
                                engine,
                                run_id=run_id,
                                message=f"reembed_failed source_id={source_id} document_id={document_id} error={exc}",
                            )
            continue
        if seed_state == "new":
            counters["new"] += 1

        last_request_at = _throttle_source(last_request_at, rate_limit_per_hour=rate_limit_per_hour)
        item_fetch = _fetch_with_retries(item_url)
        item_status = int(item_fetch.get("status_code") or 0)
        content_type = str((item_fetch.get("headers") or {}).get("content-type") or "").lower()
        content_bytes = item_fetch.get("content_bytes") or b""
        is_pdf = "application/pdf" in content_type or item_url.lower().endswith(".pdf")
        raw_payload = "" if is_pdf else _strip_nul_bytes(str(item_fetch.get("html") or ""))
        safe_item_title = _strip_nul_bytes(item_title)
        safe_item_summary = _strip_nul_bytes(item_summary)
        has_payload = bool(content_bytes) if is_pdf else bool(raw_payload)
        if item_status >= 400 or not has_payload:
            if not safe_item_summary:
                counters["failed"] += 1
                source_error = f"item_fetch_failed status={item_status}"
                mark_research_document_failed(
                    engine,
                    document_id=document_id,
                    fetch_meta={
                        "http_status": item_status,
                        "content_type": content_type,
                        "error": item_fetch.get("error"),
                    },
                )
                append_research_run_error(
                    engine,
                    run_id=run_id,
                    message=f"item_fetch_failed source_id={source_id} status={item_status} url={item_url}",
                )
                continue

            # Fallback for blocked fetches: ingest feed summary text so retrieval still has signal.
            content_hash = hashlib.sha256(safe_item_summary.encode("utf-8")).hexdigest()
            mark_research_document_fetched(
                engine,
                document_id=document_id,
                title=safe_item_title or None,
                raw_payload="",
                content_hash=content_hash,
                published_at=item.get("published_at"),
                fetch_meta={
                    "http_status": item_status,
                    "content_type": content_type,
                    "error": item_fetch.get("error"),
                    "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "raw_payload_stored": False,
                    "fallback": "feed_summary",
                },
            )
            extraction = {
                "text": safe_item_summary,
                "method": "feed_summary",
                "confidence": 0.35,
                "warnings": [f"fetch_failed_status_{item_status}"],
                "published_at": None,
            }
        else:
            if is_pdf:
                content_hash = hashlib.sha256(content_bytes).hexdigest()
            else:
                content_hash = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()
            mark_research_document_fetched(
                engine,
                document_id=document_id,
                title=(_strip_nul_bytes(extract_title_from_html(raw_payload)) or safe_item_title or None) if not is_pdf else (safe_item_title or None),
                raw_payload=raw_payload,
                content_hash=content_hash,
                published_at=item.get("published_at"),
                fetch_meta={
                    "http_status": item_status,
                    "content_type": content_type,
                    "etag": (item_fetch.get("headers") or {}).get("etag"),
                    "last_modified": (item_fetch.get("headers") or {}).get("last-modified"),
                    "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "binary_bytes": len(content_bytes) if is_pdf else 0,
                    "raw_payload_stored": not is_pdf,
                    "warnings": ["truncated"] if item_fetch.get("truncated") else [],
                },
            )

            if is_pdf:
                extraction = extract_pdf_text(content_bytes)
                extraction["published_at"] = None
                extraction["confidence"] = 0.6 if extraction.get("text") else 0.0
            else:
                extraction = extract_readable_text(raw_payload, item_url)
        extracted_text = _strip_nul_bytes(str(extraction.get("text") or "")).strip()
        if not extracted_text:
            if safe_item_summary:
                extraction = {
                    "text": safe_item_summary,
                    "method": "feed_summary",
                    "confidence": 0.3,
                    "warnings": ["empty_extraction_fallback_to_feed_summary"],
                    "published_at": None,
                }
                extracted_text = safe_item_summary
                mark_research_document_fetched(
                    engine,
                    document_id=document_id,
                    title=safe_item_title or None,
                    raw_payload="",
                    content_hash=hashlib.sha256(safe_item_summary.encode("utf-8")).hexdigest(),
                    published_at=item.get("published_at"),
                    fetch_meta={
                        "http_status": item_status,
                        "content_type": content_type,
                        "error": "empty extracted text",
                        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "raw_payload_stored": False,
                        "fallback": "feed_summary",
                    },
                )
            else:
                counters["failed"] += 1
                source_error = "extraction_failed"
                mark_research_document_failed(
                    engine,
                    document_id=document_id,
                    fetch_meta={
                        "http_status": item_status,
                        "content_type": content_type,
                        "error": "empty extracted text",
                    },
                )
                append_research_run_error(
                    engine,
                    run_id=run_id,
                    message=f"extraction_failed source_id={source_id} url={item_url}",
                )
                continue
        junk_reason = detect_junk_document(
            url=item_url,
            title=safe_item_title or str(extract_title_from_html(raw_payload) or ""),
            extracted_text=extracted_text,
            item_summary=safe_item_summary,
            fetch_status=item_status,
            fetch_fallback=str((get_research_document(engine, document_id=document_id) or {}).get("fetch_meta", {}).get("fallback") or ""),
        )
        if junk_reason:
            set_research_document_suppressed(
                engine,
                document_id=document_id,
                suppressed=True,
                reason=junk_reason,
            )
            append_research_run_error(
                engine,
                run_id=run_id,
                message=f"document_suppressed source_id={source_id} document_id={document_id} reason={junk_reason} url={item_url}",
            )
            _safe_log(
                "research_document_suppressed",
                source_id=source_id,
                document_id=document_id,
                reason=junk_reason,
                url=item_url,
            )
            continue
        mark_research_document_extracted(
            engine,
            document_id=document_id,
            extracted_text=extracted_text,
            extraction_meta={
                "method": extraction.get("method"),
                "confidence": extraction.get("confidence"),
                "format": "pdf" if is_pdf else "html",
                "warnings": extraction.get("warnings") or [],
                "published_at_source": "feed" if item.get("published_at") else "",
            },
            published_at=extraction.get("published_at") or item.get("published_at"),
            summary_short=extracted_text[:320],
        )
        existing_doc = get_research_document(engine, document_id=document_id) or {}
        enriched_chunks = enrich_chunks(
            chunk_document(
                document_id=document_id,
                text=extracted_text,
                max_chars=max(chunk_max_chars, 200),
            )
        )
        enrichment, insights = enrich_document(
            canonical_url=item_url,
            source_name=str(source.get("name") or ""),
            source_class=str(source.get("source_class") or "external_commentary"),
            default_decision_domains=[str(value) for value in (source.get("default_decision_domains") or [])],
            extracted_text=extracted_text,
            chunks=enriched_chunks,
            fetch_meta=dict(existing_doc.get("fetch_meta") or {}),
            extraction_meta=dict(existing_doc.get("extraction_meta") or {}),
            published_at=(extraction.get("published_at") or item.get("published_at")),
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
        try:
            _embed_existing_document(
                engine,
                document_id=document_id,
                extracted_text=extracted_text,
                embedding_model_id=embedding_model_id,
                embedding_api_key=embedding_api_key,
                chunk_max_chars=chunk_max_chars,
            )
        except Exception as exc:
            counters["failed"] += 1
            source_error = f"embedding_failed error={exc}"
            mark_research_document_failed(
                engine,
                document_id=document_id,
                fetch_meta={
                    "http_status": item_status,
                    "content_type": (item_fetch.get("headers") or {}).get("content-type"),
                    "error": f"embedding_error: {exc}",
                },
            )
            append_research_run_error(
                engine,
                run_id=run_id,
                message=f"embedding_failed source_id={source_id} url={item_url} error={exc}",
            )
            continue

    set_research_source_polled(engine, source_id=source_id)
    counters["source_error"] = source_error
    return counters


def process_run(engine: Any, run: Dict[str, Any]) -> None:
    run_id = run.get("run_id")
    topic_key = str(run.get("topic_key") or "")
    selected_source_ids = run.get("selected_source_ids") or []
    source_ids: List[str] = [str(value) for value in selected_source_ids if value]
    sources = list_research_sources(
        engine,
        topic_key=topic_key,
        source_ids=source_ids or None,
        enabled_only=True,
    )
    failure_threshold = _int_env("RESEARCH_SOURCE_FAILURE_THRESHOLD", 3)
    cooldown_minutes = _int_env("RESEARCH_SOURCE_COOLDOWN_MINUTES", 60)
    run_new_item_budget = _int_env("RESEARCH_RUN_MAX_NEW_ITEMS", 0)
    run_new_items = 0
    try:
        for source in sources:
            source_id = str(source.get("source_id") or "")
            remaining_budget = 0
            if run_new_item_budget > 0:
                remaining_budget = max(run_new_item_budget - run_new_items, 0)
                if remaining_budget <= 0:
                    append_research_run_error(
                        engine,
                        run_id=run_id,
                        message=f"run_budget_exhausted max_new_items={run_new_item_budget}",
                    )
                    break
            counters = _process_source(
                engine,
                run_id=run_id,
                source=source,
                max_new_items=remaining_budget,
            )
            update_research_run_counters(
                engine,
                run_id=run_id,
                items_seen=counters["seen"],
                items_new=counters["new"],
                items_deduped=counters["deduped"],
                items_failed=counters["failed"],
            )
            run_new_items += int(counters["new"])
            if source_id:
                if int(counters["failed"]) > 0:
                    mark_research_source_failure(
                        engine,
                        source_id=source_id,
                        error=str(counters.get("source_error") or "source_processing_failed"),
                        failure_threshold=failure_threshold,
                        cooldown_minutes=cooldown_minutes,
                    )
                else:
                    mark_research_source_success(engine, source_id=source_id)
            if run_new_item_budget > 0 and run_new_items >= run_new_item_budget:
                append_research_run_error(
                    engine,
                    run_id=run_id,
                    message=f"run_budget_exhausted max_new_items={run_new_item_budget}",
                )
                break
        mark_research_ingestion_run_finished(engine, run_id=run_id, status="completed")
        _safe_log("research_run_completed", run_id=str(run_id), topic_key=topic_key)
    except Exception as exc:  # pragma: no cover - defensive runtime path
        append_research_run_error(engine, run_id=run_id, message=f"run_failed error={exc}")
        mark_research_ingestion_run_finished(engine, run_id=run_id, status="failed")
        _safe_log("research_run_failed", run_id=str(run_id), topic_key=topic_key, error=str(exc))


def enqueue_due_schedule_runs(engine: Any) -> int:
    due_sources = list_due_research_sources(engine)
    if not due_sources:
        return 0
    grouped: Dict[str, List[str]] = {}
    for source in due_sources:
        topic_key = str(source.get("topic_key") or "")
        source_id = str(source.get("source_id") or "")
        if not topic_key or not source_id:
            continue
        grouped.setdefault(topic_key, []).append(source_id)
    created = 0
    for topic_key, source_ids in grouped.items():
        if has_open_research_run_for_topic(engine, topic_key=topic_key, trigger="schedule"):
            continue
        create_research_ingestion_run(
            engine,
            topic_key=topic_key,
            trigger="schedule",
            requested_source_ids=[],
            selected_source_ids=source_ids,
            idempotency_key=None,
        )
        created += 1
    return created


def run_once(engine: Any) -> bool:
    stale_after_seconds = _int_env("RESEARCH_RUN_STALE_AFTER_S", 300)
    recovered = fail_stale_research_ingestion_runs(engine, stale_after_seconds=stale_after_seconds)
    if recovered:
        _safe_log("research_stale_runs_failed", count=recovered, stale_after_seconds=stale_after_seconds)
    run = claim_next_research_ingestion_run(engine)
    if not run:
        return False
    process_run(engine, run)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Research ingestion worker (stub)")
    parser.add_argument("--once", action="store_true", help="Run one loop iteration and exit")
    parser.add_argument("--sleep-seconds", type=int, default=5)
    args = parser.parse_args()

    enabled = os.getenv("RESEARCH_WORKER_ENABLED", "false").lower() == "true"
    if not enabled:
        logger.info("research_worker_disabled")
        return

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    engine = create_db_engine(database_url)

    while True:
        processed = run_once(engine)
        if args.once:
            break
        if not processed:
            created = enqueue_due_schedule_runs(engine)
            if created <= 0:
                time.sleep(max(args.sleep_seconds, 1))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
