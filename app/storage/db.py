from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import hashlib
import re
import uuid
from collections import Counter
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.storage.schema import (
    intel_article_sections,
    intel_articles,
    intel_ingest_jobs,
    projects,
    research_decision_feedback,
    research_digest_feedback,
    research_document_insights,
    research_evidence_relations,
    research_documents,
    research_chunks,
    research_bootstrap_events,
    research_embeddings,
    research_ingestion_runs,
    research_relevance_scores,
    research_retrieval_feedback,
    research_query_logs,
    research_source_policies,
    research_sources,
    tasks,
)


def _list_text(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    items: List[str] = []
    for item in value:
        text_value = str(item).strip()
        if text_value:
            items.append(text_value)
    return items


def _strip_nul_from_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [_strip_nul_from_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _strip_nul_from_value(item) for key, item in value.items()}
    return value


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


def list_projects_page(
    engine: Engine,
    *,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    stmt = (
        select(projects)
        .order_by(projects.c.updated_at.desc().nullslast(), projects.c.name.asc())
        .limit(max(limit, 1))
    )
    with engine.begin() as conn:
        rows = conn.execute(stmt).mappings().all()
    return [dict(row) for row in rows]


def list_tasks_with_projects(
    engine: Engine,
    *,
    limit: int = 1000,
    project_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    stmt = (
        select(
            tasks,
            projects.c.name.label("project_name"),
            projects.c.status.label("project_status"),
            projects.c.updated_at.label("project_updated_at"),
        )
        .select_from(tasks.outerjoin(projects, tasks.c.project_id == projects.c.project_id))
        .order_by(tasks.c.updated_at.desc().nullslast(), tasks.c.title.asc())
        .limit(max(limit, 1))
    )
    if project_id:
        stmt = stmt.where(tasks.c.project_id == project_id)
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
    publisher_type: str,
    source_class: str,
    default_decision_domains: List[str],
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
                "publisher_type": publisher_type,
                "source_class": source_class,
                "default_decision_domains": default_decision_domains,
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
                "publisher_type": source_stmt.excluded.publisher_type,
                "source_class": source_stmt.excluded.source_class,
                "default_decision_domains": source_stmt.excluded.default_decision_domains,
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


def set_research_source_enabled(
    engine: Engine,
    *,
    source_id: str,
    enabled: bool,
) -> bool:
    with engine.begin() as conn:
        result = conn.execute(
            research_sources.update()
            .where(research_sources.c.source_id == source_id)
            .values(enabled=enabled, updated_at=text("now()"))
        )
    return int(result.rowcount or 0) > 0


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


def fail_stale_research_ingestion_runs(
    engine: Engine,
    *,
    stale_after_seconds: int = 300,
) -> int:
    threshold = max(int(stale_after_seconds), 60)
    sql = """
        UPDATE research_ingestion_runs
        SET status = 'failed',
            finished_at = now(),
            updated_at = now(),
            errors = coalesce(errors, '[]'::jsonb) || jsonb_build_array(CAST(:message AS text))
        WHERE status = 'running'
          AND updated_at < now() - (:threshold_seconds * interval '1 second')
    """
    with engine.begin() as conn:
        result = conn.execute(
            text(sql),
            {
                "threshold_seconds": threshold,
                "message": f"run_failed error=stale_running_run idle_for_gt_{threshold}s",
            },
        )
    return int(result.rowcount or 0)


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
    published_at: Optional[Any] = None,
) -> None:
    normalized_published_at = published_at if published_at not in {"", "null", "None"} else None
    safe_title = _strip_nul_from_value(title)
    safe_raw_payload = _strip_nul_from_value(raw_payload)
    safe_fetch_meta = _strip_nul_from_value(fetch_meta)
    with engine.begin() as conn:
        conn.execute(
            research_documents.update()
            .where(research_documents.c.document_id == document_id)
            .values(
                title=safe_title,
                raw_payload=safe_raw_payload,
                content_hash=content_hash,
                fetch_meta=safe_fetch_meta,
                published_at=normalized_published_at,
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
    summary_short: Optional[str] = None,
) -> None:
    normalized_published_at = published_at if published_at not in {"", "null", "None"} else None
    safe_extracted_text = _strip_nul_from_value(extracted_text)
    safe_summary = _strip_nul_from_value(summary_short)
    safe_extraction_meta = _strip_nul_from_value(extraction_meta)
    with engine.begin() as conn:
        conn.execute(
            research_documents.update()
            .where(research_documents.c.document_id == document_id)
            .values(
                extracted_text=safe_extracted_text,
                extraction_meta=safe_extraction_meta,
                published_at=normalized_published_at,
                summary_short=safe_summary if safe_summary is not None else safe_extracted_text[:320],
                status="extracted",
                extracted_at=text("now()"),
                updated_at=text("now()"),
            )
        )


def mark_research_document_enriched(
    engine: Engine,
    *,
    document_id: str,
    enrichment: Dict[str, Any],
) -> None:
    allowed = {
        "content_type",
        "publisher_type",
        "source_class",
        "summary_short",
        "why_it_matters",
        "topic_tags",
        "entity_tags",
        "use_case_tags",
        "decision_domains",
        "quality_signals",
        "metrics",
        "notable_quotes",
        "key_claims",
        "tradeoffs",
        "recommendations",
        "novelty_score",
        "evidence_density_score",
        "document_signal_score",
        "embedding_ready",
        "published_at_confidence",
        "enrichment_meta",
        "quality_signals",
    }
    values = {key: enrichment[key] for key in allowed if key in enrichment}
    values["status"] = "enriched"
    values["updated_at"] = text("now()")
    with engine.begin() as conn:
        conn.execute(
            research_documents.update()
            .where(research_documents.c.document_id == document_id)
            .values(**values)
        )


def replace_research_document_insights(
    engine: Engine,
    *,
    document_id: str,
    insights: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for insight in insights:
        text_value = str(insight.get("text") or "").strip()
        chunk_id = str(insight.get("chunk_id") or "").strip()
        insight_type = str(insight.get("insight_type") or "").strip()
        if not text_value or not chunk_id or not insight_type:
            continue
        rows.append(
            {
                "insight_id": uuid.uuid4(),
                "document_id": document_id,
                "chunk_id": chunk_id,
                "insight_type": insight_type,
                "text": text_value,
                "normalized_payload": insight.get("normalized_payload") or {},
                "topic_tags": insight.get("topic_tags") or [],
                "entity_tags": insight.get("entity_tags") or [],
                "problem_tags": insight.get("problem_tags") or [],
                "intervention_tags": insight.get("intervention_tags") or [],
                "tradeoff_dimensions": insight.get("tradeoff_dimensions") or [],
                "decision_domains": insight.get("decision_domains") or [],
                "source_class": str(insight.get("source_class") or "external_commentary"),
                "publisher_type": str(insight.get("publisher_type") or "independent"),
                "confidence": float(insight.get("confidence") or 0.0),
                "evidence_strength": float(insight.get("evidence_strength") or 0.0),
                "freshness_score": float(insight.get("freshness_score") or 0.0),
                "applicability_conditions": insight.get("applicability_conditions") or [],
                "source_trust_tier": float(insight.get("source_trust_tier") or 0.0),
                "corroboration_count": int(insight.get("corroboration_count") or 0),
                "contradiction_count": int(insight.get("contradiction_count") or 0),
                "coverage_score": float(insight.get("coverage_score") or 0.0),
                "internal_coverage_score": float(insight.get("internal_coverage_score") or 0.0),
                "external_coverage_score": float(insight.get("external_coverage_score") or 0.0),
                "evidence_quality": float(insight.get("evidence_quality") or 0.0),
                "staleness_flag": bool(insight.get("staleness_flag") or False),
                "superseded_flag": bool(insight.get("superseded_flag") or False),
            }
        )
    with engine.begin() as conn:
        conn.execute(
            research_document_insights.delete().where(research_document_insights.c.document_id == document_id)
        )
        if rows:
            conn.execute(research_document_insights.insert(), rows)
    return rows


def replace_research_evidence_relations(
    engine: Engine,
    *,
    relations: List[Dict[str, Any]],
) -> int:
    relation_rows: List[Dict[str, Any]] = []
    touched_ids: set[uuid.UUID] = set()
    for relation in relations:
        from_id = relation.get("from_insight_id")
        to_id = relation.get("to_insight_id")
        relation_type = str(relation.get("relation_type") or "").strip()
        if not from_id or not to_id or not relation_type:
            continue
        from_uuid = from_id if isinstance(from_id, uuid.UUID) else uuid.UUID(str(from_id))
        to_uuid = to_id if isinstance(to_id, uuid.UUID) else uuid.UUID(str(to_id))
        touched_ids.add(from_uuid)
        touched_ids.add(to_uuid)
        relation_rows.append(
            {
                "relation_id": uuid.uuid4(),
                "from_insight_id": from_uuid,
                "to_insight_id": to_uuid,
                "relation_type": relation_type,
                "confidence": float(relation.get("confidence") or 0.0),
                "explanation": (str(relation.get("explanation") or "").strip() or None),
            }
        )
    with engine.begin() as conn:
        if touched_ids:
            conn.execute(
                research_evidence_relations.delete().where(
                    research_evidence_relations.c.from_insight_id.in_(list(touched_ids))
                    | research_evidence_relations.c.to_insight_id.in_(list(touched_ids))
                )
            )
        if relation_rows:
            conn.execute(research_evidence_relations.insert(), relation_rows)
    return len(relation_rows)


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
                "chunk_meta": chunk.get("chunk_meta") or {},
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


def set_research_document_suppressed(
    engine: Engine,
    *,
    document_id: str,
    suppressed: bool,
    reason: Optional[str] = None,
) -> bool:
    safe_reason = (reason or "").strip() or None
    with engine.begin() as conn:
        existing = conn.execute(
            select(research_documents.c.document_id).where(research_documents.c.document_id == document_id)
        ).first()
        if not existing:
            return False
        if suppressed:
            conn.execute(
                research_chunks.delete().where(research_chunks.c.document_id == document_id)
            )
            conn.execute(
                research_embeddings.delete().where(research_embeddings.c.document_id == document_id)
            )
            conn.execute(
                research_document_insights.delete().where(research_document_insights.c.document_id == document_id)
            )
            conn.execute(
                research_documents.update()
                .where(research_documents.c.document_id == document_id)
                .values(
                    suppressed=True,
                    suppression_reason=safe_reason,
                    suppressed_at=text("now()"),
                    embedding_ready=False,
                    embedding_model_id=None,
                    embedded_at=None,
                    status="suppressed",
                    updated_at=text("now()"),
                )
            )
        else:
            conn.execute(
                research_documents.update()
                .where(research_documents.c.document_id == document_id)
                .values(
                    suppressed=False,
                    suppression_reason=None,
                    suppressed_at=None,
                    status=text(
                        "CASE "
                        "WHEN coalesce(extracted_text, '') <> '' THEN 'extracted' "
                        "WHEN coalesce(raw_payload, '') <> '' THEN 'fetched' "
                        "ELSE 'discovered' END"
                    ),
                    updated_at=text("now()"),
                )
            )
    return True


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
    decision_domain: Optional[str] = None,
    content_types: Optional[List[str]] = None,
    source_classes: Optional[List[str]] = None,
    publisher_types: Optional[List[str]] = None,
    exclude_content_types: Optional[List[str]] = None,
    evidence_types: Optional[List[str]] = None,
    problem_tags: Optional[List[str]] = None,
    intervention_tags: Optional[List[str]] = None,
    tradeoff_dimensions: Optional[List[str]] = None,
    corpus_preference: str = "mixed",
    source_trust_min: Optional[float] = None,
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
            d.content_type,
            d.publisher_type,
            d.source_class,
            d.summary_short,
            d.why_it_matters,
            d.topic_tags,
            d.decision_domains,
            d.metrics,
            d.notable_quotes,
            d.tradeoffs,
            d.recommendations,
            d.document_signal_score,
            d.quality_signals,
            p.source_weight,
            c.chunk_id,
            c.ordinal,
            c.content,
            c.chunk_meta,
            coalesce(max(i.confidence), 0.0) AS insight_confidence,
            coalesce(max(i.evidence_quality), 0.0) AS evidence_quality,
            coalesce(max(i.corroboration_count), 0) AS corroboration_count,
            coalesce(max(i.contradiction_count), 0) AS contradiction_count,
            coalesce(max(i.freshness_score), 0.0) AS freshness_score,
            coalesce(max(i.coverage_score), 0.0) AS coverage_score,
            coalesce(array_agg(DISTINCT tag_problem.value) FILTER (WHERE tag_problem.value IS NOT NULL), ARRAY[]::text[]) AS problem_tags,
            coalesce(array_agg(DISTINCT tag_intervention.value) FILTER (WHERE tag_intervention.value IS NOT NULL), ARRAY[]::text[]) AS intervention_tags,
            coalesce(array_agg(DISTINCT tag_tradeoff.value) FILTER (WHERE tag_tradeoff.value IS NOT NULL), ARRAY[]::text[]) AS tradeoff_dimensions,
            ts_rank(
                to_tsvector(
                    'english',
                    coalesce(c.content, '') || ' ' ||
                    coalesce(d.title, '') || ' ' ||
                    coalesce(d.summary_short, '') || ' ' ||
                    coalesce(d.why_it_matters, '') || ' ' ||
                    coalesce(array_to_string(ARRAY(SELECT jsonb_array_elements_text(d.topic_tags)), ' '), '') || ' ' ||
                    coalesce(array_to_string(ARRAY(SELECT jsonb_array_elements_text(d.decision_domains)), ' '), '') || ' ' ||
                    coalesce(string_agg(i.text, ' '), '')
                ),
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
        LEFT JOIN research_document_insights i
          ON i.document_id = d.document_id
         AND i.chunk_id = c.chunk_id
        LEFT JOIN LATERAL jsonb_array_elements_text(coalesce(i.problem_tags, '[]'::jsonb)) AS tag_problem(value) ON TRUE
        LEFT JOIN LATERAL jsonb_array_elements_text(coalesce(i.intervention_tags, '[]'::jsonb)) AS tag_intervention(value) ON TRUE
        LEFT JOIN LATERAL jsonb_array_elements_text(coalesce(i.tradeoff_dimensions, '[]'::jsonb)) AS tag_tradeoff(value) ON TRUE
        WHERE s.topic_key = :topic_key
          AND d.status IN ('embedded', 'extracted', 'enriched')
          AND coalesce(d.suppressed, false) = false
          AND to_tsvector(
                'english',
                coalesce(c.content, '') || ' ' ||
                coalesce(d.title, '') || ' ' ||
                coalesce(d.summary_short, '') || ' ' ||
                coalesce(d.why_it_matters, '') || ' ' ||
                coalesce(array_to_string(ARRAY(SELECT jsonb_array_elements_text(d.topic_tags)), ' '), '') || ' ' ||
                coalesce(array_to_string(ARRAY(SELECT jsonb_array_elements_text(d.decision_domains)), ' '), '') || ' ' ||
                coalesce(i.text, '')
              )
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
    if decision_domain:
        sql += " AND d.decision_domains @> CAST(:decision_domains AS jsonb)"
        params["decision_domains"] = '["%s"]' % decision_domain.strip().lower()
    if content_types:
        placeholders = []
        for idx, value in enumerate(content_types):
            key = f"content_type_{idx}"
            placeholders.append(f":{key}")
            params[key] = value
        sql += f" AND d.content_type IN ({', '.join(placeholders)})"
    if source_classes:
        placeholders = []
        for idx, value in enumerate(source_classes):
            key = f"source_class_{idx}"
            placeholders.append(f":{key}")
            params[key] = value
        sql += f" AND d.source_class IN ({', '.join(placeholders)})"
    if publisher_types:
        placeholders = []
        for idx, value in enumerate(publisher_types):
            key = f"publisher_type_{idx}"
            placeholders.append(f":{key}")
            params[key] = value
        sql += f" AND d.publisher_type IN ({', '.join(placeholders)})"
    if exclude_content_types:
        placeholders = []
        for idx, value in enumerate(exclude_content_types):
            key = f"exclude_content_type_{idx}"
            placeholders.append(f":{key}")
            params[key] = value
        sql += f" AND d.content_type NOT IN ({', '.join(placeholders)})"
    if evidence_types:
        placeholders = []
        for idx, value in enumerate(evidence_types):
            key = f"evidence_type_{idx}"
            placeholders.append(f":{key}")
            params[key] = value
        sql += f" AND i.insight_type IN ({', '.join(placeholders)})"
    if problem_tags:
        clauses = []
        for idx, value in enumerate(problem_tags):
            key = f"problem_tag_{idx}"
            clauses.append(f"i.problem_tags @> CAST(:{key} AS jsonb)")
            params[key] = '["%s"]' % value
        sql += " AND (" + " OR ".join(clauses) + ")"
    if intervention_tags:
        clauses = []
        for idx, value in enumerate(intervention_tags):
            key = f"intervention_tag_{idx}"
            clauses.append(f"i.intervention_tags @> CAST(:{key} AS jsonb)")
            params[key] = '["%s"]' % value
        sql += " AND (" + " OR ".join(clauses) + ")"
    if tradeoff_dimensions:
        clauses = []
        for idx, value in enumerate(tradeoff_dimensions):
            key = f"tradeoff_dimension_{idx}"
            clauses.append(f"i.tradeoff_dimensions @> CAST(:{key} AS jsonb)")
            params[key] = '["%s"]' % value
        sql += " AND (" + " OR ".join(clauses) + ")"
    if corpus_preference == "internal":
        sql += " AND d.source_class LIKE 'internal_%'"
    elif corpus_preference == "external":
        sql += " AND d.source_class NOT LIKE 'internal_%'"
    if source_trust_min is not None:
        sql += """
          AND (
                CASE
                    WHEN d.source_class = 'internal_authoritative' THEN 1.0
                    WHEN d.source_class = 'external_primary' THEN 0.85
                    WHEN d.source_class = 'internal_working' THEN 0.75
                    WHEN d.source_class = 'external_secondary' THEN 0.65
                    ELSE 0.45
                END
              ) >= :source_trust_min
        """
        params["source_trust_min"] = max(min(source_trust_min, 1.0), 0.0)
    sql += """
        GROUP BY
            d.document_id, d.source_id, d.title, d.canonical_url, d.published_at, d.content_type,
            d.publisher_type, d.source_class, d.summary_short, d.why_it_matters, d.topic_tags,
            d.decision_domains, d.metrics, d.notable_quotes, d.tradeoffs, d.recommendations,
            d.document_signal_score, d.quality_signals, d.discovered_at, p.source_weight, c.chunk_id, c.ordinal, c.content, c.chunk_meta
        ORDER BY lexical_score DESC, coalesce(d.document_signal_score, 0.0) DESC, coalesce(d.published_at, d.discovered_at) DESC NULLS LAST, c.ordinal ASC
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
            c.chunk_meta,
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
        JOIN research_documents d
          ON d.document_id = c.document_id
        WHERE c.document_id = :document_id
          AND coalesce(d.suppressed, false) = false
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
        if not rows:
            fallback_sql = """
                SELECT
                    c.chunk_id,
                    c.ordinal,
                    c.chunk_meta,
                    NULL::float AS score,
                    left(c.content, 280) AS snippet
                FROM research_chunks c
                JOIN research_documents d
                  ON d.document_id = c.document_id
                WHERE c.document_id = :document_id
                  AND coalesce(d.suppressed, false) = false
                ORDER BY c.ordinal ASC
                LIMIT :limit
            """
            rows = conn.execute(text(fallback_sql), params).mappings().all()
    return [dict(row) for row in rows]


def list_research_topics(
    engine: Engine,
    *,
    query: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"limit": max(limit, 1)}
    sql = """
        SELECT
            s.topic_key,
            replace(initcap(replace(s.topic_key, '_', ' ')), ' Ai ', ' AI ') AS label,
            concat('Research corpus for ', replace(s.topic_key, '_', ' '), '.') AS description,
            count(DISTINCT s.source_id) AS source_count,
            count(DISTINCT d.document_id) AS document_count,
            count(DISTINCT CASE WHEN d.status = 'embedded' THEN d.document_id END) AS embedded_document_count,
            max(d.published_at) AS last_published_at,
            max(coalesce(d.embedded_at, d.extracted_at, d.discovered_at)) AS last_ingested_at
        FROM research_sources s
        LEFT JOIN research_documents d
          ON d.source_id = s.source_id
         AND coalesce(d.suppressed, false) = false
    """
    if query and query.strip():
        params["query"] = f"%{query.strip().lower()}%"
        sql += """
        WHERE lower(s.topic_key) LIKE :query
           OR lower(s.name) LIKE :query
           OR EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(s.tags) AS tag
                WHERE lower(tag) LIKE :query
           )
        """
    sql += """
        GROUP BY s.topic_key
        ORDER BY document_count DESC, source_count DESC, s.topic_key ASC
        LIMIT :limit
    """
    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]


def list_research_documents_for_topic(
    engine: Engine,
    *,
    topic_key: str,
    limit: int = 10,
    sort: str = "recent",
) -> List[Dict[str, Any]]:
    order_clause = (
        "coalesce(d.published_at, d.discovered_at) DESC NULLS LAST, d.updated_at DESC"
        if sort != "title"
        else "lower(coalesce(d.title, d.canonical_url)) ASC, d.updated_at DESC"
    )
    sql = f"""
        SELECT
            d.document_id,
            d.source_id,
            coalesce(d.title, d.canonical_url) AS title,
            d.canonical_url,
            d.published_at,
            coalesce(nullif(d.summary_short, ''), left(coalesce(d.extracted_text, ''), 320)) AS summary,
            d.content_type,
            d.publisher_type,
            d.source_class,
            d.topic_tags,
            d.decision_domains,
            d.metrics,
            d.notable_quotes
        FROM research_documents d
        JOIN research_sources s
          ON s.source_id = d.source_id
        WHERE s.topic_key = :topic_key
          AND d.status IN ('embedded', 'extracted', 'enriched')
          AND coalesce(d.suppressed, false) = false
        ORDER BY {order_clause}
        LIMIT :limit
    """
    with engine.begin() as conn:
        rows = conn.execute(text(sql), {"topic_key": topic_key, "limit": max(limit, 1)}).mappings().all()
    return [dict(row) for row in rows]


def list_research_documents_for_reembed(
    engine: Engine,
    *,
    topic_key: str,
    embedding_model_id: str,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            d.document_id,
            d.embedding_model_id,
            d.extracted_text
        FROM research_documents d
        JOIN research_sources s
          ON s.source_id = d.source_id
        WHERE s.topic_key = :topic_key
          AND d.status IN ('embedded', 'extracted')
          AND coalesce(d.suppressed, false) = false
          AND coalesce(d.extracted_text, '') <> ''
          AND coalesce(d.embedding_model_id, '') <> :embedding_model_id
        ORDER BY coalesce(d.embedded_at, d.extracted_at, d.discovered_at) ASC, d.document_id ASC
        LIMIT :limit
    """
    params = {
        "topic_key": topic_key,
        "embedding_model_id": embedding_model_id,
        "limit": max(limit, 1),
    }
    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]


def list_research_documents_for_enrichment_backfill(
    engine: Engine,
    *,
    topic_key: Optional[str] = None,
    limit: int = 1000,
    only_missing_reasoning_fields: bool = True,
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"limit": max(limit, 1)}
    sql = """
        SELECT
            d.document_id,
            d.source_id,
            d.canonical_url,
            d.title,
            d.extracted_text,
            d.fetch_meta,
            d.extraction_meta,
            d.published_at,
            d.status,
            s.name AS source_name,
            coalesce(s.publisher_type, 'independent') AS source_publisher_type,
            coalesce(s.source_class, 'external_primary') AS source_class,
            coalesce(s.default_decision_domains, '[]'::jsonb) AS default_decision_domains
        FROM research_documents d
        JOIN research_sources s
          ON s.source_id = d.source_id
        WHERE d.status IN ('embedded', 'extracted', 'enriched')
          AND coalesce(d.suppressed, false) = false
          AND coalesce(d.extracted_text, '') <> ''
    """
    if topic_key:
        sql += " AND s.topic_key = :topic_key"
        params["topic_key"] = topic_key
    if only_missing_reasoning_fields:
        sql += """
          AND (
                coalesce(jsonb_array_length(d.topic_tags), 0) = 0
                OR coalesce(jsonb_array_length(d.recommendations), 0) = 0
                OR coalesce(jsonb_array_length(d.tradeoffs), 0) = 0
                OR coalesce(jsonb_array_length(d.metrics), 0) = 0
                OR coalesce(jsonb_array_length(d.notable_quotes), 0) = 0
                OR coalesce(d.summary_short, '') = ''
                OR coalesce(d.why_it_matters, '') = ''
              )
        """
    sql += """
        ORDER BY coalesce(d.updated_at, d.embedded_at, d.extracted_at, d.discovered_at) ASC, d.document_id ASC
        LIMIT :limit
    """
    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]


def list_research_chunks_for_document(
    engine: Engine,
    *,
    document_id: str,
) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            chunk_id,
            document_id,
            ordinal,
            content,
            token_estimate,
            char_count,
            chunk_meta
        FROM research_chunks
        WHERE document_id = :document_id
        ORDER BY ordinal ASC
    """
    with engine.begin() as conn:
        rows = conn.execute(text(sql), {"document_id": document_id}).mappings().all()
    return [dict(row) for row in rows]


def list_research_source_metrics_for_topic(
    engine: Engine,
    *,
    topic_key: str,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    items = list_research_source_metrics(engine, topic_key=topic_key, limit=limit)
    return items[: max(limit, 1)]


_TOKEN_RE = re.compile(r"[a-z][a-z0-9_-]{3,}")
_STOPWORDS = {
    "about",
    "after",
    "agent",
    "agents",
    "architecture",
    "article",
    "best",
    "current",
    "engineering",
    "improved",
    "improving",
    "management",
    "patterns",
    "practice",
    "practices",
    "product",
    "research",
    "software",
    "systems",
    "teams",
    "using",
    "with",
}


def collect_research_topic_themes(
    engine: Engine,
    *,
    topic_key: str,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            d.title,
            d.topic_tags,
            d.decision_domains,
            c.chunk_meta,
            c.content
        FROM research_documents d
        JOIN research_sources s
          ON s.source_id = d.source_id
        LEFT JOIN research_chunks c
          ON c.document_id = d.document_id
        WHERE s.topic_key = :topic_key
          AND d.status IN ('embedded', 'extracted', 'enriched')
          AND coalesce(d.suppressed, false) = false
        ORDER BY coalesce(d.published_at, d.discovered_at) DESC NULLS LAST, c.ordinal ASC
        LIMIT 200
    """
    counts: Counter[str] = Counter()
    with engine.begin() as conn:
        rows = conn.execute(text(sql), {"topic_key": topic_key}).mappings().all()
    for row in rows:
        for tag in _list_text(row.get("topic_tags")) + _list_text(row.get("decision_domains")):
            normalized = tag.strip().lower()
            if normalized and normalized not in _STOPWORDS:
                counts[normalized] += 4
        chunk_meta = row.get("chunk_meta") or {}
        if isinstance(chunk_meta, dict):
            for heading in chunk_meta.get("heading_path") or []:
                normalized = str(heading).strip().lower()
                if normalized and normalized not in _STOPWORDS:
                    counts[normalized] += 3
            for tag in chunk_meta.get("tags") or []:
                normalized = str(tag).strip().lower()
                if normalized and normalized not in _STOPWORDS:
                    counts[normalized] += 2
        for field in (row.get("title"), row.get("content")):
            for token in _TOKEN_RE.findall(str(field or "").lower()):
                if token not in _STOPWORDS:
                    counts[token] += 1
    return [{"name": name.replace("_", " "), "score": float(score)} for name, score in counts.most_common(max(limit, 1))]


def get_research_topic_detail(
    engine: Engine,
    *,
    topic_key: str,
) -> Optional[Dict[str, Any]]:
    items = list_research_topics(engine, query=topic_key, limit=20)
    normalized = topic_key.strip().lower()
    for item in items:
        if str(item.get("topic_key") or "").strip().lower() == normalized:
            return item
    return None


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


def list_research_document_insights(
    engine: Engine,
    *,
    document_ids: Optional[List[str]] = None,
    topic_key: Optional[str] = None,
    decision_domain: Optional[str] = None,
    insight_types: Optional[List[str]] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"limit": max(limit, 1)}
    sql = """
        SELECT
            i.*,
            d.topic_tags,
            d.decision_domains,
            d.source_id,
            d.title,
            d.canonical_url,
            d.summary_short,
            d.why_it_matters,
            d.published_at,
            d.content_type,
            d.publisher_type,
            d.source_class
        FROM research_document_insights i
        JOIN research_documents d
          ON d.document_id = i.document_id
        JOIN research_sources s
          ON s.source_id = d.source_id
        WHERE coalesce(d.suppressed, false) = false
    """
    if topic_key:
        sql += " AND s.topic_key = :topic_key"
        params["topic_key"] = topic_key
    if document_ids:
        placeholders = []
        for idx, value in enumerate(document_ids):
            key = f"document_id_{idx}"
            placeholders.append(f":{key}")
            params[key] = value
        sql += f" AND i.document_id IN ({', '.join(placeholders)})"
    if decision_domain:
        sql += " AND d.decision_domains @> CAST(:decision_domains AS jsonb)"
        params["decision_domains"] = '["%s"]' % decision_domain.strip().lower()
    if insight_types:
        placeholders = []
        for idx, value in enumerate(insight_types):
            key = f"insight_type_{idx}"
            placeholders.append(f":{key}")
            params[key] = value
        sql += f" AND i.insight_type IN ({', '.join(placeholders)})"
    sql += " ORDER BY i.confidence DESC, d.published_at DESC NULLS LAST, i.created_at DESC LIMIT :limit"
    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]


def search_research_evidence(
    engine: Engine,
    *,
    topic_key: str,
    query: str,
    evidence_types: Optional[List[str]] = None,
    problem_tags: Optional[List[str]] = None,
    intervention_tags: Optional[List[str]] = None,
    tradeoff_dimensions: Optional[List[str]] = None,
    decision_domain: Optional[str] = None,
    corpus_preference: str = "mixed",
    source_trust_min: Optional[float] = None,
    recency_days: Optional[int] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    if not query.strip():
        return []
    rows = search_research_chunks(
        engine,
        topic_key=topic_key,
        query=query,
        recency_days=recency_days,
        decision_domain=decision_domain,
        evidence_types=evidence_types,
        problem_tags=problem_tags,
        intervention_tags=intervention_tags,
        tradeoff_dimensions=tradeoff_dimensions,
        corpus_preference=corpus_preference,
        source_trust_min=source_trust_min,
        limit=max(limit * 3, 10),
    )
    document_ids = sorted({str(row.get("document_id") or "") for row in rows if row.get("document_id")})
    insights = list_research_document_insights(
        engine,
        document_ids=document_ids or None,
        topic_key=topic_key,
        decision_domain=decision_domain,
        insight_types=evidence_types,
        limit=max(limit * 8, 25),
    )
    if not insights:
        return []
    scored: List[Dict[str, Any]] = []
    row_index: Dict[tuple[str, str], Dict[str, Any]] = {
        (str(row.get("document_id") or ""), str(row.get("chunk_id") or "")): row for row in rows
    }
    for insight in insights:
        key = (str(insight.get("document_id") or ""), str(insight.get("chunk_id") or ""))
        row = row_index.get(key, {})
        merged = dict(insight)
        merged["lexical_score"] = float(row.get("lexical_score") or 0.0)
        merged["evidence_quality"] = float(insight.get("evidence_quality") or row.get("evidence_quality") or 0.0)
        merged["coverage_score"] = float(insight.get("coverage_score") or row.get("coverage_score") or 0.0)
        merged["freshness_score"] = float(insight.get("freshness_score") or row.get("freshness_score") or 0.0)
        merged["corroboration_count"] = int(insight.get("corroboration_count") or row.get("corroboration_count") or 0)
        merged["contradiction_count"] = int(insight.get("contradiction_count") or row.get("contradiction_count") or 0)
        scored.append(merged)
    scored.sort(
        key=lambda item: (
            float(item.get("evidence_quality") or 0.0),
            float(item.get("confidence") or 0.0),
            float(item.get("lexical_score") or 0.0),
            float(item.get("freshness_score") or 0.0),
        ),
        reverse=True,
    )
    return scored[: max(limit, 1)]


def list_research_evidence_relations(
    engine: Engine,
    *,
    insight_ids: List[str],
    relation_types: Optional[List[str]] = None,
    direction: str = "both",
    limit: int = 100,
) -> List[Dict[str, Any]]:
    if not insight_ids:
        return []
    params: Dict[str, Any] = {"limit": max(limit, 1)}
    placeholders = []
    for idx, insight_id in enumerate(insight_ids):
        key = f"insight_id_{idx}"
        placeholders.append(f":{key}")
        params[key] = insight_id
    sql = """
        SELECT *
        FROM research_evidence_relations
        WHERE
    """
    if direction == "outgoing":
        sql += f" from_insight_id IN ({', '.join(placeholders)})"
    elif direction == "incoming":
        sql += f" to_insight_id IN ({', '.join(placeholders)})"
    else:
        sql += f" (from_insight_id IN ({', '.join(placeholders)}) OR to_insight_id IN ({', '.join(placeholders)}))"
        for idx, insight_id in enumerate(insight_ids):
            params[f"insight_id_{idx + len(insight_ids)}"] = insight_id
    if relation_types:
        rel_placeholders = []
        for idx, relation_type in enumerate(relation_types):
            key = f"relation_type_{idx}"
            rel_placeholders.append(f":{key}")
            params[key] = relation_type
        sql += f" AND relation_type IN ({', '.join(rel_placeholders)})"
    sql += " ORDER BY confidence DESC, created_at DESC LIMIT :limit"
    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]


def list_recent_research_documents(
    engine: Engine,
    *,
    topic_key: str,
    days: int,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            d.document_id,
            d.source_id,
            d.title,
            d.canonical_url,
            d.published_at,
            d.summary_short,
            d.why_it_matters,
            d.metrics,
            d.notable_quotes,
            d.topic_tags,
            d.decision_domains,
            d.content_type
        FROM research_documents d
        JOIN research_sources s
          ON s.source_id = d.source_id
        WHERE s.topic_key = :topic_key
          AND d.status IN ('embedded', 'extracted', 'enriched')
          AND coalesce(d.suppressed, false) = false
          AND coalesce(d.published_at, d.discovered_at) >= now() - (:days * interval '1 day')
        ORDER BY coalesce(d.published_at, d.discovered_at) DESC NULLS LAST, d.document_signal_score DESC, d.updated_at DESC
        LIMIT :limit
    """
    with engine.begin() as conn:
        rows = conn.execute(text(sql), {"topic_key": topic_key, "days": max(days, 1), "limit": max(limit, 1)}).mappings().all()
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
              AND coalesce(d.suppressed, false) = false
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


def list_research_source_metrics(
    engine: Engine,
    *,
    topic_key: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            s.source_id,
            s.name,
            s.enabled,
            p.last_polled_at,
            p.consecutive_failures,
            p.cooldown_until,
            p.last_error,
            count(d.document_id) AS documents_total,
            count(*) FILTER (WHERE d.status = 'embedded') AS documents_embedded,
            count(*) FILTER (WHERE d.status = 'failed') AS documents_failed,
            (
                SELECT count(*)
                FROM research_query_logs q
                WHERE q.topic_key = s.topic_key
                  AND q.created_at >= now() - interval '24 hours'
            ) AS retrieval_queries_24h
        FROM research_sources s
        JOIN research_source_policies p ON p.source_id = s.source_id
        LEFT JOIN research_documents d ON d.source_id = s.source_id
        WHERE s.topic_key = :topic_key
        GROUP BY
            s.source_id,
            s.name,
            s.enabled,
            p.last_polled_at,
            p.consecutive_failures,
            p.cooldown_until,
            p.last_error
        ORDER BY documents_total DESC, s.created_at ASC
        LIMIT :limit
    """
    params = {"topic_key": topic_key, "limit": max(limit, 1)}
    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]


def list_research_document_stage_counts(
    engine: Engine,
    *,
    topic_key: str,
) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            d.status,
            count(*) AS count
        FROM research_documents d
        JOIN research_sources s
          ON s.source_id = d.source_id
        WHERE s.topic_key = :topic_key
        GROUP BY d.status
        ORDER BY d.status ASC
    """
    with engine.begin() as conn:
        rows = conn.execute(text(sql), {"topic_key": topic_key}).mappings().all()
    return [dict(row) for row in rows]


def get_research_storage_usage(
    engine: Engine,
    *,
    topic_key: str,
) -> Dict[str, Any]:
    sql = """
        WITH docs AS (
            SELECT
                d.document_id,
                d.raw_payload,
                d.extracted_text
            FROM research_documents d
            JOIN research_sources s
              ON s.source_id = d.source_id
            WHERE s.topic_key = :topic_key
        ),
        chunks AS (
            SELECT
                c.document_id,
                c.chunk_id,
                c.content
            FROM research_chunks c
            JOIN docs d
              ON d.document_id = c.document_id
        ),
        embs AS (
            SELECT
                e.document_id,
                e.chunk_id,
                e.vector
            FROM research_embeddings e
            JOIN docs d
              ON d.document_id = e.document_id
        )
        SELECT
            (SELECT count(*) FROM docs) AS documents_count,
            (SELECT count(*) FROM chunks) AS chunks_count,
            (SELECT count(*) FROM embs) AS embeddings_count,
            (SELECT COALESCE(sum(octet_length(COALESCE(raw_payload, ''))), 0) FROM docs) AS raw_payload_bytes,
            (SELECT COALESCE(sum(octet_length(COALESCE(extracted_text, ''))), 0) FROM docs) AS extracted_text_bytes,
            (SELECT COALESCE(sum(octet_length(COALESCE(content, ''))), 0) FROM chunks) AS chunks_bytes,
            (SELECT COALESCE(sum(pg_column_size(vector)), 0) FROM embs) AS embeddings_bytes
    """
    with engine.begin() as conn:
        row = conn.execute(text(sql), {"topic_key": topic_key}).mappings().first()
    return dict(row or {})


def list_research_run_progress(
    engine: Engine,
    *,
    topic_key: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            r.run_id,
            r.trigger,
            r.status,
            r.created_at,
            r.started_at,
            r.finished_at,
            COALESCE(jsonb_array_length(r.selected_source_ids), 0) AS sources_selected,
            r.items_seen,
            r.items_new,
            r.items_deduped,
            r.items_failed
        FROM research_ingestion_runs r
        WHERE r.topic_key = :topic_key
        ORDER BY r.created_at DESC
        LIMIT :limit
    """
    with engine.begin() as conn:
        rows = conn.execute(text(sql), {"topic_key": topic_key, "limit": max(limit, 1)}).mappings().all()
    return [dict(row) for row in rows]


def get_research_pipeline_counts(
    engine: Engine,
    *,
    topic_key: str,
) -> Dict[str, Any]:
    sql = """
        WITH docs AS (
            SELECT
                d.document_id,
                d.status
            FROM research_documents d
            JOIN research_sources s
              ON s.source_id = d.source_id
            WHERE s.topic_key = :topic_key
        )
        SELECT
            count(*) AS documents_total,
            count(*) FILTER (WHERE d.status = 'discovered') AS discovered_count,
            count(*) FILTER (WHERE d.status = 'fetched') AS fetched_count,
            count(*) FILTER (WHERE d.status = 'extracted') AS extracted_count,
            count(*) FILTER (WHERE d.status = 'embedded') AS embedded_count,
            count(*) FILTER (WHERE d.status = 'failed') AS failed_count,
            (
                SELECT count(*)
                FROM research_chunks c
                JOIN docs d ON d.document_id = c.document_id
            ) AS chunks_count,
            (
                SELECT count(*)
                FROM research_embeddings e
                JOIN docs d ON d.document_id = e.document_id
            ) AS embeddings_count
        FROM docs d
    """
    with engine.begin() as conn:
        row = conn.execute(text(sql), {"topic_key": topic_key}).mappings().first()
    return dict(row or {})


def get_research_ai_usage_by_model(
    engine: Engine,
    *,
    topic_key: str,
) -> List[Dict[str, Any]]:
    sql = """
        WITH topic_rows AS (
            SELECT
                d.document_id,
                d.embedding_model_id,
                d.embedded_at,
                c.content
            FROM research_documents d
            JOIN research_sources s
              ON s.source_id = d.source_id
            LEFT JOIN research_chunks c
              ON c.document_id = d.document_id
            WHERE s.topic_key = :topic_key
              AND d.status = 'embedded'
              AND coalesce(d.suppressed, false) = false
              AND d.embedding_model_id IS NOT NULL
        )
        SELECT
            embedding_model_id,
            count(DISTINCT document_id) AS documents_count,
            count(content) AS chunks_count,
            COALESCE(sum(CEIL(octet_length(COALESCE(content, ''))::numeric / 4.0)), 0)::bigint AS estimated_tokens_total,
            COALESCE(
                sum(
                    CASE
                        WHEN embedded_at >= now() - interval '24 hours'
                        THEN CEIL(octet_length(COALESCE(content, ''))::numeric / 4.0)
                        ELSE 0
                    END
                ),
                0
            )::bigint AS estimated_tokens_24h
        FROM topic_rows
        GROUP BY embedding_model_id
        ORDER BY embedding_model_id ASC
    """
    with engine.begin() as conn:
        rows = conn.execute(text(sql), {"topic_key": topic_key}).mappings().all()
    return [dict(row) for row in rows]


def get_context_db_size_bytes(engine: Engine) -> int:
    sql = "SELECT pg_database_size(current_database()) AS size_bytes"
    with engine.begin() as conn:
        row = conn.execute(text(sql)).mappings().first()
    return int((row or {}).get("size_bytes") or 0)


def redact_research_raw_payloads(
    engine: Engine,
    *,
    topic_key: str,
    older_than_days: int,
) -> int:
    sql = """
        UPDATE research_documents d
        SET raw_payload = NULL,
            updated_at = now()
        FROM research_sources s
        WHERE s.source_id = d.source_id
          AND s.topic_key = :topic_key
          AND d.raw_payload IS NOT NULL
          AND d.created_at < now() - (:older_than_days * interval '1 day')
    """
    with engine.begin() as conn:
        result = conn.execute(
            text(sql),
            {"topic_key": topic_key, "older_than_days": max(older_than_days, 0)},
        )
    return int(result.rowcount or 0)


def list_research_review_queue(
    engine: Engine,
    *,
    topic_key: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    sql = """
        WITH feedback_rollup AS (
            SELECT
                trace_id,
                count(*) FILTER (WHERE verdict = 'useful') AS useful_count,
                count(*) FILTER (WHERE verdict = 'not_useful') AS not_useful_count
            FROM research_retrieval_feedback
            GROUP BY trace_id
        )
        SELECT
            q.query_log_id,
            q.trace_id,
            q.query_text,
            q.candidate_count,
            q.returned_document_ids,
            q.returned_chunk_ids,
            q.status,
            q.error,
            q.created_at,
            coalesce(f.useful_count, 0) AS useful_count,
            coalesce(f.not_useful_count, 0) AS not_useful_count
        FROM research_query_logs q
        LEFT JOIN feedback_rollup f ON f.trace_id = q.trace_id
        WHERE q.topic_key = :topic_key
        ORDER BY
            coalesce(f.not_useful_count, 0) DESC,
            CASE WHEN q.status = 'error' THEN 1 ELSE 0 END DESC,
            q.created_at DESC
        LIMIT :limit
    """
    with engine.begin() as conn:
        rows = conn.execute(
            text(sql),
            {"topic_key": topic_key, "limit": max(limit, 1)},
        ).mappings().all()
    return [dict(row) for row in rows]


def get_research_bootstrap_event_by_idempotency(
    engine: Engine,
    *,
    topic_key: str,
    idempotency_key: str,
) -> Optional[Dict[str, Any]]:
    stmt = (
        select(research_bootstrap_events)
        .where(research_bootstrap_events.c.topic_key == topic_key)
        .where(research_bootstrap_events.c.idempotency_key == idempotency_key)
        .order_by(research_bootstrap_events.c.created_at.desc())
        .limit(1)
    )
    with engine.begin() as conn:
        row = conn.execute(stmt).mappings().first()
    return dict(row) if row else None


def create_research_bootstrap_event(
    engine: Engine,
    *,
    topic_key: str,
    request_hash: str,
    idempotency_key: Optional[str],
    summary: Dict[str, int],
    results: List[Dict[str, Any]],
    run_id: Optional[str],
) -> Dict[str, Any]:
    event_id = uuid.uuid4()
    parsed_run_id = None
    if run_id:
        try:
            parsed_run_id = uuid.UUID(str(run_id))
        except ValueError:
            parsed_run_id = None
    with engine.begin() as conn:
        row = conn.execute(
            research_bootstrap_events.insert()
            .values(
                {
                    "event_id": event_id,
                    "topic_key": topic_key,
                    "idempotency_key": idempotency_key,
                    "request_hash": request_hash,
                    "received": int(summary.get("received") or 0),
                    "valid": int(summary.get("valid") or 0),
                    "invalid": int(summary.get("invalid") or 0),
                    "created": int(summary.get("created") or 0),
                    "updated": int(summary.get("updated") or 0),
                    "skipped_duplicate": int(summary.get("skipped_duplicate") or 0),
                    "results": results,
                    "run_id": parsed_run_id,
                }
            )
            .returning(research_bootstrap_events)
        ).mappings().first()
    return dict(row) if row else {}


def get_latest_research_bootstrap_event(
    engine: Engine,
    *,
    topic_key: str,
) -> Optional[Dict[str, Any]]:
    stmt = (
        select(research_bootstrap_events)
        .where(research_bootstrap_events.c.topic_key == topic_key)
        .order_by(research_bootstrap_events.c.created_at.desc())
        .limit(1)
    )
    with engine.begin() as conn:
        row = conn.execute(stmt).mappings().first()
    return dict(row) if row else None


def count_research_bootstrap_events(
    engine: Engine,
    *,
    topic_key: str,
) -> int:
    sql = """
        SELECT count(*) AS c
        FROM research_bootstrap_events
        WHERE topic_key = :topic_key
    """
    with engine.begin() as conn:
        row = conn.execute(text(sql), {"topic_key": topic_key}).mappings().first()
    return int(row["c"]) if row else 0
