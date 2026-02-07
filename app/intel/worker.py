from __future__ import annotations

import argparse
import logging
import os
import time
from typing import Any, Callable, Dict, Optional

from app.intel.enrich import enrich_article
from app.intel.extract import extract_readable_text
from app.intel.fetch import fetch_url
from app.intel.sectionise import sectionise
from app.storage.db import (
    claim_next_job,
    get_intel_article,
    mark_article_enriched,
    mark_article_extracted,
    mark_article_failed,
    replace_intel_sections,
    update_job_status,
)
from app.storage.db import create_db_engine

logger = logging.getLogger(__name__)


def _safe_log(message: str, **kwargs: Any) -> None:
    safe = {key: value for key, value in kwargs.items() if value is not None}
    logger.info(message, extra=safe)


def process_job(
    engine: Any,
    job: Dict[str, Any],
    *,
    enrich: bool = True,
    fetcher: Callable[[str], Dict[str, Any]] = fetch_url,
    extractor: Callable[[str, str], Dict[str, Any]] = extract_readable_text,
    sectioniser: Callable[[str], Dict[str, Any]] = sectionise,
    enricher: Callable[..., Any] = enrich_article,
) -> None:
    job_id = job.get("job_id")
    article_id = job.get("article_id")
    url = job.get("url_canonical") or job.get("url_original")
    if not article_id or not url:
        update_job_status(engine, job_id=job_id, status="failed", last_error="missing job data")
        return

    try:
        fetch_result = fetcher(url)
    except Exception as exc:
        update_job_status(engine, job_id=job_id, status="failed", last_error=str(exc))
        mark_article_failed(engine, article_id=article_id)
        return

    html = fetch_result.get("html") or ""
    status_code = fetch_result.get("status_code")
    if status_code and int(status_code) >= 400:
        update_job_status(
            engine,
            job_id=job_id,
            status="failed",
            last_error=f"http_status_{status_code}",
        )
        mark_article_failed(engine, article_id=article_id)
        return
    if not html:
        update_job_status(engine, job_id=job_id, status="failed", last_error="empty html")
        mark_article_failed(engine, article_id=article_id)
        return

    extract_result = extractor(html, url)
    text = extract_result.get("text") or ""
    if not text:
        update_job_status(engine, job_id=job_id, status="failed", last_error="empty extracted text")
        mark_article_failed(engine, article_id=article_id)
        return

    sectionised = sectioniser(text)
    sections = sectionised.get("sections") or []
    outline = sectionised.get("outline") or []
    replace_intel_sections(engine, article_id=article_id, sections=sections)

    fetch_meta = {
        "http_status": status_code,
        "content_type": fetch_result.get("headers", {}).get("content-type"),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "warnings": ["truncated"] if fetch_result.get("truncated") else [],
    }
    extraction_meta = {
        "method": extract_result.get("method"),
        "confidence": extract_result.get("confidence"),
        "warnings": extract_result.get("warnings") or [],
    }

    mark_article_extracted(
        engine,
        article_id=article_id,
        title=extract_result.get("title"),
        author=extract_result.get("author"),
        published_at=extract_result.get("published_at"),
        extracted_text=text,
        raw_html=html,
        http_status=status_code,
        content_type=fetch_result.get("headers", {}).get("content-type"),
        etag=fetch_result.get("headers", {}).get("etag"),
        last_modified=fetch_result.get("headers", {}).get("last-modified"),
        fetch_meta=fetch_meta,
        extraction_meta=extraction_meta,
        outline=outline,
    )

    if not enrich:
        update_job_status(engine, job_id=job_id, status="done")
        _safe_log("intel_job_done", job_id=str(job_id), article_id=article_id, status="extracted")
        return

    article_row = get_intel_article(engine, article_id) or {}
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    api_key = os.getenv("OPENAI_API_KEY", "")
    try:
        enriched, enrichment_meta = enricher(
            title=extract_result.get("title"),
            url=url,
            sections=sections,
            model=model,
            api_key=api_key,
        )
        topics = enriched.get("topics") or (article_row.get("topics") or [])
        mark_article_enriched(
            engine,
            article_id=article_id,
            summary=enriched.get("summary") or "",
            signals=enriched.get("signals") or [],
            topics=topics,
            enrichment_meta=enrichment_meta,
            outline=outline,
            status="enriched",
        )
        update_job_status(engine, job_id=job_id, status="done")
        _safe_log("intel_job_done", job_id=str(job_id), article_id=article_id, status="enriched")
    except Exception as exc:
        mark_article_enriched(
            engine,
            article_id=article_id,
            summary="",
            signals=[],
            topics=article_row.get("topics") or [],
            enrichment_meta={"warnings": ["enrichment_failed"], "error": str(exc)},
            outline=outline,
            status="partial",
        )
        update_job_status(engine, job_id=job_id, status="failed", last_error=str(exc))
        _safe_log("intel_job_failed", job_id=str(job_id), article_id=article_id, error=str(exc))


def run_once(engine: Any, *, enrich: bool = True) -> bool:
    job = claim_next_job(engine)
    if not job:
        return False
    job_enrich = job.get("enrich", enrich)
    process_job(engine, job, enrich=job_enrich)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Intel ingestion worker")
    parser.add_argument("--once", action="store_true", help="Process one job and exit")
    parser.add_argument("--sleep-seconds", type=int, default=5)
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    engine = create_db_engine(database_url)
    enrich_enabled = os.getenv("INTEL_ENRICH", "true").lower() != "false"

    while True:
        processed = run_once(engine, enrich=enrich_enabled)
        if args.once:
            break
        if not processed:
            time.sleep(max(args.sleep_seconds, 1))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
