from __future__ import annotations

import logging
import os
import time
import uuid
import json
import hashlib
from collections import deque
from threading import Lock
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

from app.config import Settings, settings as default_settings
from app.research.contracts import (
    ResearchFeedbackRequest,
    ResearchFeedbackResponse,
    ResearchRedactRequest,
    ResearchRedactResponse,
    ResearchReviewQueueItem,
    ResearchReviewQueueResponse,
    ResearchChunkSearchRequest,
    ResearchChunkSearchResponse,
    ResearchContextPackRequest,
    ResearchContextPackResponse,
    ResearchContextPackTrace,
    ResearchContextPack,
    ResearchContextPackItem,
    ResearchCitation,
    ResearchIngestRunRequest,
    ResearchIngestRunResponse,
    ResearchIngestRunStatusResponse,
    ResearchRunCounters,
    ResearchOpsSummaryResponse,
    ResearchSourceMetricRecord,
    ResearchSourceModerationResponse,
    ResearchSourceMetricsResponse,
    ResearchScoreBreakdown,
    ResearchSignal,
    ResearchSourceListResponse,
    ResearchSourceRecord,
    ResearchSourceUpsertRequest,
    ResearchSourceUpsertResponse,
    ResearchBootstrapRequest,
    ResearchBootstrapResponse,
    ResearchBootstrapSummary,
    ResearchBootstrapResult,
    ResearchBootstrapIngest,
    ResearchBootstrapStatusResponse,
    ResearchBootstrapStatusEvent,
)
from app.research.embeddings import embed_texts
from app.research.scoring import blend_score, cosine_similarity, embedding_score, lexical_score, recency_score, source_weight_score
from app.research.ids import compute_source_id
from app.models import (
    ChunkSearchRequest,
    ChunkSearchResponse,
    ContextPackRequest,
    ContextPackResponse,
    IntelArticleStatusResponse,
    IntelIngestRequest,
    IntelIngestResponse,
    IntelIngestUrlsRequest,
    IntelIngestUrlsResponse,
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
    canonicalize_url,
    create_research_ingestion_run,
    compute_article_id,
    create_intel_ingest_job,
    create_db_engine,
    create_research_query_log,
    get_research_ingestion_run,
    get_research_ingestion_run_by_idempotency,
    get_project,
    get_task,
    get_intel_article,
    get_intel_outline,
    get_intel_sections,
    get_latest_job_error,
    search_intel_articles,
    search_intel_sections,
    list_research_sources,
    list_research_embeddings_for_documents,
    insert_research_relevance_scores,
    insert_research_retrieval_feedback,
    get_research_ops_summary,
    list_research_review_queue,
    get_research_bootstrap_event_by_idempotency,
    create_research_bootstrap_event,
    get_latest_research_bootstrap_event,
    list_research_source_metrics,
    redact_research_raw_payloads,
    search_research_chunks,
    search_research_document_chunks,
    search_projects,
    search_tasks,
    set_research_source_enabled,
    upsert_research_source,
    get_research_document,
    upsert_intel_article_seed,
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
DEFAULT_RESEARCH_MAX_ITEMS = 3
DEFAULT_RESEARCH_MAX_CHUNKS = 3
MAX_RESEARCH_MAX_CHUNKS = 10
DEFAULT_RESEARCH_MAX_CHARS = 600
DEFAULT_BOOTSTRAP_MAX_SUGGESTIONS = 200
DEFAULT_BOOTSTRAP_CALLS_PER_MINUTE = 20

_bootstrap_rate_lock = Lock()
_bootstrap_rate_state: Dict[str, deque[float]] = {}


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


def _clean_snippet(snippet: str) -> str:
    return snippet.replace("<b>", "").replace("</b>", "").strip()


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _topic_default_policy() -> Dict[str, Any]:
    return {
        "poll_interval_minutes": _to_int(os.getenv("RESEARCH_DEFAULT_POLL_INTERVAL_MINUTES", "60")) or 60,
        "rate_limit_per_hour": _to_int(os.getenv("RESEARCH_DEFAULT_RATE_LIMIT_PER_HOUR", "30")) or 30,
        "source_weight": float(os.getenv("RESEARCH_DEFAULT_SOURCE_WEIGHT", "1.0")),
        "robots_mode": os.getenv("RESEARCH_ROBOTS_MODE", "strict").strip().lower() or "strict",
    }


def _hash_bootstrap_request(topic_key: str, payload: Dict[str, Any]) -> str:
    canonical = {"topic_key": topic_key, "payload": payload}
    body = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _enforce_bootstrap_rate_limit(token: str) -> None:
    max_calls = _to_int(os.getenv("RESEARCH_BOOTSTRAP_MAX_CALLS_PER_MINUTE", str(DEFAULT_BOOTSTRAP_CALLS_PER_MINUTE)))
    if max_calls <= 0:
        return
    now = time.time()
    window_start = now - 60.0
    with _bootstrap_rate_lock:
        queue = _bootstrap_rate_state.setdefault(token, deque())
        while queue and queue[0] < window_start:
            queue.popleft()
        if len(queue) >= max_calls:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Bootstrap rate limit exceeded",
            )
        queue.append(now)


def _bootstrap_response_from_event(
    event: Dict[str, Any],
    run_status: Optional[str] = None,
) -> ResearchBootstrapResponse:
    summary = ResearchBootstrapSummary(
        received=_to_int(event.get("received")),
        valid=_to_int(event.get("valid")),
        invalid=_to_int(event.get("invalid")),
        created=_to_int(event.get("created")),
        updated=_to_int(event.get("updated")),
        skipped_duplicate=_to_int(event.get("skipped_duplicate")),
    )
    raw_results = event.get("results") or []
    results = [ResearchBootstrapResult.model_validate(item) for item in raw_results if isinstance(item, dict)]
    run_id = str(event.get("run_id")) if event.get("run_id") else None
    status_value = run_status or (str(event.get("run_status")) if event.get("run_status") else None)
    ingest = ResearchBootstrapIngest(
        triggered=bool(run_id),
        run_id=run_id,
        status=status_value if status_value in {"queued", "running", "completed", "failed"} else None,
    )
    return ResearchBootstrapResponse(
        topic_key=str(event.get("topic_key") or ""),
        summary=summary,
        results=results,
        ingest=ingest,
    )


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
    ) -> str:
        if not authorization:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
        try:
            scheme, token = authorization.split(" ", 1)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")
        if scheme.lower() != "bearer" or token != settings.context_api_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")
        return token

    @app.get("/health")
    def health() -> Dict[str, str]:
        try:
            check_db(app.state.engine)
        except Exception:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> Dict[str, str]:
        try:
            check_db(app.state.engine)
        except Exception:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")
        return {"status": "ready"}

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

    @app.post("/v2/intel/ingest_urls", response_model=IntelIngestUrlsResponse)
    def ingest_intel_urls_endpoint(
        payload: IntelIngestUrlsRequest,
        _: None = Depends(require_bearer),
    ) -> IntelIngestUrlsResponse:
        results = []
        for url in payload.urls:
            if not url or not isinstance(url, str):
                results.append({"url": url or "", "status": "failed", "reason": "invalid url"})
                continue
            canonical = canonicalize_url(url)
            if not canonical:
                results.append({"url": url, "status": "failed", "reason": "invalid url"})
                continue
            article_id = compute_article_id(canonical)
            existing = get_intel_article(app.state.engine, article_id)
            if existing and not payload.force_refetch and existing.get("status") == "enriched":
                results.append({"url": url, "status": "deduped", "article_id": article_id})
                continue
            try:
                upsert_intel_article_seed(
                    app.state.engine,
                    article_id=article_id,
                    url=canonical,
                    url_original=url,
                    topics=payload.topics,
                    tags=payload.tags,
                    status="queued",
                    force_reset=bool(payload.force_refetch),
                )
                job_status = "queued" if payload.enrich is not False else "queued_no_enrich"
                job_id = create_intel_ingest_job(
                    app.state.engine,
                    url_original=url,
                    url_canonical=canonical,
                    article_id=article_id,
                    status=job_status,
                )
            except SQLAlchemyError as exc:
                results.append({"url": url, "status": "failed", "reason": str(exc)})
                continue
            results.append(
                {
                    "url": url,
                    "status": "queued",
                    "article_id": article_id,
                    "job_id": job_id,
                }
            )
        return IntelIngestUrlsResponse(results=results)

    @app.get("/v2/intel/articles/{article_id}", response_model=IntelArticleStatusResponse)
    def intel_article_status_endpoint(
        article_id: str,
        _: None = Depends(require_bearer),
    ) -> IntelArticleStatusResponse:
        row = get_intel_article(app.state.engine, article_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
        last_error = get_latest_job_error(app.state.engine, article_id)
        status_value = row.get("status") or "queued"
        fetch_meta = row.get("fetch_meta") or {}
        extraction_meta = row.get("extraction_meta") or {}
        enrichment_meta = row.get("enrichment_meta") or {}
        meta = {
            "fetch": {
                "http_status": row.get("http_status"),
                "content_type": row.get("content_type"),
                "fetched_at": fetch_meta.get("fetched_at"),
                "warnings": fetch_meta.get("warnings") or [],
            }
            if fetch_meta
            else None,
            "extraction": {
                "method": extraction_meta.get("method"),
                "confidence": extraction_meta.get("confidence"),
                "warnings": extraction_meta.get("warnings") or [],
            }
            if extraction_meta
            else None,
            "enrichment": {
                "model": enrichment_meta.get("model"),
                "prompt_version": enrichment_meta.get("prompt_version"),
                "confidence": enrichment_meta.get("confidence"),
                "token_usage": enrichment_meta.get("token_usage"),
                "warnings": enrichment_meta.get("warnings") or [],
            }
            if enrichment_meta
            else None,
        }
        summary = row.get("summary") if status_value in ("enriched", "partial") else None
        signals = row.get("signals") if status_value in ("enriched", "partial") else None
        outline = row.get("outline") if status_value in ("extracted", "enriched", "partial") else None
        return IntelArticleStatusResponse(
            article_id=article_id,
            url=row.get("url") or "",
            title=row.get("title"),
            status=status_value,
            topics=row.get("topics") or [],
            summary=summary,
            signals=signals,
            outline=outline,
            meta=meta,
            last_error=last_error,
        )

    @app.post("/v2/research/sources/upsert", response_model=ResearchSourceUpsertResponse)
    def upsert_research_source_endpoint(
        payload: ResearchSourceUpsertRequest,
        _: None = Depends(require_bearer),
    ) -> ResearchSourceUpsertResponse:
        canonical_base = canonicalize_url(payload.base_url)
        if not canonical_base:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid base_url")
        source_id = compute_source_id(
            topic_key=payload.topic_key,
            kind=payload.kind,
            base_url=canonical_base,
        )
        max_items_per_run = max(int(os.getenv("RESEARCH_MAX_ITEMS_PER_SOURCE", "50")), 1)
        result = upsert_research_source(
            app.state.engine,
            source_id=source_id,
            topic_key=payload.topic_key.strip().lower(),
            kind=payload.kind,
            name=payload.name.strip(),
            base_url_original=payload.base_url.strip(),
            base_url_canonical=canonical_base,
            enabled=payload.enabled,
            tags=[tag.strip().lower() for tag in payload.tags if tag.strip()],
            poll_interval_minutes=payload.poll_interval_minutes,
            rate_limit_per_hour=payload.rate_limit_per_hour,
            robots_mode=payload.robots_mode,
            max_items_per_run=max_items_per_run,
            source_weight=float(payload.source_weight),
        )
        return ResearchSourceUpsertResponse(**result)

    @app.get("/v2/research/sources", response_model=ResearchSourceListResponse)
    def list_research_sources_endpoint(
        topic_key: str,
        enabled_only: bool = True,
        _: None = Depends(require_bearer),
    ) -> ResearchSourceListResponse:
        rows = list_research_sources(
            app.state.engine,
            topic_key=topic_key.strip().lower(),
            enabled_only=enabled_only,
        )
        items: List[ResearchSourceRecord] = []
        for row in rows:
            items.append(
                ResearchSourceRecord(
                    source_id=row["source_id"],
                    topic_key=row["topic_key"],
                    kind=row["kind"],
                    name=row["name"],
                    base_url_original=row["base_url_original"],
                    base_url_canonical=row["base_url_canonical"],
                    enabled=bool(row.get("enabled", True)),
                    tags=row.get("tags") or [],
                    poll_interval_minutes=int(row.get("poll_interval_minutes") or 60),
                    rate_limit_per_hour=int(row.get("rate_limit_per_hour") or 30),
                    source_weight=float(row.get("source_weight") or 1.0),
                    consecutive_failures=int(row.get("consecutive_failures") or 0),
                    cooldown_until=row.get("cooldown_until"),
                    last_error=(str(row.get("last_error")) if row.get("last_error") else None),
                    robots_mode=row.get("robots_mode") or "strict",
                    max_items_per_run=int(row.get("max_items_per_run") or 50),
                )
            )
        return ResearchSourceListResponse(items=items)

    @app.post("/v2/research/sources/bootstrap", response_model=ResearchBootstrapResponse)
    def bootstrap_research_sources_endpoint(
        payload: ResearchBootstrapRequest,
        token: str = Depends(require_bearer),
    ) -> ResearchBootstrapResponse:
        normalized_topic = payload.topic_key.strip().lower()
        max_suggestions = _to_int(
            os.getenv("RESEARCH_BOOTSTRAP_MAX_SUGGESTIONS", str(DEFAULT_BOOTSTRAP_MAX_SUGGESTIONS))
        ) or DEFAULT_BOOTSTRAP_MAX_SUGGESTIONS
        if len(payload.suggestions) > max_suggestions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"suggestions exceeds limit ({max_suggestions})",
            )
        if not payload.dry_run:
            _enforce_bootstrap_rate_limit(token)

        request_hash = _hash_bootstrap_request(
            normalized_topic,
            payload.model_dump(exclude_none=True),
        )
        if payload.idempotency_key and not payload.dry_run:
            existing_event = get_research_bootstrap_event_by_idempotency(
                app.state.engine,
                topic_key=normalized_topic,
                idempotency_key=payload.idempotency_key,
            )
            if existing_event:
                existing_hash = str(existing_event.get("request_hash") or "")
                if existing_hash and existing_hash != request_hash:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="idempotency_key already used with different payload",
                    )
                run_status = None
                run_id = existing_event.get("run_id")
                if run_id:
                    run = get_research_ingestion_run(app.state.engine, run_id=str(run_id))
                    run_status = str(run.get("status") or "") if run else None
                return _bootstrap_response_from_event(existing_event, run_status=run_status)

        defaults = _topic_default_policy()
        existing_rows = list_research_sources(
            app.state.engine,
            topic_key=normalized_topic,
            enabled_only=False,
        )
        existing_source_ids = {str(row.get("source_id") or "") for row in existing_rows}
        seen_source_ids = set()
        max_items_per_run = max(int(os.getenv("RESEARCH_MAX_ITEMS_PER_SOURCE", "50")), 1)
        summary = {
            "received": len(payload.suggestions),
            "valid": 0,
            "invalid": 0,
            "created": 0,
            "updated": 0,
            "skipped_duplicate": 0,
        }
        results: List[ResearchBootstrapResult] = []
        valid_source_ids: List[str] = []

        for index, suggestion in enumerate(payload.suggestions):
            canonical = canonicalize_url(suggestion.base_url)
            parsed = urlparse(canonical) if canonical else None
            if not canonical or not parsed or not parsed.netloc:
                summary["invalid"] += 1
                results.append(
                    ResearchBootstrapResult(index=index, status="invalid", reason="invalid base_url")
                )
                continue
            source_id = compute_source_id(topic_key=normalized_topic, kind=suggestion.kind, base_url=canonical)
            if source_id in seen_source_ids:
                summary["skipped_duplicate"] += 1
                results.append(
                    ResearchBootstrapResult(
                        index=index,
                        status="skipped_duplicate",
                        reason="duplicate source in request",
                        source_id=source_id,
                    )
                )
                continue
            seen_source_ids.add(source_id)
            summary["valid"] += 1
            valid_source_ids.append(source_id)
            effective_poll = suggestion.poll_interval_minutes or int(defaults["poll_interval_minutes"])
            effective_rate = suggestion.rate_limit_per_hour or int(defaults["rate_limit_per_hour"])
            effective_weight = suggestion.source_weight if suggestion.source_weight is not None else float(defaults["source_weight"])
            effective_robots = suggestion.robots_mode or str(defaults["robots_mode"])
            status_value = "updated" if source_id in existing_source_ids else "created"

            if not payload.dry_run:
                upsert_result = upsert_research_source(
                    app.state.engine,
                    source_id=source_id,
                    topic_key=normalized_topic,
                    kind=suggestion.kind,
                    name=suggestion.name.strip(),
                    base_url_original=suggestion.base_url.strip(),
                    base_url_canonical=canonical,
                    enabled=True,
                    tags=[tag.strip().lower() for tag in suggestion.tags if tag.strip()],
                    poll_interval_minutes=effective_poll,
                    rate_limit_per_hour=effective_rate,
                    robots_mode=effective_robots,
                    max_items_per_run=max_items_per_run,
                    source_weight=float(effective_weight),
                )
                status_value = str(upsert_result.get("status") or status_value)
            if status_value == "created":
                summary["created"] += 1
                existing_source_ids.add(source_id)
            else:
                summary["updated"] += 1
            results.append(ResearchBootstrapResult(index=index, status=status_value, source_id=source_id))

        ingest_triggered = False
        run_id: Optional[str] = None
        run_status: Optional[str] = None
        selected_source_ids = list(dict.fromkeys(valid_source_ids))
        if payload.trigger_ingest and selected_source_ids and not payload.dry_run:
            run = create_research_ingestion_run(
                app.state.engine,
                topic_key=normalized_topic,
                trigger=payload.trigger,
                requested_source_ids=selected_source_ids,
                selected_source_ids=selected_source_ids,
                idempotency_key=f"bootstrap:{payload.idempotency_key}" if payload.idempotency_key else None,
            )
            run_id = str(run.get("run_id"))
            run_status = str(run.get("status") or "queued")
            ingest_triggered = True

        response_payload = ResearchBootstrapResponse(
            topic_key=normalized_topic,
            summary=ResearchBootstrapSummary(**summary),
            results=results,
            ingest=ResearchBootstrapIngest(
                triggered=ingest_triggered,
                run_id=run_id,
                status=run_status if run_status in {"queued", "running", "completed", "failed"} else None,
            ),
        )
        if not payload.dry_run:
            create_research_bootstrap_event(
                app.state.engine,
                topic_key=normalized_topic,
                request_hash=request_hash,
                idempotency_key=payload.idempotency_key,
                summary=summary,
                results=[item.model_dump(mode="json", exclude_none=True) for item in results],
                run_id=run_id,
            )
        return response_payload

    @app.get("/v2/research/bootstrap/status", response_model=ResearchBootstrapStatusResponse)
    def get_research_bootstrap_status_endpoint(
        topic_key: str,
        _: str = Depends(require_bearer),
    ) -> ResearchBootstrapStatusResponse:
        normalized_topic = topic_key.strip().lower()
        event = get_latest_research_bootstrap_event(
            app.state.engine,
            topic_key=normalized_topic,
        )
        if not event:
            return ResearchBootstrapStatusResponse(topic_key=normalized_topic, latest_bootstrap=None)
        run_status = None
        if event.get("run_id"):
            run = get_research_ingestion_run(app.state.engine, run_id=str(event["run_id"]))
            run_status = str(run.get("status") or "") if run else None
        summary = ResearchBootstrapSummary(
            received=_to_int(event.get("received")),
            valid=_to_int(event.get("valid")),
            invalid=_to_int(event.get("invalid")),
            created=_to_int(event.get("created")),
            updated=_to_int(event.get("updated")),
            skipped_duplicate=_to_int(event.get("skipped_duplicate")),
        )
        return ResearchBootstrapStatusResponse(
            topic_key=normalized_topic,
            latest_bootstrap=ResearchBootstrapStatusEvent(
                event_id=str(event.get("event_id")),
                request_hash=str(event.get("request_hash") or ""),
                idempotency_key=(str(event.get("idempotency_key")) if event.get("idempotency_key") else None),
                summary=summary,
                run_id=(str(event.get("run_id")) if event.get("run_id") else None),
                run_status=run_status if run_status in {"queued", "running", "completed", "failed"} else None,
                created_at=event.get("created_at"),
            ),
        )

    @app.post(
        "/v2/research/sources/{source_id}/disable",
        response_model=ResearchSourceModerationResponse,
    )
    def disable_research_source_endpoint(
        source_id: str,
        _: None = Depends(require_bearer),
    ) -> ResearchSourceModerationResponse:
        updated = set_research_source_enabled(
            app.state.engine,
            source_id=source_id,
            enabled=False,
        )
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
        return ResearchSourceModerationResponse(source_id=source_id, enabled=False, status="updated")

    @app.post(
        "/v2/research/sources/{source_id}/enable",
        response_model=ResearchSourceModerationResponse,
    )
    def enable_research_source_endpoint(
        source_id: str,
        _: None = Depends(require_bearer),
    ) -> ResearchSourceModerationResponse:
        updated = set_research_source_enabled(
            app.state.engine,
            source_id=source_id,
            enabled=True,
        )
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
        return ResearchSourceModerationResponse(source_id=source_id, enabled=True, status="updated")

    @app.post("/v2/research/ingest/run", response_model=ResearchIngestRunResponse)
    def queue_research_ingest_run_endpoint(
        payload: ResearchIngestRunRequest,
        _: None = Depends(require_bearer),
    ) -> ResearchIngestRunResponse:
        normalized_topic = payload.topic_key.strip().lower()
        if payload.idempotency_key:
            existing = get_research_ingestion_run_by_idempotency(
                app.state.engine,
                topic_key=normalized_topic,
                idempotency_key=payload.idempotency_key,
            )
            if existing:
                selected = existing.get("selected_source_ids") or []
                return ResearchIngestRunResponse(
                    run_id=str(existing.get("run_id")),
                    status=existing.get("status") or "queued",
                    sources_selected=len(selected) if isinstance(selected, list) else 0,
                )

        selected_sources = list_research_sources(
            app.state.engine,
            topic_key=normalized_topic,
            source_ids=payload.source_ids or None,
            enabled_only=True,
        )
        selected_source_ids = [str(row["source_id"]) for row in selected_sources]
        if not selected_source_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No enabled sources selected for topic",
            )
        run = create_research_ingestion_run(
            app.state.engine,
            topic_key=normalized_topic,
            trigger=payload.trigger,
            requested_source_ids=payload.source_ids,
            selected_source_ids=selected_source_ids,
            idempotency_key=payload.idempotency_key,
        )
        return ResearchIngestRunResponse(
            run_id=str(run.get("run_id")),
            status=run.get("status") or "queued",
            sources_selected=len(selected_source_ids),
        )

    @app.get("/v2/research/ingest/runs/{run_id}", response_model=ResearchIngestRunStatusResponse)
    def get_research_ingest_run_endpoint(
        run_id: str,
        _: None = Depends(require_bearer),
    ) -> ResearchIngestRunStatusResponse:
        run = get_research_ingestion_run(app.state.engine, run_id=run_id)
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
        return ResearchIngestRunStatusResponse(
            run_id=str(run["run_id"]),
            status=run.get("status") or "queued",
            started_at=run.get("started_at"),
            finished_at=run.get("finished_at"),
            counters=ResearchRunCounters(
                items_seen=int(run.get("items_seen") or 0),
                items_new=int(run.get("items_new") or 0),
                items_deduped=int(run.get("items_deduped") or 0),
                items_failed=int(run.get("items_failed") or 0),
            ),
            errors=[str(item) for item in (run.get("errors") or [])],
        )

    @app.post("/v2/research/context/pack", response_model=ResearchContextPackResponse)
    def research_context_pack_endpoint(
        payload: ResearchContextPackRequest,
        _: None = Depends(require_bearer),
    ) -> ResearchContextPackResponse:
        trace_id = str(uuid.uuid4())
        start_time = time.perf_counter()
        max_items = max(payload.max_items or DEFAULT_RESEARCH_MAX_ITEMS, 1)
        topic_key = payload.topic_key.strip().lower()
        embedding_model_id = os.getenv("RESEARCH_EMBEDDING_MODEL", "hash-64")
        lexical_weight = float(os.getenv("RESEARCH_SCORE_WEIGHT_LEXICAL", "0.45"))
        embedding_weight = float(os.getenv("RESEARCH_SCORE_WEIGHT_EMBEDDING", "0.35"))
        recency_weight = float(os.getenv("RESEARCH_SCORE_WEIGHT_RECENCY", "0.15"))
        source_weight_factor = float(os.getenv("RESEARCH_SCORE_WEIGHT_SOURCE", "0.05"))
        query_vector: List[float] = []
        try:
            rows = search_research_chunks(
                app.state.engine,
                topic_key=topic_key,
                query=payload.query,
                source_ids=payload.source_ids or None,
                recency_days=payload.recency_days,
                limit=max_items * 15,
            )
            try:
                vectors = embed_texts(
                    texts=[payload.query],
                    model=embedding_model_id,
                    api_key=os.getenv("OPENAI_API_KEY", ""),
                )
                if vectors:
                    query_vector = vectors[0]
            except Exception:
                query_vector = []

            doc_ids = sorted({str(row.get("document_id") or "") for row in rows if row.get("document_id")})
            embedding_rows = list_research_embeddings_for_documents(
                app.state.engine,
                document_ids=doc_ids,
                embedding_model_id=embedding_model_id,
            )
            embedding_map = {
                (str(row.get("document_id")), str(row.get("chunk_id"))): row.get("vector") or []
                for row in embedding_rows
            }
            ranked: List[Dict[str, Any]] = []
            for row in rows:
                document_id = str(row.get("document_id") or "")
                chunk_id = str(row.get("chunk_id") or "")
                if not document_id or not chunk_id:
                    continue
                chunk_vector = embedding_map.get((document_id, chunk_id)) or []
                lexical_value = lexical_score(float(row.get("lexical_score") or 0.0))
                cosine = cosine_similarity(query_vector, chunk_vector) if query_vector and chunk_vector else 0.0
                embedding_value = embedding_score(cosine)
                recency_value = recency_score(row.get("published_at"))
                source_weight_value = source_weight_score(float(row.get("source_weight") or 1.0))
                score = blend_score(
                    lexical=lexical_value,
                    embedding=embedding_value,
                    recency=recency_value,
                    source_weight=source_weight_value,
                    lexical_weight=lexical_weight,
                    embedding_weight=embedding_weight,
                    recency_weight=recency_weight,
                    source_weight_factor=source_weight_factor,
                )
                merged = dict(row)
                merged["_score"] = score
                ranked.append(merged)
            ranked.sort(
                key=lambda row: (
                    float((row.get("_score") or {}).get("total") or 0.0),
                    float((row.get("_score") or {}).get("lexical") or 0.0),
                ),
                reverse=True,
            )
            candidate_count = len(rows)
            items: List[ResearchContextPackItem] = []
            seen_docs = set()
            returned_chunk_ids: List[str] = []
            top_score = float((ranked[0].get("_score") or {}).get("total") or 0.0) if ranked else 0.0

            for row in ranked:
                document_id = str(row.get("document_id") or "")
                chunk_id = str(row.get("chunk_id") or "")
                if not document_id or not chunk_id or document_id in seen_docs:
                    continue
                score = row.get("_score") or {}
                total_score = float(score.get("total") or 0.0)
                if payload.min_relevance_score is not None and total_score < payload.min_relevance_score:
                    continue
                snippet = _clean_snippet(str(row.get("snippet") or row.get("content") or ""))
                if not snippet:
                    continue
                citation = ResearchCitation(document_id=document_id, chunk_id=chunk_id)
                items.append(
                    ResearchContextPackItem(
                        document_id=document_id,
                        source_id=str(row.get("source_id") or ""),
                        title=str(row.get("title") or ""),
                        canonical_url=str(row.get("canonical_url") or ""),
                        published_at=row.get("published_at"),
                        summary=_trim_text(snippet, DEFAULT_RESEARCH_MAX_CHARS),
                        signals=[
                            ResearchSignal(
                                claim=_trim_text(snippet, 240),
                                why="Hybrid relevance from lexical, embedding, recency, and source weighting.",
                                cite=citation,
                            )
                        ],
                        citations=[citation],
                        score_breakdown=ResearchScoreBreakdown(
                            total=total_score,
                            lexical=float(score.get("lexical") or 0.0),
                            embedding=float(score.get("embedding") or 0.0),
                            recency=float(score.get("recency") or 0.0),
                            source_weight=float(score.get("source_weight") or 0.0),
                        ),
                    )
                )
                seen_docs.add(document_id)
                returned_chunk_ids.append(chunk_id)
                if len(items) >= max_items:
                    break

            insert_research_relevance_scores(
                app.state.engine,
                trace_id=trace_id,
                topic_key=topic_key,
                query_text=payload.query,
                items=[
                    {
                        "document_id": str(row.get("document_id") or ""),
                        "chunk_id": str(row.get("chunk_id") or ""),
                        "score_total": float((row.get("_score") or {}).get("total") or 0.0),
                        "score_lexical": float((row.get("_score") or {}).get("lexical") or 0.0),
                        "score_embedding": float((row.get("_score") or {}).get("embedding") or 0.0),
                        "score_recency": float((row.get("_score") or {}).get("recency") or 0.0),
                        "score_source_weight": float((row.get("_score") or {}).get("source_weight") or 0.0),
                    }
                    for row in ranked[: max_items * 5]
                ],
            )
            retrieved_document_ids = [item.document_id for item in items]
            cited_signals = len(items[0].signals) if items else 0
            confidence = _determine_confidence(top_score, cited_signals)
            next_action = _determine_next_action(confidence, payload.query)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            create_research_query_log(
                app.state.engine,
                trace_id=trace_id,
                topic_key=topic_key,
                query_text=payload.query,
                source_ids=payload.source_ids,
                token_budget=payload.token_budget,
                max_items=max_items,
                recency_days=payload.recency_days,
                min_relevance_score=payload.min_relevance_score,
                candidate_count=candidate_count,
                returned_document_ids=retrieved_document_ids,
                returned_chunk_ids=returned_chunk_ids,
                timing_ms=elapsed_ms,
                status="ok",
            )
            return ResearchContextPackResponse(
                pack=ResearchContextPack(items=items),
                retrieval_confidence=confidence,
                next_action=next_action,
                trace=ResearchContextPackTrace(
                    trace_id=trace_id,
                    retrieved_document_ids=retrieved_document_ids,
                    timing_ms={"total": elapsed_ms},
                ),
            )
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            create_research_query_log(
                app.state.engine,
                trace_id=trace_id,
                topic_key=topic_key,
                query_text=payload.query,
                source_ids=payload.source_ids,
                token_budget=payload.token_budget,
                max_items=max_items,
                recency_days=payload.recency_days,
                min_relevance_score=payload.min_relevance_score,
                candidate_count=0,
                returned_document_ids=[],
                returned_chunk_ids=[],
                timing_ms=elapsed_ms,
                status="error",
                error=str(exc),
            )
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Research retrieval failed")

    @app.post(
        "/v2/research/documents/{document_id}/chunks:search",
        response_model=ResearchChunkSearchResponse,
    )
    def research_document_chunks_endpoint(
        document_id: str,
        payload: ResearchChunkSearchRequest,
        _: None = Depends(require_bearer),
    ) -> ResearchChunkSearchResponse:
        doc = get_research_document(app.state.engine, document_id=document_id)
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        max_chunks = min(max(payload.max_chunks or DEFAULT_RESEARCH_MAX_CHUNKS, 1), MAX_RESEARCH_MAX_CHUNKS)
        max_chars = max(payload.max_chars or DEFAULT_RESEARCH_MAX_CHARS, 80)
        rows = search_research_document_chunks(
            app.state.engine,
            document_id=document_id,
            query=payload.query,
            limit=max_chunks,
        )
        chunks = []
        for row in rows:
            snippet = _clean_snippet(str(row.get("snippet") or ""))
            chunks.append(
                {
                    "chunk_id": str(row.get("chunk_id") or ""),
                    "snippet": _trim_text(snippet, max_chars),
                    "score": float(row.get("score")) if row.get("score") is not None else None,
                }
            )
        return ResearchChunkSearchResponse(document_id=document_id, chunks=chunks)

    @app.post("/v2/research/retrieval/feedback", response_model=ResearchFeedbackResponse)
    def research_feedback_endpoint(
        payload: ResearchFeedbackRequest,
        _: None = Depends(require_bearer),
    ) -> ResearchFeedbackResponse:
        doc = get_research_document(app.state.engine, document_id=payload.document_id)
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        feedback_id = insert_research_retrieval_feedback(
            app.state.engine,
            trace_id=payload.trace_id,
            query_log_id=payload.query_log_id,
            document_id=payload.document_id,
            chunk_id=payload.chunk_id,
            verdict=payload.verdict,
            notes=payload.notes,
        )
        return ResearchFeedbackResponse(feedback_id=feedback_id, status="recorded")

    @app.get("/v2/research/ops/summary", response_model=ResearchOpsSummaryResponse)
    def research_ops_summary_endpoint(
        topic_key: str,
        _: None = Depends(require_bearer),
    ) -> ResearchOpsSummaryResponse:
        normalized_topic = topic_key.strip().lower()
        summary = get_research_ops_summary(
            app.state.engine,
            topic_key=normalized_topic,
        )
        return ResearchOpsSummaryResponse(
            topic_key=normalized_topic,
            sources_total=int(summary.get("sources_total") or 0),
            sources_enabled=int(summary.get("sources_enabled") or 0),
            sources_in_cooldown=int(summary.get("sources_in_cooldown") or 0),
            documents_total=int(summary.get("documents_total") or 0),
            documents_embedded=int(summary.get("documents_embedded") or 0),
            documents_failed=int(summary.get("documents_failed") or 0),
            runs_open=int(summary.get("runs_open") or 0),
            runs_failed_24h=int(summary.get("runs_failed_24h") or 0),
            run_failure_rate_24h=float(summary.get("run_failure_rate_24h") or 0.0),
            retrieval_queries_24h=int(summary.get("retrieval_queries_24h") or 0),
            retrieval_errors_24h=int(summary.get("retrieval_errors_24h") or 0),
        )

    @app.get("/v2/research/ops/sources", response_model=ResearchSourceMetricsResponse)
    def research_ops_sources_endpoint(
        topic_key: str,
        limit: int = 20,
        _: None = Depends(require_bearer),
    ) -> ResearchSourceMetricsResponse:
        normalized_topic = topic_key.strip().lower()
        rows = list_research_source_metrics(
            app.state.engine,
            topic_key=normalized_topic,
            limit=limit,
        )
        items = [
            ResearchSourceMetricRecord(
                source_id=str(row.get("source_id") or ""),
                name=str(row.get("name") or ""),
                enabled=bool(row.get("enabled", True)),
                last_polled_at=row.get("last_polled_at"),
                consecutive_failures=int(row.get("consecutive_failures") or 0),
                cooldown_until=row.get("cooldown_until"),
                last_error=(str(row.get("last_error")) if row.get("last_error") else None),
                documents_total=int(row.get("documents_total") or 0),
                documents_embedded=int(row.get("documents_embedded") or 0),
                documents_failed=int(row.get("documents_failed") or 0),
                retrieval_queries_24h=int(row.get("retrieval_queries_24h") or 0),
            )
            for row in rows
        ]
        return ResearchSourceMetricsResponse(topic_key=normalized_topic, items=items)

    @app.post("/v2/research/governance/redact", response_model=ResearchRedactResponse)
    def research_governance_redact_endpoint(
        payload: ResearchRedactRequest,
        _: None = Depends(require_bearer),
    ) -> ResearchRedactResponse:
        normalized_topic = payload.topic_key.strip().lower()
        redacted = redact_research_raw_payloads(
            app.state.engine,
            topic_key=normalized_topic,
            older_than_days=payload.older_than_days,
        )
        return ResearchRedactResponse(
            topic_key=normalized_topic,
            older_than_days=payload.older_than_days,
            redacted_documents=redacted,
        )

    @app.get("/v2/research/review/queue", response_model=ResearchReviewQueueResponse)
    def research_review_queue_endpoint(
        topic_key: str,
        limit: int = 20,
        _: None = Depends(require_bearer),
    ) -> ResearchReviewQueueResponse:
        normalized_topic = topic_key.strip().lower()
        rows = list_research_review_queue(
            app.state.engine,
            topic_key=normalized_topic,
            limit=limit,
        )
        items = [
            ResearchReviewQueueItem(
                query_log_id=str(row.get("query_log_id")),
                trace_id=str(row.get("trace_id") or ""),
                query_text=str(row.get("query_text") or ""),
                candidate_count=int(row.get("candidate_count") or 0),
                returned_document_ids=[str(item) for item in (row.get("returned_document_ids") or [])],
                returned_chunk_ids=[str(item) for item in (row.get("returned_chunk_ids") or [])],
                status=str(row.get("status") or "ok"),
                error=(str(row.get("error")) if row.get("error") else None),
                useful_count=int(row.get("useful_count") or 0),
                not_useful_count=int(row.get("not_useful_count") or 0),
                created_at=row.get("created_at"),
            )
            for row in rows
        ]
        return ResearchReviewQueueResponse(topic_key=normalized_topic, items=items)

    return app


app = create_app()
