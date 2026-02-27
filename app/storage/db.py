from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import hashlib
import uuid
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.storage.schema import (
    intel_article_sections,
    intel_articles,
    intel_ingest_jobs,
    projects,
    research_documents,
    research_chunks,
    research_embeddings,
    research_ingestion_runs,
    research_relevance_scores,
    research_retrieval_feedback,
    research_query_logs,
    research_source_policies,
    research_sources,
    tasks,
)


def create_db_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True, future=True)


def check_db(engine: Engine) -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def upsert_projects(
    engine: Engine,
    *,
    items: Iterable[Dict[str, Any]],
    source: Optional[str],
) -> int:
    rows = []
    for item in items:
        rows.append(
            {
                "project_id": item["project_id"],
                "name": item["name"],
                "status": item.get("status"),
                "source": source,
                "updated_at": item.get("updated_at"),
                "raw": item.get("raw"),
            }
        )
    if not rows:
        return 0
    stmt = pg_insert(projects).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[projects.c.project_id],
        set_={
            "name": stmt.excluded.name,
            "status": stmt.excluded.status,
            "source": stmt.excluded.source,
            "updated_at": stmt.excluded.updated_at,
            "raw": stmt.excluded.raw,
        },
    )
    with engine.begin() as conn:
        conn.execute(stmt)
    return len(rows)


def upsert_tasks(
    engine: Engine,
    *,
    items: Iterable[Dict[str, Any]],
    source: Optional[str],
) -> int:
    rows = []
    for item in items:
        rows.append(
            {
                "task_id": item["task_id"],
                "title": item["title"],
                "status": item.get("status"),
                "priority": item.get("priority"),
                "due": item.get("due"),
                "project_id": item.get("project_id"),
                "source": source,
                "updated_at": item.get("updated_at"),
                "raw": item.get("raw"),
            }
        )
    if not rows:
        return 0
    stmt = pg_insert(tasks).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[tasks.c.task_id],
        set_={
            "title": stmt.excluded.title,
            "status": stmt.excluded.status,
            "priority": stmt.excluded.priority,
            "due": stmt.excluded.due,
            "project_id": stmt.excluded.project_id,
            "source": stmt.excluded.source,
            "updated_at": stmt.excluded.updated_at,
            "raw": stmt.excluded.raw,
        },
    )
    with engine.begin() as conn:
        conn.execute(stmt)
    return len(rows)


def get_project(engine: Engine, project_id: str) -> Optional[Dict[str, Any]]:
    with engine.begin() as conn:
        row = conn.execute(select(projects).where(projects.c.project_id == project_id)).mappings().first()
        return dict(row) if row else None


def get_task(engine: Engine, task_id: str) -> Optional[Dict[str, Any]]:
    with engine.begin() as conn:
        row = conn.execute(select(tasks).where(tasks.c.task_id == task_id)).mappings().first()
        return dict(row) if row else None


def search_projects(engine: Engine, query: str, limit: int) -> List[Dict[str, Any]]:
    pattern = f"%{query}%"
    with engine.begin() as conn:
        rows = (
            conn.execute(
                select(projects)
                .where(projects.c.name.ilike(pattern))
                .order_by(projects.c.name.asc())
                .limit(max(limit, 1) * 5)
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


def search_tasks(
    engine: Engine,
    *,
    query: str,
    limit: int,
    project_id: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    pattern = f"%{query}%"
    stmt = select(tasks).where(tasks.c.title.ilike(pattern))
    if project_id:
        stmt = stmt.where(tasks.c.project_id == project_id)
    if status:
        stmt = stmt.where(tasks.c.status == status)
    stmt = stmt.order_by(tasks.c.title.asc()).limit(max(limit, 1) * 5)
    with engine.begin() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [dict(row) for row in rows]


def upsert_intel_articles(engine: Engine, *, items: Iterable[Dict[str, Any]]) -> List[str]:
    rows: List[Dict[str, Any]] = []
    for item in items:
        rows.append(
            {
                "article_id": item["article_id"],
                "url": item["url"],
                "title": item["title"],
                "publisher": item.get("publisher"),
                "author": item.get("author"),
                "published_at": item.get("published_at"),
                "topics": item.get("topics") or [],
                "summary": item.get("summary") or "",
                "signals": item.get("signals") or [],
                "outline": item.get("outline") or [],
                "outbound_links": item.get("outbound_links") or [],
                "status": item.get("status") or "enriched",
            }
        )
    if not rows:
        return []
    stmt = pg_insert(intel_articles).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[intel_articles.c.article_id],
        set_={
            "url": stmt.excluded.url,
            "title": stmt.excluded.title,
            "publisher": stmt.excluded.publisher,
            "author": stmt.excluded.author,
            "published_at": stmt.excluded.published_at,
            "topics": stmt.excluded.topics,
            "summary": stmt.excluded.summary,
            "signals": stmt.excluded.signals,
            "outline": stmt.excluded.outline,
            "outbound_links": stmt.excluded.outbound_links,
            "status": stmt.excluded.status,
            "updated_at": text("now()"),
        },
    )
    with engine.begin() as conn:
        conn.execute(stmt)
    return [row["article_id"] for row in rows]


def replace_intel_sections(engine: Engine, *, article_id: str, sections: Iterable[Dict[str, Any]]) -> None:
    rows: List[Dict[str, Any]] = []
    for section in sections:
        section_id = section.get("section_id")
        content = section.get("content")
        if not section_id or not content:
            continue
        rows.append(
            {
                "article_id": article_id,
                "section_id": section_id,
                "heading": section.get("heading") or "",
                "content": content,
                "rank": int(section.get("rank") or 0),
            }
        )
    rows.sort(key=lambda item: (item["rank"], item["section_id"]))
    with engine.begin() as conn:
        conn.execute(
            intel_article_sections.delete().where(intel_article_sections.c.article_id == article_id)
        )
        if rows:
            conn.execute(intel_article_sections.insert(), rows)


def search_intel_articles(
    engine: Engine,
    *,
    query: str,
    limit: int,
    recency_days: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if not query.strip():
        return []
    fts_expr = (
        "to_tsvector('english', coalesce(title, '') || ' ' || "
        "coalesce(summary, '') || ' ' || coalesce(signals::text, ''))"
    )
    sql = f"""
        SELECT
            article_id,
            url,
            title,
            summary,
            signals,
            outline,
            topics,
            published_at,
            ingested_at,
            ts_rank({fts_expr}, plainto_tsquery('english', :query)) AS score
        FROM intel_articles
        WHERE {fts_expr} @@ plainto_tsquery('english', :query)
    """
    params: Dict[str, Any] = {"query": query, "limit": max(limit, 1)}
    if recency_days is not None:
        sql += " AND coalesce(published_at, ingested_at) >= now() - (:recency_days * interval '1 day')"
        params["recency_days"] = max(recency_days, 0)
    sql += " ORDER BY score DESC, published_at DESC NULLS LAST, ingested_at DESC LIMIT :limit"
    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]


def get_intel_outline(engine: Engine, article_id: str) -> Optional[Dict[str, Any]]:
    with engine.begin() as conn:
        row = (
            conn.execute(
                select(intel_articles.c.article_id, intel_articles.c.outline).where(
                    intel_articles.c.article_id == article_id
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None


def get_intel_sections(
    engine: Engine,
    *,
    article_id: str,
    section_ids: List[str],
) -> List[Dict[str, Any]]:
    if not section_ids:
        return []
    stmt = (
        select(intel_article_sections)
        .where(intel_article_sections.c.article_id == article_id)
        .where(intel_article_sections.c.section_id.in_(section_ids))
        .order_by(intel_article_sections.c.rank.asc())
    )
    with engine.begin() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [dict(row) for row in rows]


def search_intel_sections(
    engine: Engine,
    *,
    article_id: str,
    query: str,
    limit: int,
) -> List[Dict[str, Any]]:
    if not query.strip():
        return []
    sql = """
        SELECT
            section_id,
            ts_rank(
                to_tsvector('english', coalesce(content, '')),
                plainto_tsquery('english', :query)
            ) AS score,
            ts_headline(
                'english',
                content,
                plainto_tsquery('english', :query),
                'MaxWords=30, MinWords=12, ShortWord=3'
            ) AS snippet,
            rank
        FROM intel_article_sections
        WHERE article_id = :article_id
          AND to_tsvector('english', coalesce(content, '')) @@ plainto_tsquery('english', :query)
        ORDER BY score DESC, rank ASC
        LIMIT :limit
    """
    params = {"article_id": article_id, "query": query, "limit": max(limit, 1)}
    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]


TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_name",
    "utm_cid",
    "utm_reader",
    "utm_viz_id",
    "utm_pubreferrer",
    "utm_swu",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
}


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    trimmed = url.strip()
    parsed = urlparse(trimmed)
    if not parsed.scheme:
        parsed = urlparse(f"https://{trimmed}")
    scheme = (parsed.scheme or "https").lower()
    netloc = (parsed.netloc or "").lower()
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    if scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    params = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=False)
        if key.lower() not in TRACKING_QUERY_KEYS
    ]
    params.sort()
    query = urlencode(params, doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def compute_article_id(canonical_url: str) -> str:
    if not canonical_url:
        raise ValueError("canonical_url is required")
    digest = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
    return f"url_{digest}"


def upsert_intel_article_seed(
    engine: Engine,
    *,
    article_id: str,
    url: str,
    url_original: Optional[str],
    topics: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    status: str = "queued",
    force_reset: bool = False,
) -> None:
    values: Dict[str, Any] = {
        "article_id": article_id,
        "url": url,
        "title": "",
        "status": status,
    }
    if url_original:
        values["url_original"] = url_original
    if topics is not None:
        values["topics"] = topics
    if tags is not None:
        values["tags"] = tags
    stmt = pg_insert(intel_articles).values(values)
    update_values: Dict[str, Any] = {
        "url": stmt.excluded.url,
        "status": stmt.excluded.status,
        "updated_at": text("now()"),
    }
    if url_original:
        update_values["url_original"] = stmt.excluded.url_original
    if topics is not None:
        update_values["topics"] = stmt.excluded.topics
    if tags is not None:
        update_values["tags"] = stmt.excluded.tags
    if force_reset:
        update_values.update(
            {
                "summary": "",
                "signals": [],
                "outline": [],
                "outbound_links": [],
                "raw_html": None,
                "extracted_text": None,
                "http_status": None,
                "content_type": None,
                "etag": None,
                "last_modified": None,
                "fetch_meta": None,
                "extraction_meta": None,
                "enrichment_meta": None,
            }
        )
    stmt = stmt.on_conflict_do_update(
        index_elements=[intel_articles.c.article_id],
        set_=update_values,
    )
    with engine.begin() as conn:
        conn.execute(stmt)


def create_intel_ingest_job(
    engine: Engine,
    *,
    url_original: str,
    url_canonical: str,
    article_id: str,
    status: str = "queued",
) -> str:
    job_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            intel_ingest_jobs.insert().values(
                {
                    "job_id": job_id,
                    "url_original": url_original,
                    "url_canonical": url_canonical,
                    "article_id": article_id,
                    "status": status,
                }
            )
        )
    return str(job_id)


def claim_next_job(engine: Engine) -> Optional[Dict[str, Any]]:
    sql_select = """
        SELECT *
        FROM intel_ingest_jobs
        WHERE status IN ('queued', 'retry', 'queued_no_enrich')
        ORDER BY created_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    """
    with engine.begin() as conn:
        row = conn.execute(text(sql_select)).mappings().first()
        if not row:
            return None
        attempts = int(row.get("attempts") or 0) + 1
        conn.execute(
            text(
                """
                UPDATE intel_ingest_jobs
                SET status = 'running',
                    attempts = :attempts,
                    updated_at = now()
                WHERE job_id = :job_id
                """
            ),
            {"job_id": row["job_id"], "attempts": attempts},
        )
        updated = dict(row)
        updated["attempts"] = attempts
        updated["status"] = "running"
        updated["enrich"] = row.get("status") != "queued_no_enrich"
        return updated


def update_job_status(
    engine: Engine,
    *,
    job_id: Any,
    status: str,
    last_error: Optional[str] = None,
    attempts: Optional[int] = None,
) -> None:
    updates: Dict[str, Any] = {"status": status, "updated_at": text("now()"), "last_error": last_error}
    if attempts is not None:
        updates["attempts"] = attempts
    with engine.begin() as conn:
        conn.execute(intel_ingest_jobs.update().where(intel_ingest_jobs.c.job_id == job_id).values(**updates))


def mark_article_extracted(
    engine: Engine,
    *,
    article_id: str,
    title: Optional[str],
    author: Optional[str],
    published_at: Optional[Any],
    extracted_text: Optional[str],
    raw_html: Optional[str],
    http_status: Optional[int],
    content_type: Optional[str],
    etag: Optional[str],
    last_modified: Optional[str],
    fetch_meta: Optional[Dict[str, Any]],
    extraction_meta: Optional[Dict[str, Any]],
    outline: Optional[List[Dict[str, Any]]],
) -> None:
    updates: Dict[str, Any] = {
        "title": title or "",
        "author": author,
        "published_at": published_at,
        "extracted_text": extracted_text,
        "raw_html": raw_html,
        "http_status": http_status,
        "content_type": content_type,
        "etag": etag,
        "last_modified": last_modified,
        "fetch_meta": fetch_meta,
        "extraction_meta": extraction_meta,
        "outline": outline or [],
        "status": "extracted",
        "updated_at": text("now()"),
    }
    with engine.begin() as conn:
        conn.execute(intel_articles.update().where(intel_articles.c.article_id == article_id).values(**updates))


def mark_article_enriched(
    engine: Engine,
    *,
    article_id: str,
    summary: str,
    signals: List[Dict[str, Any]],
    topics: List[str],
    enrichment_meta: Optional[Dict[str, Any]],
    outline: Optional[List[Dict[str, Any]]] = None,
    status: str = "enriched",
) -> None:
    updates: Dict[str, Any] = {
        "summary": summary,
        "signals": signals,
        "topics": topics,
        "enrichment_meta": enrichment_meta,
        "status": status,
        "updated_at": text("now()"),
    }
    if outline is not None:
        updates["outline"] = outline
    with engine.begin() as conn:
        conn.execute(intel_articles.update().where(intel_articles.c.article_id == article_id).values(**updates))


def mark_article_failed(engine: Engine, *, article_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            intel_articles.update()
            .where(intel_articles.c.article_id == article_id)
            .values(status="failed", updated_at=text("now()"))
        )


def get_intel_article(engine: Engine, article_id: str) -> Optional[Dict[str, Any]]:
    with engine.begin() as conn:
        row = (
            conn.execute(select(intel_articles).where(intel_articles.c.article_id == article_id))
            .mappings()
            .first()
        )
        return dict(row) if row else None


def get_latest_job_error(engine: Engine, article_id: str) -> Optional[str]:
    sql = """
        SELECT last_error
        FROM intel_ingest_jobs
        WHERE article_id = :article_id AND last_error IS NOT NULL
        ORDER BY updated_at DESC
        LIMIT 1
    """
    with engine.begin() as conn:
        row = conn.execute(text(sql), {"article_id": article_id}).mappings().first()
    return str(row["last_error"]) if row and row.get("last_error") else None


def upsert_research_source(
    engine: Engine,
    *,
    source_id: str,
    topic_key: str,
    kind: str,
    name: str,
    base_url_original: str,
    base_url_canonical: str,
    enabled: bool,
    tags: List[str],
    poll_interval_minutes: int,
    rate_limit_per_hour: int,
    robots_mode: str,
    max_items_per_run: int,
    source_weight: float,
) -> Dict[str, Any]:
    with engine.begin() as conn:
        existing = conn.execute(
            select(research_sources.c.source_id).where(research_sources.c.source_id == source_id)
        ).mappings().first()
        source_stmt = pg_insert(research_sources).values(
            {
                "source_id": source_id,
                "topic_key": topic_key,
                "kind": kind,
                "name": name,
                "base_url_original": base_url_original,
                "base_url_canonical": base_url_canonical,
                "enabled": enabled,
                "tags": tags,
            }
        )
        source_stmt = source_stmt.on_conflict_do_update(
            index_elements=[research_sources.c.source_id],
            set_={
                "topic_key": source_stmt.excluded.topic_key,
                "kind": source_stmt.excluded.kind,
                "name": source_stmt.excluded.name,
                "base_url_original": source_stmt.excluded.base_url_original,
                "base_url_canonical": source_stmt.excluded.base_url_canonical,
                "enabled": source_stmt.excluded.enabled,
                "tags": source_stmt.excluded.tags,
                "updated_at": text("now()"),
            },
        )
        conn.execute(source_stmt)

        policy_stmt = pg_insert(research_source_policies).values(
            {
                "source_id": source_id,
                "poll_interval_minutes": poll_interval_minutes,
                "rate_limit_per_hour": rate_limit_per_hour,
                "robots_mode": robots_mode,
                "max_items_per_run": max_items_per_run,
                "source_weight": source_weight,
            }
        )
        policy_stmt = policy_stmt.on_conflict_do_update(
            index_elements=[research_source_policies.c.source_id],
            set_={
                "poll_interval_minutes": policy_stmt.excluded.poll_interval_minutes,
                "rate_limit_per_hour": policy_stmt.excluded.rate_limit_per_hour,
                "robots_mode": policy_stmt.excluded.robots_mode,
                "max_items_per_run": policy_stmt.excluded.max_items_per_run,
                "source_weight": policy_stmt.excluded.source_weight,
                "updated_at": text("now()"),
            },
        )
        conn.execute(policy_stmt)

    return {"source_id": source_id, "status": "created" if existing is None else "updated"}


def list_research_sources(
    engine: Engine,
    *,
    topic_key: str,
    source_ids: Optional[List[str]] = None,
    enabled_only: bool = True,
) -> List[Dict[str, Any]]:
    stmt = (
        select(
            research_sources,
            research_source_policies.c.poll_interval_minutes,
            research_source_policies.c.rate_limit_per_hour,
            research_source_policies.c.robots_mode,
            research_source_policies.c.max_items_per_run,
            research_source_policies.c.source_weight,
            research_source_policies.c.last_polled_at,
            research_source_policies.c.consecutive_failures,
            research_source_policies.c.cooldown_until,
            research_source_policies.c.last_error,
        )
        .join(
            research_source_policies,
            research_source_policies.c.source_id == research_sources.c.source_id,
        )
        .where(research_sources.c.topic_key == topic_key)
    )
    if enabled_only:
        stmt = stmt.where(research_sources.c.enabled.is_(True))
    if source_ids:
        stmt = stmt.where(research_sources.c.source_id.in_(source_ids))
    stmt = stmt.order_by(research_sources.c.created_at.asc())
    with engine.begin() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [dict(row) for row in rows]


def set_research_source_polled(
    engine: Engine,
    *,
    source_id: str,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            research_source_policies.update()
            .where(research_source_policies.c.source_id == source_id)
            .values(last_polled_at=text("now()"), updated_at=text("now()"))
        )


def get_research_source_policy(
    engine: Engine,
    *,
    source_id: str,
) -> Optional[Dict[str, Any]]:
    stmt = select(research_source_policies).where(research_source_policies.c.source_id == source_id)
    with engine.begin() as conn:
        row = conn.execute(stmt).mappings().first()
    return dict(row) if row else None


def mark_research_source_success(
    engine: Engine,
    *,
    source_id: str,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            research_source_policies.update()
            .where(research_source_policies.c.source_id == source_id)
            .values(
                last_polled_at=text("now()"),
                consecutive_failures=0,
                cooldown_until=None,
                last_error=None,
                updated_at=text("now()"),
            )
        )


def mark_research_source_failure(
    engine: Engine,
    *,
    source_id: str,
    error: str,
    failure_threshold: int,
    cooldown_minutes: int,
) -> None:
    policy = get_research_source_policy(engine, source_id=source_id)
    current_failures = int((policy or {}).get("consecutive_failures") or 0)
    next_failures = current_failures + 1
    values: Dict[str, Any] = {
        "last_polled_at": text("now()"),
        "consecutive_failures": next_failures,
        "last_error": error[:500],
        "updated_at": text("now()"),
    }
    if next_failures >= max(failure_threshold, 1):
        values["cooldown_until"] = text(f"now() + interval '{max(cooldown_minutes, 1)} minutes'")
    else:
        values["cooldown_until"] = None
    with engine.begin() as conn:
        conn.execute(
            research_source_policies.update()
            .where(research_source_policies.c.source_id == source_id)
            .values(**values)
        )


def get_research_ingestion_run_by_idempotency(
    engine: Engine,
    *,
    topic_key: str,
    idempotency_key: str,
) -> Optional[Dict[str, Any]]:
    stmt = (
        select(research_ingestion_runs)
        .where(research_ingestion_runs.c.topic_key == topic_key)
        .where(research_ingestion_runs.c.idempotency_key == idempotency_key)
        .order_by(research_ingestion_runs.c.created_at.desc())
        .limit(1)
    )
    with engine.begin() as conn:
        row = conn.execute(stmt).mappings().first()
    return dict(row) if row else None


def create_research_ingestion_run(
    engine: Engine,
    *,
    topic_key: str,
    trigger: str,
    requested_source_ids: List[str],
    selected_source_ids: List[str],
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    run_id = uuid.uuid4()
    with engine.begin() as conn:
        row = conn.execute(
            research_ingestion_runs.insert()
            .values(
                {
                    "run_id": run_id,
                    "topic_key": topic_key,
                    "trigger": trigger,
                    "status": "queued",
                    "idempotency_key": idempotency_key,
                    "requested_source_ids": requested_source_ids,
                    "selected_source_ids": selected_source_ids,
                }
            )
            .returning(research_ingestion_runs)
        ).mappings().first()
    return dict(row) if row else {"run_id": str(run_id), "status": "queued"}


def get_research_ingestion_run(
    engine: Engine,
    *,
    run_id: str,
) -> Optional[Dict[str, Any]]:
    stmt = select(research_ingestion_runs).where(research_ingestion_runs.c.run_id == run_id)
    with engine.begin() as conn:
        row = conn.execute(stmt).mappings().first()
    return dict(row) if row else None


def has_open_research_run_for_topic(
    engine: Engine,
    *,
    topic_key: str,
    trigger: str,
) -> bool:
    sql = """
        SELECT 1
        FROM research_ingestion_runs
        WHERE topic_key = :topic_key
          AND trigger = :trigger
          AND status IN ('queued', 'running')
        LIMIT 1
    """
    with engine.begin() as conn:
        row = conn.execute(text(sql), {"topic_key": topic_key, "trigger": trigger}).first()
    return row is not None


def claim_next_research_ingestion_run(engine: Engine) -> Optional[Dict[str, Any]]:
    sql_select = """
        SELECT *
        FROM research_ingestion_runs
        WHERE status = 'queued'
        ORDER BY created_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    """
    with engine.begin() as conn:
        row = conn.execute(text(sql_select)).mappings().first()
        if not row:
            return None
        conn.execute(
            text(
                """
                UPDATE research_ingestion_runs
                SET status = 'running',
                    started_at = COALESCE(started_at, now()),
                    updated_at = now()
                WHERE run_id = :run_id
                """
            ),
            {"run_id": row["run_id"]},
        )
        updated = dict(row)
        updated["status"] = "running"
        return updated


def update_research_run_counters(
    engine: Engine,
    *,
    run_id: Any,
    items_seen: int = 0,
    items_new: int = 0,
    items_deduped: int = 0,
    items_failed: int = 0,
) -> None:
    sql = """
        UPDATE research_ingestion_runs
        SET items_seen = items_seen + :items_seen,
            items_new = items_new + :items_new,
            items_deduped = items_deduped + :items_deduped,
            items_failed = items_failed + :items_failed,
            updated_at = now()
        WHERE run_id = :run_id
    """
    with engine.begin() as conn:
        conn.execute(
            text(sql),
            {
                "run_id": run_id,
                "items_seen": max(items_seen, 0),
                "items_new": max(items_new, 0),
                "items_deduped": max(items_deduped, 0),
                "items_failed": max(items_failed, 0),
            },
        )


def append_research_run_error(
    engine: Engine,
    *,
    run_id: Any,
    message: str,
    max_errors: int = 20,
) -> None:
    run = get_research_ingestion_run(engine, run_id=str(run_id))
    if not run:
        return
    errors = run.get("errors") or []
    if not isinstance(errors, list):
        errors = []
    errors.append(message[:500])
    if len(errors) > max_errors:
        errors = errors[-max_errors:]
    with engine.begin() as conn:
        conn.execute(
            research_ingestion_runs.update()
            .where(research_ingestion_runs.c.run_id == run_id)
            .values(errors=errors, updated_at=text("now()"))
        )


def mark_research_ingestion_run_finished(
    engine: Engine,
    *,
    run_id: Any,
    status: str,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            research_ingestion_runs.update()
            .where(research_ingestion_runs.c.run_id == run_id)
            .values(status=status, finished_at=text("now()"), updated_at=text("now()"))
        )


def upsert_research_document_seed(
    engine: Engine,
    *,
    document_id: str,
    source_id: str,
    run_id: Any,
    canonical_url: str,
    url_original: Optional[str],
    external_id: Optional[str] = None,
) -> str:
    with engine.begin() as conn:
        existing = conn.execute(
            select(research_documents.c.document_id, research_documents.c.status).where(
                research_documents.c.document_id == document_id
            )
        ).mappings().first()
        if not existing:
            conn.execute(
                research_documents.insert().values(
                    {
                        "document_id": document_id,
                        "source_id": source_id,
                        "run_id": run_id,
                        "canonical_url": canonical_url,
                        "url_original": url_original,
                        "external_id": external_id,
                        "status": "discovered",
                    }
                )
            )
            return "new"
        status = str(existing.get("status") or "discovered")
        if status in {"failed", "discovered"}:
            conn.execute(
                research_documents.update()
                .where(research_documents.c.document_id == document_id)
                .values(status="discovered", run_id=run_id, updated_at=text("now()"))
            )
            return "retry"
        return "deduped"


def mark_research_document_fetched(
    engine: Engine,
    *,
    document_id: str,
    title: Optional[str],
    raw_payload: str,
    content_hash: str,
    fetch_meta: Dict[str, Any],
) -> None:
    with engine.begin() as conn:
        conn.execute(
            research_documents.update()
            .where(research_documents.c.document_id == document_id)
            .values(
                title=title,
                raw_payload=raw_payload,
                content_hash=content_hash,
                fetch_meta=fetch_meta,
                status="fetched",
                fetched_at=text("now()"),
                updated_at=text("now()"),
            )
        )


def mark_research_document_extracted(
    engine: Engine,
    *,
    document_id: str,
    extracted_text: str,
    extraction_meta: Dict[str, Any],
    published_at: Optional[Any] = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            research_documents.update()
            .where(research_documents.c.document_id == document_id)
            .values(
                extracted_text=extracted_text,
                extraction_meta=extraction_meta,
                published_at=published_at,
                status="extracted",
                extracted_at=text("now()"),
                updated_at=text("now()"),
            )
        )


def replace_research_chunks(
    engine: Engine,
    *,
    document_id: str,
    chunks: List[Dict[str, Any]],
) -> None:
    rows: List[Dict[str, Any]] = []
    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id") or "").strip()
        content = str(chunk.get("content") or "").strip()
        if not chunk_id or not content:
            continue
        rows.append(
            {
                "document_id": document_id,
                "chunk_id": chunk_id,
                "ordinal": int(chunk.get("ordinal") or 0),
                "content": content,
                "content_hash": str(chunk.get("content_hash") or ""),
            }
        )
    rows.sort(key=lambda item: (item["ordinal"], item["chunk_id"]))
    with engine.begin() as conn:
        conn.execute(
            research_chunks.delete().where(research_chunks.c.document_id == document_id)
        )
        if rows:
            conn.execute(research_chunks.insert(), rows)


def replace_research_embeddings(
    engine: Engine,
    *,
    document_id: str,
    embedding_model_id: str,
    embeddings: List[Dict[str, Any]],
) -> None:
    rows: List[Dict[str, Any]] = []
    for item in embeddings:
        chunk_id = str(item.get("chunk_id") or "").strip()
        vector = item.get("vector")
        if not chunk_id or not isinstance(vector, list) or not vector:
            continue
        rows.append(
            {
                "document_id": document_id,
                "chunk_id": chunk_id,
                "embedding_model_id": embedding_model_id,
                "vector": vector,
            }
        )
    with engine.begin() as conn:
        conn.execute(
            research_embeddings.delete()
            .where(research_embeddings.c.document_id == document_id)
            .where(research_embeddings.c.embedding_model_id == embedding_model_id)
        )
        if rows:
            conn.execute(research_embeddings.insert(), rows)


def mark_research_document_embedded(
    engine: Engine,
    *,
    document_id: str,
    embedding_model_id: str,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            research_documents.update()
            .where(research_documents.c.document_id == document_id)
            .values(
                embedding_model_id=embedding_model_id,
                status="embedded",
                embedded_at=text("now()"),
                updated_at=text("now()"),
            )
        )


def mark_research_document_failed(
    engine: Engine,
    *,
    document_id: str,
    fetch_meta: Optional[Dict[str, Any]] = None,
) -> None:
    values: Dict[str, Any] = {"status": "failed", "updated_at": text("now()")}
    if fetch_meta is not None:
        values["fetch_meta"] = fetch_meta
    with engine.begin() as conn:
        conn.execute(
            research_documents.update()
            .where(research_documents.c.document_id == document_id)
            .values(**values)
        )


def get_research_document(
    engine: Engine,
    *,
    document_id: str,
) -> Optional[Dict[str, Any]]:
    with engine.begin() as conn:
        row = conn.execute(
            select(research_documents).where(research_documents.c.document_id == document_id)
        ).mappings().first()
    return dict(row) if row else None


def list_due_research_sources(engine: Engine) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            s.source_id,
            s.topic_key,
            s.kind,
            s.name,
            s.base_url_original,
            s.base_url_canonical,
            s.enabled,
            s.tags,
            p.poll_interval_minutes,
            p.rate_limit_per_hour,
            p.robots_mode,
            p.max_items_per_run,
            p.source_weight,
            p.last_polled_at
        FROM research_sources s
        JOIN research_source_policies p
          ON p.source_id = s.source_id
        WHERE s.enabled = true
          AND (
            p.cooldown_until IS NULL
            OR p.cooldown_until <= now()
          )
          AND (
            p.last_polled_at IS NULL
            OR now() - p.last_polled_at >= (p.poll_interval_minutes * interval '1 minute')
          )
        ORDER BY s.topic_key ASC, s.created_at ASC
    """
    with engine.begin() as conn:
        rows = conn.execute(text(sql)).mappings().all()
    return [dict(row) for row in rows]


def count_research_documents(
    engine: Engine,
    *,
    source_id: str,
) -> int:
    sql = """
        SELECT count(*) AS c
        FROM research_documents
        WHERE source_id = :source_id
    """
    with engine.begin() as conn:
        row = conn.execute(text(sql), {"source_id": source_id}).mappings().first()
    return int(row["c"]) if row else 0


def count_research_documents_by_status(
    engine: Engine,
    *,
    source_id: str,
    status: str,
) -> int:
    sql = """
        SELECT count(*) AS c
        FROM research_documents
        WHERE source_id = :source_id
          AND status = :status
    """
    with engine.begin() as conn:
        row = conn.execute(text(sql), {"source_id": source_id, "status": status}).mappings().first()
    return int(row["c"]) if row else 0


def count_research_chunks(
    engine: Engine,
    *,
    document_id: str,
) -> int:
    sql = """
        SELECT count(*) AS c
        FROM research_chunks
        WHERE document_id = :document_id
    """
    with engine.begin() as conn:
        row = conn.execute(text(sql), {"document_id": document_id}).mappings().first()
    return int(row["c"]) if row else 0


def count_research_embeddings(
    engine: Engine,
    *,
    document_id: str,
    embedding_model_id: str,
) -> int:
    sql = """
        SELECT count(*) AS c
        FROM research_embeddings
        WHERE document_id = :document_id
          AND embedding_model_id = :embedding_model_id
    """
    with engine.begin() as conn:
        row = conn.execute(
            text(sql),
            {"document_id": document_id, "embedding_model_id": embedding_model_id},
        ).mappings().first()
    return int(row["c"]) if row else 0


def list_research_documents(
    engine: Engine,
    *,
    source_id: str,
) -> List[Dict[str, Any]]:
    stmt = (
        select(research_documents)
        .where(research_documents.c.source_id == source_id)
        .order_by(research_documents.c.created_at.asc())
    )
    with engine.begin() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [dict(row) for row in rows]


def search_research_chunks(
    engine: Engine,
    *,
    topic_key: str,
    query: str,
    source_ids: Optional[List[str]] = None,
    recency_days: Optional[int] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    if not query.strip():
        return []
    params: Dict[str, Any] = {
        "topic_key": topic_key,
        "query": query,
        "limit": max(limit, 1),
    }
    sql = """
        SELECT
            d.document_id,
            d.source_id,
            d.title,
            d.canonical_url,
            d.published_at,
            p.source_weight,
            c.chunk_id,
            c.ordinal,
            c.content,
            ts_rank(
                to_tsvector('english', coalesce(c.content, '') || ' ' || coalesce(d.title, '')),
                plainto_tsquery('english', :query)
            ) AS lexical_score,
            ts_headline(
                'english',
                c.content,
                plainto_tsquery('english', :query),
                'MaxWords=35, MinWords=12, ShortWord=3'
            ) AS snippet
        FROM research_chunks c
        JOIN research_documents d
          ON d.document_id = c.document_id
        JOIN research_sources s
          ON s.source_id = d.source_id
        JOIN research_source_policies p
          ON p.source_id = d.source_id
        WHERE s.topic_key = :topic_key
          AND d.status IN ('embedded', 'extracted')
          AND to_tsvector('english', coalesce(c.content, '') || ' ' || coalesce(d.title, ''))
              @@ plainto_tsquery('english', :query)
    """
    if source_ids:
        placeholders: List[str] = []
        for idx, source_id in enumerate(source_ids):
            key = f"source_id_{idx}"
            placeholders.append(f":{key}")
            params[key] = source_id
        sql += f" AND d.source_id IN ({', '.join(placeholders)})"
    if recency_days is not None:
        sql += " AND coalesce(d.published_at, d.discovered_at) >= now() - (:recency_days * interval '1 day')"
        params["recency_days"] = max(recency_days, 0)
    sql += """
        ORDER BY lexical_score DESC, coalesce(d.published_at, d.discovered_at) DESC NULLS LAST, c.ordinal ASC
        LIMIT :limit
    """
    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]


def search_research_document_chunks(
    engine: Engine,
    *,
    document_id: str,
    query: str,
    limit: int,
) -> List[Dict[str, Any]]:
    if not query.strip():
        return []
    sql = """
        SELECT
            c.chunk_id,
            c.ordinal,
            ts_rank(
                to_tsvector('english', coalesce(c.content, '')),
                plainto_tsquery('english', :query)
            ) AS score,
            ts_headline(
                'english',
                c.content,
                plainto_tsquery('english', :query),
                'MaxWords=35, MinWords=12, ShortWord=3'
            ) AS snippet
        FROM research_chunks c
        WHERE c.document_id = :document_id
          AND to_tsvector('english', coalesce(c.content, '')) @@ plainto_tsquery('english', :query)
        ORDER BY score DESC, c.ordinal ASC
        LIMIT :limit
    """
    params = {
        "document_id": document_id,
        "query": query,
        "limit": max(limit, 1),
    }
    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]


def create_research_query_log(
    engine: Engine,
    *,
    trace_id: str,
    topic_key: str,
    query_text: str,
    source_ids: List[str],
    token_budget: Optional[int],
    max_items: Optional[int],
    recency_days: Optional[int],
    min_relevance_score: Optional[float],
    candidate_count: int,
    returned_document_ids: List[str],
    returned_chunk_ids: List[str],
    timing_ms: int,
    status: str = "ok",
    error: Optional[str] = None,
) -> str:
    query_log_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            research_query_logs.insert().values(
                {
                    "query_log_id": query_log_id,
                    "trace_id": trace_id,
                    "topic_key": topic_key,
                    "query_text": query_text[:500],
                    "source_ids": source_ids,
                    "token_budget": token_budget,
                    "max_items": max_items,
                    "recency_days": recency_days,
                    "min_relevance_score": min_relevance_score,
                    "candidate_count": max(candidate_count, 0),
                    "returned_document_ids": returned_document_ids,
                    "returned_chunk_ids": returned_chunk_ids,
                    "timing_ms": max(timing_ms, 0),
                    "status": status,
                    "error": error[:1000] if error else None,
                }
            )
        )
    return str(query_log_id)


def list_research_embeddings_for_documents(
    engine: Engine,
    *,
    document_ids: List[str],
    embedding_model_id: str,
) -> List[Dict[str, Any]]:
    if not document_ids:
        return []
    stmt = (
        select(research_embeddings)
        .where(research_embeddings.c.document_id.in_(document_ids))
        .where(research_embeddings.c.embedding_model_id == embedding_model_id)
    )
    with engine.begin() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [dict(row) for row in rows]


def insert_research_relevance_scores(
    engine: Engine,
    *,
    trace_id: str,
    topic_key: str,
    query_text: str,
    items: List[Dict[str, Any]],
) -> int:
    rows: List[Dict[str, Any]] = []
    for item in items:
        document_id = str(item.get("document_id") or "")
        chunk_id = str(item.get("chunk_id") or "")
        if not document_id or not chunk_id:
            continue
        rows.append(
            {
                "score_id": uuid.uuid4(),
                "trace_id": trace_id,
                "topic_key": topic_key,
                "query_text": query_text[:500],
                "document_id": document_id,
                "chunk_id": chunk_id,
                "score_total": float(item.get("score_total") or 0.0),
                "score_lexical": float(item.get("score_lexical") or 0.0),
                "score_embedding": float(item.get("score_embedding") or 0.0),
                "score_recency": float(item.get("score_recency") or 0.0),
                "score_source_weight": float(item.get("score_source_weight") or 0.0),
            }
        )
    if not rows:
        return 0
    with engine.begin() as conn:
        conn.execute(research_relevance_scores.insert(), rows)
    return len(rows)


def insert_research_retrieval_feedback(
    engine: Engine,
    *,
    trace_id: str,
    query_log_id: Optional[str],
    document_id: str,
    chunk_id: str,
    verdict: str,
    notes: Optional[str] = None,
) -> str:
    feedback_id = uuid.uuid4()
    query_log_uuid = None
    if query_log_id:
        try:
            query_log_uuid = uuid.UUID(query_log_id)
        except ValueError:
            query_log_uuid = None
    with engine.begin() as conn:
        conn.execute(
            research_retrieval_feedback.insert().values(
                {
                    "feedback_id": feedback_id,
                    "trace_id": trace_id,
                    "query_log_id": query_log_uuid,
                    "document_id": document_id,
                    "chunk_id": chunk_id,
                    "verdict": verdict,
                    "notes": notes[:2000] if notes else None,
                }
            )
        )
    return str(feedback_id)


def count_research_query_logs(
    engine: Engine,
    *,
    topic_key: str,
) -> int:
    sql = """
        SELECT count(*) AS c
        FROM research_query_logs
        WHERE topic_key = :topic_key
    """
    with engine.begin() as conn:
        row = conn.execute(text(sql), {"topic_key": topic_key}).mappings().first()
    return int(row["c"]) if row else 0


def count_research_feedback(
    engine: Engine,
    *,
    trace_id: str,
) -> int:
    sql = """
        SELECT count(*) AS c
        FROM research_retrieval_feedback
        WHERE trace_id = :trace_id
    """
    with engine.begin() as conn:
        row = conn.execute(text(sql), {"trace_id": trace_id}).mappings().first()
    return int(row["c"]) if row else 0


def get_research_ops_summary(
    engine: Engine,
    *,
    topic_key: str,
) -> Dict[str, Any]:
    sql = """
        WITH source_stats AS (
            SELECT
                count(*) AS sources_total,
                count(*) FILTER (WHERE s.enabled = true) AS sources_enabled,
                count(*) FILTER (
                    WHERE s.enabled = true
                      AND p.cooldown_until IS NOT NULL
                      AND p.cooldown_until > now()
                ) AS sources_in_cooldown
            FROM research_sources s
            JOIN research_source_policies p ON p.source_id = s.source_id
            WHERE s.topic_key = :topic_key
        ),
        doc_stats AS (
            SELECT
                count(*) AS documents_total,
                count(*) FILTER (WHERE d.status = 'embedded') AS documents_embedded,
                count(*) FILTER (WHERE d.status = 'failed') AS documents_failed
            FROM research_documents d
            JOIN research_sources s ON s.source_id = d.source_id
            WHERE s.topic_key = :topic_key
        ),
        run_stats AS (
            SELECT
                count(*) FILTER (WHERE status IN ('queued', 'running')) AS runs_open,
                count(*) FILTER (WHERE status = 'failed' AND created_at >= now() - interval '24 hours') AS runs_failed_24h,
                CASE
                    WHEN count(*) FILTER (WHERE created_at >= now() - interval '24 hours') = 0 THEN 0.0
                    ELSE (
                        count(*) FILTER (
                            WHERE status = 'failed'
                              AND created_at >= now() - interval '24 hours'
                        )::float
                        / count(*) FILTER (WHERE created_at >= now() - interval '24 hours')::float
                    )
                END AS run_failure_rate_24h
            FROM research_ingestion_runs
            WHERE topic_key = :topic_key
        ),
        query_stats AS (
            SELECT
                count(*) FILTER (WHERE created_at >= now() - interval '24 hours') AS retrieval_queries_24h,
                count(*) FILTER (
                    WHERE status = 'error'
                      AND created_at >= now() - interval '24 hours'
                ) AS retrieval_errors_24h
            FROM research_query_logs
            WHERE topic_key = :topic_key
        )
        SELECT *
        FROM source_stats, doc_stats, run_stats, query_stats
    """
    with engine.begin() as conn:
        row = conn.execute(text(sql), {"topic_key": topic_key}).mappings().first()
    return dict(row) if row else {}
