from __future__ import annotations

import argparse
import hashlib
import logging
import os
import time
from typing import Any, Dict, List

from app.intel.fetch import fetch_url
from app.research.discovery import discover_candidate_items, extract_title_from_html, is_allowed_by_robots
from app.research.ids import compute_document_id
from app.storage.db import (
    append_research_run_error,
    claim_next_research_ingestion_run,
    create_db_engine,
    create_research_ingestion_run,
    has_open_research_run_for_topic,
    list_due_research_sources,
    list_research_sources,
    mark_research_document_failed,
    mark_research_document_fetched,
    mark_research_ingestion_run_finished,
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


def _process_source(
    engine: Any,
    *,
    run_id: Any,
    source: Dict[str, Any],
) -> Dict[str, int]:
    source_id = str(source["source_id"])
    base_url = str(source.get("base_url_canonical") or source.get("base_url_original") or "")
    kind = str(source.get("kind") or "html_listing")
    robots_mode = str(source.get("robots_mode") or "strict")
    user_agent = os.getenv("INTEL_USER_AGENT", "context_api/1.0")
    max_items_default = _int_env("RESEARCH_MAX_ITEMS_PER_SOURCE", 50)
    max_items = int(source.get("max_items_per_run") or max_items_default)
    rate_limit_per_hour = int(source.get("rate_limit_per_hour") or 30)

    counters = {"seen": 0, "new": 0, "deduped": 0, "failed": 0}
    source_fetch = _fetch_with_retries(base_url)
    source_status = int(source_fetch.get("status_code") or 0)
    if source_status >= 400:
        counters["failed"] += 1
        append_research_run_error(
            engine,
            run_id=run_id,
            message=f"source_fetch_failed source_id={source_id} status={source_status} url={base_url}",
        )
        set_research_source_polled(engine, source_id=source_id)
        return counters

    discovered = discover_candidate_items(
        kind=kind,
        raw_text=str(source_fetch.get("html") or ""),
        base_url=base_url,
        max_items=max_items,
    )
    last_request_at: float | None = None
    for item in discovered:
        item_url = str(item.get("url") or "").strip()
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
            continue
        if seed_state == "new":
            counters["new"] += 1

        last_request_at = _throttle_source(last_request_at, rate_limit_per_hour=rate_limit_per_hour)
        item_fetch = _fetch_with_retries(item_url)
        item_status = int(item_fetch.get("status_code") or 0)
        raw_payload = str(item_fetch.get("html") or "")
        if item_status >= 400 or not raw_payload:
            counters["failed"] += 1
            mark_research_document_failed(
                engine,
                document_id=document_id,
                fetch_meta={
                    "http_status": item_status,
                    "content_type": (item_fetch.get("headers") or {}).get("content-type"),
                    "error": item_fetch.get("error"),
                },
            )
            append_research_run_error(
                engine,
                run_id=run_id,
                message=f"item_fetch_failed source_id={source_id} status={item_status} url={item_url}",
            )
            continue

        content_hash = hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()
        mark_research_document_fetched(
            engine,
            document_id=document_id,
            title=extract_title_from_html(raw_payload) or None,
            raw_payload=raw_payload,
            content_hash=content_hash,
            fetch_meta={
                "http_status": item_status,
                "content_type": (item_fetch.get("headers") or {}).get("content-type"),
                "etag": (item_fetch.get("headers") or {}).get("etag"),
                "last_modified": (item_fetch.get("headers") or {}).get("last-modified"),
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "warnings": ["truncated"] if item_fetch.get("truncated") else [],
            },
        )

    set_research_source_polled(engine, source_id=source_id)
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
    try:
        for source in sources:
            counters = _process_source(engine, run_id=run_id, source=source)
            update_research_run_counters(
                engine,
                run_id=run_id,
                items_seen=counters["seen"],
                items_new=counters["new"],
                items_deduped=counters["deduped"],
                items_failed=counters["failed"],
            )
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
