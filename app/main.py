from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings, settings as default_settings
from app.models import (
    ChunkSearchRequest,
    ChunkSearchResponse,
    ContextPackRequest,
    ContextPackResponse,
    IntelIngestRequest,
    IntelIngestResponse,
    OutlineResponse,
    ProjectResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SectionsRequest,
    SectionsResponse,
    SyncProjectsRequest,
    SyncTasksRequest,
    TaskResponse,
    TaskSearchRequest,
)
from app.storage.db import (
    check_db,
    create_db_engine,
    get_project,
    get_task,
    get_intel_outline,
    get_intel_sections,
    search_intel_articles,
    search_intel_sections,
    search_projects,
    search_tasks,
    upsert_projects,
    upsert_tasks,
)
from app.util.intel_fixtures import ingest_intel_fixtures
from app.util.scoring import score_match

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITEMS = 3
DEFAULT_TOKEN_BUDGET = 800
DEFAULT_MAX_SIGNALS = 3
DEFAULT_MAX_SECTION_IDS = 8
DEFAULT_MAX_CHUNKS = 3
MAX_MAX_CHUNKS = 10
DEFAULT_MAX_CHARS = 600


def _trim_text(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _normalize_topics(topics: Optional[List[str]]) -> List[str]:
    if not topics:
        return []
    normalized: List[str] = []
    for topic in topics:
        if isinstance(topic, str) and topic.strip():
            normalized.append(topic.strip().lower())
    return normalized


def _row_matches_topics(row: Dict[str, Any], topics: List[str]) -> bool:
    if not topics:
        return True
    row_topics = row.get("topics") or []
    if not isinstance(row_topics, list):
        return False
    normalized_row = {str(topic).strip().lower() for topic in row_topics if str(topic).strip()}
    return bool(normalized_row.intersection(topics))


def _query_mentions_detail(query: str) -> bool:
    query_lower = query.lower()
    keywords = [
        "implement",
        "implementation",
        "detail",
        "details",
        "how",
        "steps",
        "code",
        "example",
        "schema",
        "query",
        "sql",
        "config",
        "configuration",
    ]
    return any(keyword in query_lower for keyword in keywords)


def _build_signals(
    signals_raw: Any,
    *,
    article_id: str,
    max_signals: int,
    max_signal_chars: int,
) -> List[Dict[str, Any]]:
    signals: List[Dict[str, Any]] = []
    if not isinstance(signals_raw, list):
        return signals
    for signal in signals_raw:
        if not isinstance(signal, dict):
            continue
        claim = str(signal.get("claim") or "").strip()
        why = str(signal.get("why") or "").strip()
        if not claim or not why:
            continue
        tradeoff = signal.get("tradeoff")
        cite = signal.get("cite") or {}
        section_id = cite.get("section_id") if isinstance(cite, dict) else None
        signals.append(
            {
                "claim": _trim_text(claim, max_signal_chars),
                "why": _trim_text(why, max_signal_chars),
                "tradeoff": _trim_text(str(tradeoff), max_signal_chars) if tradeoff else None,
                "cite": {"article_id": article_id, "section_id": section_id},
            }
        )
        if len(signals) >= max_signals:
            break
    return signals


def _build_citations(signals: List[Dict[str, Any]], url: str) -> List[Dict[str, Any]]:
    seen = set()
    citations: List[Dict[str, Any]] = []
    for signal in signals:
        cite = signal.get("cite") or {}
        article_id = cite.get("article_id")
        section_id = cite.get("section_id")
        key = (article_id, section_id)
        if not article_id or key in seen:
            continue
        seen.add(key)
        citations.append({"url": url, "article_id": article_id, "section_id": section_id})
    return citations


def _determine_confidence(top_score: float, cited_signals: int) -> str:
    if top_score < 0.05:
        return "low"
    if top_score >= 0.2 and cited_signals >= 2:
        return "high"
    return "med"


def _determine_next_action(confidence: str, query: str) -> str:
    if confidence == "low":
        return "refine_query"
    if confidence == "med" and _query_mentions_detail(query):
        return "expand_sections"
    return "proceed"


def create_app(app_settings: Settings | None = None) -> FastAPI:
    app_settings = app_settings or default_settings
    app = FastAPI()

    app.state.settings = app_settings
    app.state.engine = create_db_engine(app_settings.database_url)

    def get_settings() -> Settings:
        return app.state.settings

    def require_bearer(
        authorization: str | None = Header(default=None),
        settings: Settings = Depends(get_settings),
    ) -> None:
        if not authorization:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
        try:
            scheme, token = authorization.split(" ", 1)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")
        if scheme.lower() != "bearer" or token != settings.context_api_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")

    @app.get("/health")
    def health() -> Dict[str, str]:
        try:
            check_db(app.state.engine)
        except Exception:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")
        return {"status": "ok"}

    @app.get("/version")
    def version(settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
        return {"version": settings.version, "git_sha": settings.git_sha}

    @app.post("/v1/projects/sync")
    def sync_projects(
        payload: SyncProjectsRequest,
        _: None = Depends(require_bearer),
    ) -> Dict[str, Any]:
        try:
            count = upsert_projects(
                app.state.engine,
                items=[item.model_dump() for item in payload.items],
                source=payload.source,
            )
        except SQLAlchemyError:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")
        return {"count": count}

    @app.post("/v1/tasks/sync")
    def sync_tasks(
        payload: SyncTasksRequest,
        _: None = Depends(require_bearer),
    ) -> Dict[str, Any]:
        try:
            count = upsert_tasks(
                app.state.engine,
                items=[item.model_dump() for item in payload.items],
                source=payload.source,
            )
        except SQLAlchemyError:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")
        return {"count": count}

    @app.post("/v1/projects/search", response_model=SearchResponse)
    def search_projects_endpoint(
        payload: SearchRequest,
        _: None = Depends(require_bearer),
    ) -> SearchResponse:
        rows = search_projects(app.state.engine, payload.query, payload.limit)
        results: List[SearchResult] = []
        for row in rows:
            score = score_match(payload.query, row.get("name", ""))
            results.append(
                SearchResult(
                    id=row["project_id"],
                    label=row.get("name", ""),
                    score=score,
                    status=row.get("status"),
                    meta={"source": row.get("source"), "updated_at": row.get("updated_at")},
                )
            )
        results.sort(key=lambda item: item.score, reverse=True)
        return SearchResponse(results=results[: payload.limit])

    @app.post("/v1/tasks/search", response_model=SearchResponse)
    def search_tasks_endpoint(
        payload: TaskSearchRequest,
        _: None = Depends(require_bearer),
    ) -> SearchResponse:
        rows = search_tasks(
            app.state.engine,
            query=payload.query,
            limit=payload.limit,
            project_id=payload.project_id,
            status=payload.status,
        )
        results: List[SearchResult] = []
        for row in rows:
            score = score_match(payload.query, row.get("title", ""))
            results.append(
                SearchResult(
                    id=row["task_id"],
                    label=row.get("title", ""),
                    score=score,
                    status=row.get("status"),
                    meta={
                        "project_id": row.get("project_id"),
                        "priority": row.get("priority"),
                        "due": row.get("due"),
                        "source": row.get("source"),
                        "updated_at": row.get("updated_at"),
                    },
                )
            )
        results.sort(key=lambda item: item.score, reverse=True)
        return SearchResponse(results=results[: payload.limit])

    @app.get("/v1/projects/{project_id}", response_model=ProjectResponse)
    def get_project_endpoint(
        project_id: str,
        _: None = Depends(require_bearer),
    ) -> ProjectResponse:
        row = get_project(app.state.engine, project_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return ProjectResponse(**row)

    @app.get("/v1/tasks/{task_id}", response_model=TaskResponse)
    def get_task_endpoint(
        task_id: str,
        _: None = Depends(require_bearer),
    ) -> TaskResponse:
        row = get_task(app.state.engine, task_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return TaskResponse(**row)

    @app.post("/v2/intel/ingest", response_model=IntelIngestResponse)
    def ingest_intel_endpoint(
        payload: IntelIngestRequest,
        _: None = Depends(require_bearer),
    ) -> IntelIngestResponse:
        try:
            ingested_ids = ingest_intel_fixtures(app.state.engine, bundle=payload.fixture_bundle)
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        except SQLAlchemyError:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")
        return IntelIngestResponse(ingested_article_ids=ingested_ids)

    @app.post("/v2/context/pack", response_model=ContextPackResponse)
    def context_pack_endpoint(
        payload: ContextPackRequest,
        _: None = Depends(require_bearer),
    ) -> ContextPackResponse:
        start_time = time.perf_counter()
        max_items = max(payload.max_items or DEFAULT_MAX_ITEMS, 1)
        token_budget = payload.token_budget or DEFAULT_TOKEN_BUDGET
        char_budget = max(token_budget, 1) * 4
        per_item_budget = max(200, char_budget // max_items)
        max_summary_chars = min(400, int(per_item_budget * 0.6))
        max_signal_chars = min(240, int(per_item_budget * 0.4))

        rows = search_intel_articles(
            app.state.engine,
            query=payload.query,
            limit=max_items * 5,
            recency_days=payload.recency_days,
        )
        topics_filter = _normalize_topics(payload.topics)
        if topics_filter:
            rows = [row for row in rows if _row_matches_topics(row, topics_filter)]

        items: List[Dict[str, Any]] = []
        retrieved_article_ids: List[str] = []
        used_chars = 0
        top_score = float(rows[0]["score"]) if rows else 0.0
        for row in rows:
            if len(items) >= max_items:
                break
            article_id = row.get("article_id")
            if not article_id:
                continue
            signals = _build_signals(
                row.get("signals"),
                article_id=article_id,
                max_signals=DEFAULT_MAX_SIGNALS,
                max_signal_chars=max_signal_chars,
            )
            if not signals:
                continue
            summary = _trim_text(str(row.get("summary") or ""), max_summary_chars)
            item_size = len(summary) + sum(
                len(signal.get("claim", "")) + len(signal.get("why", "")) + len(signal.get("tradeoff") or "")
                for signal in signals
            )
            if used_chars + item_size > char_budget and items:
                break
            if used_chars + item_size > char_budget and not items:
                summary = _trim_text(summary, max(80, char_budget // 4))
            citations = _build_citations(signals, str(row.get("url") or ""))
            items.append(
                {
                    "article_id": article_id,
                    "title": row.get("title") or "",
                    "url": row.get("url") or "",
                    "summary": summary,
                    "signals": signals,
                    "citations": citations,
                }
            )
            retrieved_article_ids.append(article_id)
            used_chars += item_size

        if not items:
            confidence = "low"
            next_action = "refine_query"
        else:
            cited_signals = len([s for s in items[0]["signals"] if s.get("cite", {}).get("section_id")])
            confidence = _determine_confidence(top_score, cited_signals)
            next_action = _determine_next_action(confidence, payload.query)
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        trace_id = str(uuid.uuid4())
        logger.info(
            "context_pack",
            extra={
                "trace_id": trace_id,
                "query": payload.query[:120],
                "retrieved": len(retrieved_article_ids),
                "confidence": confidence,
                "next_action": next_action,
            },
        )
        return ContextPackResponse(
            pack={"items": items},
            retrieval_confidence=confidence,
            next_action=next_action,
            trace={"trace_id": trace_id, "retrieved_article_ids": retrieved_article_ids, "timing_ms": {"total": elapsed_ms}},
        )

    @app.get("/v2/intel/articles/{article_id}/outline", response_model=OutlineResponse)
    def intel_outline_endpoint(
        article_id: str,
        _: None = Depends(require_bearer),
    ) -> OutlineResponse:
        row = get_intel_outline(app.state.engine, article_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
        return OutlineResponse(article_id=article_id, outline=row.get("outline") or [])

    @app.post("/v2/intel/articles/{article_id}/sections", response_model=SectionsResponse)
    def intel_sections_endpoint(
        article_id: str,
        payload: SectionsRequest,
        _: None = Depends(require_bearer),
    ) -> SectionsResponse:
        row = get_intel_outline(app.state.engine, article_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
        section_ids = payload.section_ids[:DEFAULT_MAX_SECTION_IDS]
        sections = get_intel_sections(
            app.state.engine,
            article_id=article_id,
            section_ids=section_ids,
        )
        return SectionsResponse(article_id=article_id, sections=sections)

    @app.post("/v2/intel/articles/{article_id}/chunks:search", response_model=ChunkSearchResponse)
    def intel_chunks_endpoint(
        article_id: str,
        payload: ChunkSearchRequest,
        _: None = Depends(require_bearer),
    ) -> ChunkSearchResponse:
        row = get_intel_outline(app.state.engine, article_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
        max_chunks = min(max(payload.max_chunks or DEFAULT_MAX_CHUNKS, 1), MAX_MAX_CHUNKS)
        max_chars = max(payload.max_chars or DEFAULT_MAX_CHARS, 80)
        chunks = search_intel_sections(
            app.state.engine,
            article_id=article_id,
            query=payload.query,
            limit=max_chunks,
        )
        trimmed = []
        for chunk in chunks:
            snippet = str(chunk.get("snippet") or "")
            snippet = snippet.replace("<b>", "").replace("</b>", "")
            snippet = _trim_text(snippet, max_chars)
            trimmed.append(
                {
                    "section_id": chunk.get("section_id"),
                    "snippet": snippet,
                    "score": float(chunk.get("score")) if chunk.get("score") is not None else None,
                }
            )
        return ChunkSearchResponse(article_id=article_id, chunks=trimmed)

    return app


app = create_app()
