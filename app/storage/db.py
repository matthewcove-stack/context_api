from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.storage.schema import intel_article_sections, intel_articles, projects, tasks


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
