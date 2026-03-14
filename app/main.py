from __future__ import annotations

import logging
import os
import time
import uuid
import json
import hashlib
import re
from datetime import datetime, timezone
from collections import Counter, defaultdict, deque
from threading import Lock
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

from app.config import Settings, settings as default_settings
from app.research.contracts import (
    ResearchDecisionAlternative,
    ResearchDecisionPackResponse,
    ResearchDecisionRisk,
    ResearchFeedbackRequest,
    ResearchFeedbackResponse,
    ResearchMetric,
    ResearchDocumentModerationResponse,
    ResearchRedactRequest,
    ResearchRedactResponse,
    ResearchRecommendation,
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
    ResearchDocumentStagesResponse,
    ResearchDocumentStageCount,
    ResearchStorageUsageResponse,
    ResearchOpsProgressResponse,
    ResearchRunProgressRecord,
    ResearchAiUsageModelRecord,
    ResearchQuote,
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
    ResearchTopicDetailResponse,
    ResearchTopicDocument,
    ResearchTopicDocumentsResponse,
    ResearchTopicListResponse,
    ResearchTopicSearchResponse,
    ResearchTopicSummarizeRequest,
    ResearchTopicSummarizeResponse,
    ResearchTopicSummary,
    ResearchTopicTheme,
    ResearchTradeoff,
    ResearchWeeklyDigestItem,
    ResearchWeeklyDigestResponse,
    ResearchDomainSummaryResponse,
    ResearchEvidenceItem,
    ResearchEvidenceSearchResponse,
    ResearchEvidenceRelation,
    ResearchEvidenceRelatedResponse,
    ResearchEvidenceCompareCluster,
    ResearchEvidenceCompareResponse,
)
from app.research.embeddings import embed_texts, resolve_embedding_runtime
from app.research.scoring import blend_score, cosine_similarity, embedding_score, lexical_score, recency_score, source_weight_score
from app.research.ids import compute_source_id
from app.dashboard import (
    build_inbox,
    build_project_workspace,
    build_review_pack,
    build_today_dashboard,
    build_upcoming,
)
from app.models import (
    DashboardSummary,
    ChunkSearchRequest,
    ChunkSearchResponse,
    ContextPackRequest,
    ContextPackResponse,
    InboxResponse,
    IntelArticleStatusResponse,
    IntelIngestRequest,
    IntelIngestResponse,
    IntelIngestUrlsRequest,
    IntelIngestUrlsResponse,
    OutlineResponse,
    ProjectListItem,
    ProjectResponse,
    ProjectWorkspaceResponse,
    RelatedContextItem,
    ReviewPackResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SectionsRequest,
    SectionsResponse,
    SyncProjectsRequest,
    SyncTasksRequest,
    TodayDashboardResponse,
    TaskResponse,
    UpcomingResponse,
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
    list_research_document_stage_counts,
    get_research_storage_usage,
    list_research_run_progress,
    get_research_pipeline_counts,
    get_research_ai_usage_by_model,
    get_context_db_size_bytes,
    redact_research_raw_payloads,
    list_recent_research_documents,
    list_research_document_insights,
    list_research_evidence_relations,
    search_research_chunks,
    search_research_evidence,
    search_research_document_chunks,
    search_projects,
    search_tasks,
    set_research_document_suppressed,
    set_research_source_enabled,
    upsert_research_source,
    get_research_document,
    get_research_topic_detail,
    upsert_intel_article_seed,
    list_projects_page,
    list_tasks_with_projects,
    upsert_projects,
    upsert_tasks,
    list_research_documents_for_topic,
    list_research_source_metrics_for_topic,
    list_research_topics,
    collect_research_topic_themes,
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
_THEME_WORD_RE = re.compile(r"[a-z][a-z0-9_-]{3,}")


def _trim_text(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _redact_database_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    if not parsed.scheme:
        return database_url
    username = parsed.username or ""
    password = parsed.password or ""
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    auth = ""
    if username:
        auth = username
        if password:
            auth += ":***"
        auth += "@"
    path = parsed.path or ""
    return f"{parsed.scheme}://{auth}{host}{port}{path}"


def _runtime_banner_context(settings: Settings) -> Dict[str, Any]:
    storage_hint = settings.context_postgres_data_dir.strip() or "docker-managed volume"
    return {
        "database_url": _redact_database_url(settings.database_url),
        "storage_hint": storage_hint,
        "edge_proxy_enabled": bool(settings.edge_proxy_enabled),
        "persistent_corpus_guard_enabled": settings.context_api_expect_persistent_corpus,
        "expected_min_documents": settings.context_api_expected_min_documents,
        "default_topic": settings.context_api_research_topic_key,
    }


def _runtime_corpus_guard_state(settings: Settings, engine: Any) -> Dict[str, Any]:
    guard_enabled = bool(settings.context_api_expect_persistent_corpus)
    min_documents = max(int(settings.context_api_expected_min_documents or 0), 1) if guard_enabled else 0
    with engine.connect() as conn:
        documents = int(conn.execute(text("SELECT COUNT(*) FROM research_documents")).scalar_one())
        sources = int(conn.execute(text("SELECT COUNT(*) FROM research_sources")).scalar_one())
    remaining = max(min_documents - documents, 0) if guard_enabled else 0
    progress_pct = 100.0 if not guard_enabled or min_documents <= 0 else min(100.0, (float(documents) / float(min_documents)) * 100.0)
    ready = (not guard_enabled) or documents >= min_documents
    if ready:
        status_value = "ready"
        message = None
    else:
        status_value = "rebuilding"
        message = (
            "Research corpus is below the configured persistent-corpus threshold "
            f"({documents}/{min_documents} documents, {sources} sources). "
            "Serving in degraded ops mode until rebuild completes."
        )
    return {
        "guard_enabled": guard_enabled,
        "min_documents": min_documents,
        "current_documents": documents,
        "current_sources": sources,
        "remaining_documents": remaining,
        "progress_pct": round(progress_pct, 2),
        "ready": ready,
        "status": status_value,
        "message": message,
    }


def _validate_runtime_corpus(settings: Settings, engine: Any) -> Dict[str, Any]:
    state = _runtime_corpus_guard_state(settings, engine)
    if not settings.edge_proxy_enabled:
        logger.warning(
            "context_api_edge_proxy_disabled api started without edge overlay; "
            "context-api.localhost will not route until started with compose.edge.yml"
        )
    if not state["ready"] and state.get("message"):
        logger.warning(
            "context_api_runtime_guard_degraded status=%s current_documents=%s min_documents=%s sources=%s",
            state["status"],
            state["current_documents"],
            state["min_documents"],
            state["current_sources"],
        )
    return state


def _embedding_runtime() -> Dict[str, Any]:
    model = os.getenv("RESEARCH_EMBEDDING_MODEL", "text-embedding-3-small")
    return resolve_embedding_runtime(model=model, api_key=os.getenv("OPENAI_API_KEY", ""))


def _topic_label(topic_key: str) -> str:
    parts = [part for part in topic_key.replace("-", "_").split("_") if part]
    return " ".join(part.upper() if part.lower() == "ai" else part.capitalize() for part in parts) or topic_key


def _theme_candidates(*texts: str, max_items: int = 5) -> List[str]:
    stop = {
        "about",
        "also",
        "best",
        "current",
        "engineering",
        "management",
        "patterns",
        "practice",
        "practices",
        "product",
        "research",
        "software",
        "using",
        "with",
    }
    counts: Counter[str] = Counter()
    for text in texts:
        for token in _THEME_WORD_RE.findall((text or "").lower()):
            if token not in stop:
                counts[token] += 1
    return [item.replace("_", " ") for item, _ in counts.most_common(max_items)]


def _summarize_topic_documents(topic_key: str, documents: List[Dict[str, Any]], themes: List[Dict[str, Any]], focus: Optional[str]) -> str:
    label = _topic_label(topic_key)
    doc_titles = [str(doc.get("title") or "") for doc in documents[:3]]
    theme_names = [str(theme.get("name") or "") for theme in themes[:3] if str(theme.get("name") or "").strip()]
    if not theme_names:
        theme_names = _theme_candidates(*(doc_titles + [str(doc.get("summary") or "") for doc in documents[:3]]))
    theme_text = ", ".join(theme_names[:3]) if theme_names else "recent operational guidance"
    focus_text = f" focused on {focus.strip()}" if focus and focus.strip() else ""
    title_text = ", ".join(title for title in doc_titles if title) or "recent ingested documents"
    return (
        f"{label}{focus_text} currently emphasizes {theme_text}. "
        f"The most representative materials in this corpus include {title_text}. "
        f"Use the cited documents to extract concrete practices, compare tradeoffs, and check how recent the guidance is."
    )


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


def _map_metric_items(raw_items: Any) -> List[ResearchMetric]:
    items: List[ResearchMetric] = []
    if not isinstance(raw_items, list):
        return items
    for raw in raw_items:
        if not isinstance(raw, dict) or not str(raw.get("chunk_id") or "").strip():
            continue
        items.append(
            ResearchMetric(
                name=str(raw.get("name") or "metric"),
                value=str(raw.get("value") or ""),
                unit=str(raw.get("unit") or ""),
                qualifier=str(raw.get("qualifier") or ""),
                snippet=str(raw.get("snippet") or ""),
                chunk_id=str(raw.get("chunk_id") or ""),
            )
        )
    return items


def _map_quote_items(raw_items: Any) -> List[ResearchQuote]:
    items: List[ResearchQuote] = []
    if not isinstance(raw_items, list):
        return items
    for raw in raw_items:
        if not isinstance(raw, dict) or not str(raw.get("chunk_id") or "").strip():
            continue
        items.append(
            ResearchQuote(
                speaker=str(raw.get("speaker") or ""),
                text=str(raw.get("text") or ""),
                snippet=str(raw.get("snippet") or ""),
                chunk_id=str(raw.get("chunk_id") or ""),
            )
        )
    return items


def _map_tradeoff_items(raw_items: Any) -> List[ResearchTradeoff]:
    items: List[ResearchTradeoff] = []
    if not isinstance(raw_items, list):
        return items
    for raw in raw_items:
        if not isinstance(raw, dict) or not str(raw.get("chunk_id") or "").strip():
            continue
        items.append(
            ResearchTradeoff(
                benefit=str(raw.get("benefit") or ""),
                cost=str(raw.get("cost") or ""),
                condition=str(raw.get("condition") or ""),
                chunk_id=str(raw.get("chunk_id") or ""),
            )
        )
    return items


def _map_recommendation_items(raw_items: Any) -> List[ResearchRecommendation]:
    items: List[ResearchRecommendation] = []
    if not isinstance(raw_items, list):
        return items
    for raw in raw_items:
        if not isinstance(raw, dict) or not str(raw.get("chunk_id") or "").strip():
            continue
        items.append(
            ResearchRecommendation(
                action=str(raw.get("action") or ""),
                rationale=str(raw.get("rationale") or ""),
                applicability=str(raw.get("applicability") or ""),
                chunk_id=str(raw.get("chunk_id") or ""),
            )
        )
    return items


def _map_text_list(raw_items: Any) -> List[str]:
    if not isinstance(raw_items, list):
        return []
    values: List[str] = []
    for raw in raw_items:
        text_value = str(raw or "").strip()
        if text_value and text_value not in values:
            values.append(text_value)
    return values


def _map_evidence_item(row: Dict[str, Any]) -> ResearchEvidenceItem:
    return ResearchEvidenceItem(
        insight_id=str(row.get("insight_id") or ""),
        document_id=str(row.get("document_id") or ""),
        chunk_id=str(row.get("chunk_id") or ""),
        evidence_type=str(row.get("insight_type") or "claim"),
        text=str(row.get("text") or ""),
        normalized_payload=dict(row.get("normalized_payload") or {}),
        title=str(row.get("title") or ""),
        canonical_url=str(row.get("canonical_url") or ""),
        published_at=row.get("published_at"),
        source_id=str(row.get("source_id") or ""),
        source_class=str(row.get("source_class") or "external_commentary"),
        publisher_type=str(row.get("publisher_type") or "independent"),
        topic_tags=_map_text_list(row.get("topic_tags")),
        entity_tags=_map_text_list(row.get("entity_tags")),
        decision_domains=_map_text_list(row.get("decision_domains")),
        problem_tags=_map_text_list(row.get("problem_tags")),
        intervention_tags=_map_text_list(row.get("intervention_tags")),
        tradeoff_dimensions=_map_text_list(row.get("tradeoff_dimensions")),
        applicability_conditions=_map_text_list(row.get("applicability_conditions")),
        confidence=float(row.get("confidence") or 0.0),
        evidence_strength=float(row.get("evidence_strength") or 0.0),
        source_trust_tier=float(row.get("source_trust_tier") or 0.0),
        freshness_score=float(row.get("freshness_score") or 0.0),
        corroboration_count=int(row.get("corroboration_count") or 0),
        contradiction_count=int(row.get("contradiction_count") or 0),
        coverage_score=float(row.get("coverage_score") or 0.0),
        internal_coverage_score=float(row.get("internal_coverage_score") or 0.0),
        external_coverage_score=float(row.get("external_coverage_score") or 0.0),
        evidence_quality=float(row.get("evidence_quality") or 0.0),
        staleness_flag=bool(row.get("staleness_flag") or False),
        superseded_flag=bool(row.get("superseded_flag") or False),
        citation=ResearchCitation(
            document_id=str(row.get("document_id") or ""),
            chunk_id=str(row.get("chunk_id") or ""),
        ),
    )


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _elapsed_seconds(started_at: Any, finished_at: Any) -> int:
    if not started_at:
        return 0
    if isinstance(started_at, str):
        try:
            started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        except ValueError:
            return 0
    else:
        started = started_at
    if not isinstance(started, datetime):
        return 0
    if finished_at is None:
        end = datetime.now(timezone.utc)
    elif isinstance(finished_at, str):
        try:
            end = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
        except ValueError:
            end = datetime.now(timezone.utc)
    else:
        end = finished_at if isinstance(finished_at, datetime) else datetime.now(timezone.utc)
    started_utc = started if started.tzinfo else started.replace(tzinfo=timezone.utc)
    end_utc = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
    return max(int((end_utc - started_utc).total_seconds()), 0)


def _read_meminfo_bytes() -> Dict[str, int]:
    values_kib: Dict[str, int] = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if ":" not in line:
                    continue
                key, rest = line.split(":", 1)
                raw = rest.strip().split(" ", 1)[0]
                try:
                    values_kib[key.strip()] = int(raw)
                except ValueError:
                    continue
    except Exception:
        return {
            "memory_total_bytes": 0,
            "memory_available_bytes": 0,
            "memory_used_bytes": 0,
            "memory_used_pct": 0.0,
        }

    total = int(values_kib.get("MemTotal", 0) * 1024)
    available = int(values_kib.get("MemAvailable", values_kib.get("MemFree", 0)) * 1024)
    used = max(total - available, 0)
    used_pct = (float(used) / float(total) * 100.0) if total > 0 else 0.0
    return {
        "memory_total_bytes": total,
        "memory_available_bytes": available,
        "memory_used_bytes": used,
        "memory_used_pct": used_pct,
    }


def _topic_default_policy() -> Dict[str, Any]:
    return {
        "poll_interval_minutes": _to_int(os.getenv("RESEARCH_DEFAULT_POLL_INTERVAL_MINUTES", "60")) or 60,
        "rate_limit_per_hour": _to_int(os.getenv("RESEARCH_DEFAULT_RATE_LIMIT_PER_HOUR", "30")) or 30,
        "source_weight": float(os.getenv("RESEARCH_DEFAULT_SOURCE_WEIGHT", "1.0")),
        "robots_mode": os.getenv("RESEARCH_ROBOTS_MODE", "strict").strip().lower() or "strict",
    }


def _render_ops_dashboard_html(*, default_token: str, default_topic: str, runtime_info: Dict[str, Any]) -> str:
    return (
        OPS_DASHBOARD_HTML
        .replace("__DEFAULT_TOKEN__", json.dumps(default_token))
        .replace("__DEFAULT_TOPIC__", json.dumps(default_topic))
        .replace("__RUNTIME_INFO__", json.dumps(runtime_info, separators=(",", ":")))
    )


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


OPS_DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Context API Research Ops</title>
  <link rel="icon" href="data:," />
  <style>
    :root { color-scheme: light; --bg:#f5f7fb; --card:#fff; --ink:#0f172a; --muted:#64748b; --line:#e2e8f0; --ok:#0a7a3f; --warn:#b45309; --bad:#b91c1c; }
    body { margin:0; font-family: "Segoe UI",Tahoma,sans-serif; background:var(--bg); color:var(--ink); }
    .wrap { max-width:1100px; margin:0 auto; padding:16px; }
    .toolbar { display:grid; grid-template-columns:2fr 2fr 1fr auto; gap:8px; margin-bottom:12px; }
    input,select,button { padding:10px; border:1px solid var(--line); border-radius:8px; font-size:14px; }
    button { cursor:pointer; background:#0f172a; color:#fff; }
    .grid { display:grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap:10px; }
    .card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px; }
    .k { color:var(--muted); font-size:12px; }
    .v { font-size:24px; font-weight:700; margin-top:4px; }
    table { width:100%; border-collapse: collapse; font-size:13px; }
    th,td { border-bottom:1px solid var(--line); padding:8px 6px; text-align:left; vertical-align:top; }
    th { color:var(--muted); font-weight:600; }
    .status-running { color:var(--warn); font-weight:700; }
    .status-completed { color:var(--ok); font-weight:700; }
    .status-failed { color:var(--bad); font-weight:700; }
    .muted { color:var(--muted); }
    pre { white-space: pre-wrap; background:#0b1020; color:#dbeafe; padding:10px; border-radius:8px; max-height:220px; overflow:auto; }
  </style>
</head>
<body>
  <div class="wrap">
    <h2>Context API Research Ops Dashboard</h2>
    <form class="toolbar" id="controls">
      <input type="text" autocomplete="username" value="context-api-ops" style="display:none" />
      <input id="token" type="password" placeholder="Bearer token (CONTEXT_API_TOKEN)" autocomplete="current-password" />
      <input id="topic" value="ai_research" placeholder="topic_key" />
      <select id="refresh">
        <option value="10">10s</option>
        <option value="30" selected>30s</option>
        <option value="60">60s</option>
      </select>
      <button id="load" type="submit">Refresh</button>
    </form>
    <div class="card" style="margin-bottom:10px;" id="runtimeBanner"></div>
    <div class="grid" id="summaryCards"></div>
    <div class="card" style="margin-top:10px;">
      <div class="k">Run Progress</div>
      <table><thead><tr><th>Run</th><th>Status</th><th>Elapsed</th><th>Sources</th><th>Seen</th><th>New</th><th>Failed</th></tr></thead><tbody id="runsBody"></tbody></table>
    </div>
    <div class="card" style="margin-top:10px;">
      <div class="k">Pipeline Progress</div>
      <table><thead><tr><th>Stage</th><th>Count</th></tr></thead><tbody id="processBody"></tbody></table>
    </div>
    <div class="card" style="margin-top:10px;">
      <div class="k">Document Stages</div>
      <table><thead><tr><th>Status</th><th>Count</th></tr></thead><tbody id="stagesBody"></tbody></table>
    </div>
    <div class="card" style="margin-top:10px;">
      <div class="k">Storage Usage</div>
      <table><thead><tr><th>Component</th><th>Bytes</th><th>MiB</th></tr></thead><tbody id="storageBody"></tbody></table>
    </div>
    <div class="card" style="margin-top:10px;">
      <div class="k">AI Usage</div>
      <table><thead><tr><th>Model</th><th>External API</th><th>Docs</th><th>Chunks</th><th>Est Tokens</th><th>Est Tokens 24h</th></tr></thead><tbody id="aiBody"></tbody></table>
    </div>
    <div class="card" style="margin-top:10px;">
      <div class="k">System Resources</div>
      <table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody id="resourceBody"></tbody></table>
    </div>
    <div class="card" style="margin-top:10px;">
      <div class="k">Sources</div>
      <table><thead><tr><th>Name</th><th>Enabled</th><th>Failures</th><th>Cooldown</th><th>Docs</th><th>Embedded</th><th>Failed</th></tr></thead><tbody id="sourcesBody"></tbody></table>
    </div>
    <div class="card" style="margin-top:10px;">
      <div class="k">Latest Open/Recent Run</div>
      <pre id="runJson" class="muted">{}</pre>
    </div>
  </div>
  <script>
    const bootstrap = {
      token: __DEFAULT_TOKEN__,
      topic: __DEFAULT_TOPIC__,
      runtime: __RUNTIME_INFO__
    };
    const el = (id) => document.getElementById(id);
    const tokenEl = el("token");
    const topicEl = el("topic");
    const refreshEl = el("refresh");
    const loadBtn = el("load");
    const controlsEl = el("controls");
    const runtimeBanner = el("runtimeBanner");
    const cards = el("summaryCards");
    const runsBody = el("runsBody");
    const processBody = el("processBody");
    const stagesBody = el("stagesBody");
    const storageBody = el("storageBody");
    const aiBody = el("aiBody");
    const resourceBody = el("resourceBody");
    const sourcesBody = el("sourcesBody");
    const runJson = el("runJson");
    const keyToken = "ctx_ops_token";
    const keyTopic = "ctx_ops_topic";
    const storedToken = localStorage.getItem(keyToken) || "";
    const storedTopic = localStorage.getItem(keyTopic) || "";
    tokenEl.value = bootstrap.token || storedToken || "";
    topicEl.value = storedTopic || bootstrap.topic || topicEl.value;
    if (bootstrap.token && storedToken !== bootstrap.token) localStorage.setItem(keyToken, bootstrap.token);
    if (!storedTopic && (bootstrap.topic || topicEl.value)) localStorage.setItem(keyTopic, bootstrap.topic || topicEl.value);
    let timer = null;

    function hdrs() {
      const t = tokenEl.value.trim() || bootstrap.token || "";
      return t ? { "Authorization": "Bearer " + t } : {};
    }

    async function jget(path, retryWithBootstrap = true) {
      const r = await fetch(path, { headers: hdrs() });
      if (r.status === 401 && retryWithBootstrap && bootstrap.token && tokenEl.value.trim() !== bootstrap.token) {
        tokenEl.value = bootstrap.token;
        localStorage.setItem(keyToken, bootstrap.token);
        return await jget(path, false);
      }
      if (!r.ok) {
        let detail = "";
        try {
          const payload = await r.json();
          detail = payload && payload.detail ? String(payload.detail) : "";
        } catch (_) {}
        throw new Error(`${path} -> ${r.status}${detail ? " (" + detail + ")" : ""}`);
      }
      return await r.json();
    }

    function card(k, v) {
      return `<div class="card"><div class="k">${k}</div><div class="v">${v}</div></div>`;
    }
    function esc(v) {
      return String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
    function mib(n) {
      return (Number(n || 0) / (1024 * 1024)).toFixed(2);
    }
    function secToHuman(seconds) {
      const s = Number(seconds || 0);
      if (s < 60) return `${s}s`;
      const m = Math.floor(s / 60);
      const r = s % 60;
      if (m < 60) return `${m}m ${r}s`;
      const h = Math.floor(m / 60);
      return `${h}h ${m % 60}m`;
    }

    function renderRuntimeBanner() {
      const runtime = bootstrap.runtime || {};
      const liveGuard = runtime.guard || {};
      const guard = runtime.persistent_corpus_guard_enabled
        ? `enabled (min docs: ${runtime.expected_min_documents})`
        : "disabled";
      const progress = runtime.persistent_corpus_guard_enabled
        ? `${Number(liveGuard.progress_pct || 0).toFixed(1)}% (${liveGuard.current_documents || 0}/${liveGuard.min_documents || runtime.expected_min_documents || 0})`
        : "n/a";
      const status = runtime.persistent_corpus_guard_enabled
        ? (liveGuard.status || "unknown")
        : "ready";
      runtimeBanner.innerHTML = `
        <div class="k">Runtime</div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-top:8px;">
          <div style="min-width:0;"><div class="k">Database</div><div style="word-break:break-word;overflow-wrap:anywhere;line-height:1.35;">${esc(runtime.database_url || "unknown")}</div></div>
          <div style="min-width:0;"><div class="k">Storage</div><div style="word-break:break-word;overflow-wrap:anywhere;line-height:1.35;">${esc(runtime.storage_hint || "unknown")}</div></div>
          <div style="min-width:0;"><div class="k">Edge Routing</div><div style="word-break:break-word;overflow-wrap:anywhere;line-height:1.35;">${runtime.edge_proxy_enabled ? "enabled" : "disabled - start with compose.edge.yml / make up"}</div></div>
          <div style="min-width:0;"><div class="k">Corpus Guard</div><div style="word-break:break-word;overflow-wrap:anywhere;line-height:1.35;">${esc(guard)}</div></div>
          <div style="min-width:0;"><div class="k">Guard Status</div><div style="word-break:break-word;overflow-wrap:anywhere;line-height:1.35;">${esc(status)}</div></div>
          <div style="min-width:0;"><div class="k">Threshold Progress</div><div style="word-break:break-word;overflow-wrap:anywhere;line-height:1.35;">${esc(progress)}</div></div>
          <div style="min-width:0;"><div class="k">Default Topic</div><div style="word-break:break-word;overflow-wrap:anywhere;line-height:1.35;">${esc(runtime.default_topic || "ai_research")}</div></div>
        </div>`;
    }

    async function refresh() {
      if (!tokenEl.value.trim() && bootstrap.token) {
        tokenEl.value = bootstrap.token;
      }
      if (!topicEl.value.trim() && bootstrap.topic) {
        topicEl.value = bootstrap.topic;
      }
      localStorage.setItem(keyToken, tokenEl.value);
      localStorage.setItem(keyTopic, topicEl.value);
      if (!tokenEl.value.trim()) {
        cards.innerHTML = `<div class="card"><div class="k">Auth Required</div><div class="v" style="font-size:14px">No dashboard bearer token is configured server-side. Set CONTEXT_API_TOKEN or enter one manually.</div></div>`;
        runsBody.innerHTML = "";
        processBody.innerHTML = "";
        stagesBody.innerHTML = "";
        storageBody.innerHTML = "";
        aiBody.innerHTML = "";
        resourceBody.innerHTML = "";
        sourcesBody.innerHTML = "";
        runJson.textContent = "{}";
        return;
      }
      const topic = encodeURIComponent(topicEl.value.trim() || "ai_research");
      try {
        const results = await Promise.allSettled([
          jget(`/v2/research/ops/summary?topic_key=${topic}`),
          jget(`/v2/research/ops/sources?topic_key=${topic}&limit=20`),
          jget(`/v2/research/ops/documents?topic_key=${topic}`),
          jget(`/v2/research/ops/storage?topic_key=${topic}`),
          jget(`/v2/research/ops/progress?topic_key=${topic}&run_limit=12`)
        ]);
        const errors = results.filter(r => r.status === "rejected").map(r => String(r.reason));
        const summary = results[0].status === "fulfilled" ? results[0].value : null;
        const sources = results[1].status === "fulfilled" ? results[1].value : { items: [] };
        const stages = results[2].status === "fulfilled" ? results[2].value : { items: [] };
        const storage = results[3].status === "fulfilled" ? results[3].value : null;
        const progress = results[4].status === "fulfilled" ? results[4].value : null;

        cards.innerHTML = summary ? [
          card("Sources", summary.sources_total),
          card("In Cooldown", summary.sources_in_cooldown),
          card("Docs Total", summary.documents_total),
          card("Docs Embedded", summary.documents_embedded),
          card("Runs Open", summary.runs_open),
          card("Guard Status", summary.corpus_guard_status || "ready"),
          card("Threshold Progress", `${Number(summary.corpus_guard_progress_pct || 0).toFixed(1)}%`),
          card("Docs To Threshold", summary.corpus_guard_remaining_documents || 0),
          card("24h Run Fail Rate", (summary.run_failure_rate_24h * 100).toFixed(1) + "%"),
          card("Queued Runs", progress ? progress.queued_runs : 0),
          card("Running Runs", progress ? progress.running_runs : 0),
        ].join("") : `<div class="card"><div class="k">Summary Unavailable</div><div class="v" style="font-size:14px">See error details below.</div></div>`;

        runsBody.innerHTML = progress && (progress.runs || []).length
          ? (progress.runs || []).map(r => `<tr>
            <td>${String(r.run_id || "").slice(0, 8)}</td>
            <td>${r.status}</td>
            <td>${secToHuman(r.elapsed_seconds)}</td>
            <td>${r.sources_selected}</td>
            <td>${r.items_seen}</td>
            <td>${r.items_new}</td>
            <td>${r.items_failed}</td>
          </tr>`).join("")
          : `<tr><td colspan="7" class="muted">No run records yet.</td></tr>`;

        processBody.innerHTML = progress ? [
          ["corpus_guard_status", progress.corpus_guard_status || "ready"],
          ["threshold_progress_pct", `${Number(progress.corpus_guard_progress_pct || 0).toFixed(1)}%`],
          ["threshold_current_documents", progress.corpus_guard_current_documents || 0],
          ["threshold_remaining_documents", progress.corpus_guard_remaining_documents || 0],
          ["discovered", progress.stages?.discovered || 0],
          ["fetched", progress.stages?.fetched || 0],
          ["extracted", progress.stages?.extracted || 0],
          ["embedded", progress.stages?.embedded || 0],
          ["failed", progress.stages?.failed || 0],
          ["chunks_count", progress.chunks_count || 0],
          ["embeddings_count", progress.embeddings_count || 0],
          ["embedding_coverage_pct", `${Number(progress.embedding_coverage_pct || 0).toFixed(1)}%`],
        ].map(x => `<tr><td>${x[0]}</td><td>${x[1]}</td></tr>`).join("")
          : `<tr><td colspan="2" class="muted">Pipeline progress unavailable.</td></tr>`;

        stagesBody.innerHTML = (stages.items || []).length
          ? (stages.items || []).map(x => `<tr><td>${x.status}</td><td>${x.count}</td></tr>`).join("")
          : `<tr><td colspan="2" class="muted">No documents yet for this topic.</td></tr>`;

        storageBody.innerHTML = storage ? [
          ["Raw Payload", storage.raw_payload_bytes],
          ["Extracted Text", storage.extracted_text_bytes],
          ["Chunks", storage.chunks_bytes],
          ["Embeddings", storage.embeddings_bytes],
          ["Total", storage.total_bytes]
        ].map(x => `<tr><td>${x[0]}</td><td>${x[1]}</td><td>${mib(x[1])}</td></tr>`).join("")
          : `<tr><td colspan="3" class="muted">Storage metrics unavailable.</td></tr>`;

        aiBody.innerHTML = progress && (progress.ai_models || []).length
          ? (progress.ai_models || []).map(a => `<tr>
            <td>${a.embedding_model_id}</td>
            <td>${a.external_api}</td>
            <td>${a.documents_count}</td>
            <td>${a.chunks_count}</td>
            <td>${a.estimated_tokens_total}</td>
            <td>${a.estimated_tokens_24h}</td>
          </tr>`).join("")
          : `<tr><td colspan="6" class="muted">No AI usage records yet.</td></tr>`;

        resourceBody.innerHTML = progress ? [
          ["DB Size", `${progress.db_size_bytes} bytes (${mib(progress.db_size_bytes)} MiB)`],
          ["Disk Total", `${progress.disk_total_bytes} bytes (${mib(progress.disk_total_bytes)} MiB)`],
          ["Disk Used", `${progress.disk_used_bytes} bytes (${mib(progress.disk_used_bytes)} MiB)`],
          ["Disk Free", `${progress.disk_free_bytes} bytes (${mib(progress.disk_free_bytes)} MiB)`],
          ["Disk Used %", `${Number(progress.disk_used_pct || 0).toFixed(1)}%`],
          ["CPU Cores", progress.cpu_count || 0],
          ["CPU Load (1m)", Number(progress.cpu_load_1m || 0).toFixed(2)],
          ["CPU Load (5m)", Number(progress.cpu_load_5m || 0).toFixed(2)],
          ["CPU Load (15m)", Number(progress.cpu_load_15m || 0).toFixed(2)],
          ["Memory Total", `${progress.memory_total_bytes} bytes (${mib(progress.memory_total_bytes)} MiB)`],
          ["Memory Used", `${progress.memory_used_bytes} bytes (${mib(progress.memory_used_bytes)} MiB)`],
          ["Memory Available", `${progress.memory_available_bytes} bytes (${mib(progress.memory_available_bytes)} MiB)`],
          ["Memory Used %", `${Number(progress.memory_used_pct || 0).toFixed(1)}%`],
          ["Ext API Calls (est)", progress.ai_external_calls_estimate || 0],
          ["Ext API Tokens (est total)", progress.ai_estimated_tokens_total || 0],
          ["Ext API Tokens (est 24h)", progress.ai_estimated_tokens_24h || 0],
        ].map(x => `<tr><td>${x[0]}</td><td>${x[1]}</td></tr>`).join("")
          : `<tr><td colspan="2" class="muted">System resources unavailable.</td></tr>`;

        sourcesBody.innerHTML = (sources.items || []).length
          ? (sources.items || []).map(s => `<tr>
          <td>${s.name}</td>
          <td>${s.enabled}</td>
          <td>${s.consecutive_failures}</td>
          <td>${s.cooldown_until || ""}</td>
          <td>${s.documents_total}</td>
          <td>${s.documents_embedded}</td>
          <td>${s.documents_failed}</td>
        </tr>`).join("")
          : `<tr><td colspan="7" class="muted">No sources yet for this topic.</td></tr>`;

        const openRun = await jget(`/v2/research/review/queue?topic_key=${topic}&limit=1`).catch(() => null);
        if (summary) {
          bootstrap.runtime = {
            ...(bootstrap.runtime || {}),
            guard: {
              status: summary.corpus_guard_status,
              progress_pct: summary.corpus_guard_progress_pct,
              current_documents: summary.corpus_guard_current_documents,
              min_documents: summary.corpus_guard_min_documents,
              remaining_documents: summary.corpus_guard_remaining_documents,
              ready: summary.corpus_guard_ready,
              message: summary.corpus_guard_message
            }
          };
          renderRuntimeBanner();
        }
        runJson.textContent = JSON.stringify({ summary, openRun, errors }, null, 2);
      } catch (e) {
        cards.innerHTML = `<div class="card"><div class="k">Error</div><div class="v" style="font-size:14px">${String(e)}</div></div>`;
      }
    }

    function startTimer() {
      if (timer) clearInterval(timer);
      timer = setInterval(refresh, Number(refreshEl.value) * 1000);
    }

    controlsEl.addEventListener("submit", (event) => {
      event.preventDefault();
      refresh();
    });
    refreshEl.addEventListener("change", startTimer);
    renderRuntimeBanner();
    refresh(); startTimer();
  </script>
</body>
</html>"""


def create_app(app_settings: Settings | None = None) -> FastAPI:
    app_settings = app_settings or default_settings
    app = FastAPI()

    app.state.settings = app_settings
    app.state.engine = create_db_engine(app_settings.database_url)
    app.state.runtime_banner = _runtime_banner_context(app_settings)
    app.state.runtime_guard = {
        "guard_enabled": bool(app_settings.context_api_expect_persistent_corpus),
        "min_documents": max(int(app_settings.context_api_expected_min_documents or 0), 1) if app_settings.context_api_expect_persistent_corpus else 0,
        "current_documents": 0,
        "current_sources": 0,
        "remaining_documents": 0,
        "progress_pct": 0.0,
        "ready": not app_settings.context_api_expect_persistent_corpus,
        "status": "starting",
        "message": None,
    }

    @app.on_event("startup")
    def _startup_validate_runtime() -> None:
        app.state.runtime_guard = _validate_runtime_corpus(app_settings, app.state.engine)

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
        guard_state = _validate_runtime_corpus(app.state.settings, app.state.engine)
        app.state.runtime_guard = guard_state
        if not guard_state["ready"]:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=guard_state["message"] or "Research corpus is rebuilding",
            )
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

    @app.get("/v1/dashboard/today", response_model=TodayDashboardResponse)
    def dashboard_today_endpoint(
        _: None = Depends(require_bearer),
    ) -> TodayDashboardResponse:
        project_rows = list_projects_page(app.state.engine, limit=200)
        task_rows = list_tasks_with_projects(app.state.engine, limit=1000)
        return build_today_dashboard(project_rows, task_rows)

    @app.get("/v1/dashboard/upcoming", response_model=UpcomingResponse)
    def dashboard_upcoming_endpoint(
        _: None = Depends(require_bearer),
    ) -> UpcomingResponse:
        task_rows = list_tasks_with_projects(app.state.engine, limit=1000)
        return build_upcoming(task_rows)

    @app.get("/v1/projects/{project_id}/workspace", response_model=ProjectWorkspaceResponse)
    def project_workspace_endpoint(
        project_id: str,
        _: None = Depends(require_bearer),
    ) -> ProjectWorkspaceResponse:
        project_row = get_project(app.state.engine, project_id)
        if not project_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        project_rows = list_projects_page(app.state.engine, limit=200)
        task_rows = list_tasks_with_projects(app.state.engine, limit=1000, project_id=project_id)
        related_topics = list_research_topics(
            app.state.engine,
            query=str(project_row.get("name") or project_id),
            limit=4,
        )
        return build_project_workspace(project_row, project_rows, task_rows, related_topics)

    @app.get("/v1/inbox", response_model=InboxResponse)
    def inbox_endpoint(
        _: None = Depends(require_bearer),
    ) -> InboxResponse:
        task_rows = list_tasks_with_projects(app.state.engine, limit=1000)
        return build_inbox(task_rows)

    @app.get("/v1/reviews/daily", response_model=ReviewPackResponse)
    def daily_review_endpoint(
        _: None = Depends(require_bearer),
    ) -> ReviewPackResponse:
        project_rows = list_projects_page(app.state.engine, limit=200)
        task_rows = list_tasks_with_projects(app.state.engine, limit=1000)
        return build_review_pack(mode="daily", project_rows=project_rows, task_rows=task_rows)

    @app.get("/v1/reviews/weekly", response_model=ReviewPackResponse)
    def weekly_review_endpoint(
        _: None = Depends(require_bearer),
    ) -> ReviewPackResponse:
        project_rows = list_projects_page(app.state.engine, limit=200)
        task_rows = list_tasks_with_projects(app.state.engine, limit=1000)
        return build_review_pack(mode="weekly", project_rows=project_rows, task_rows=task_rows)

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
            publisher_type=payload.publisher_type.strip().lower(),
            source_class=payload.source_class.strip().lower(),
            default_decision_domains=[tag.strip().lower() for tag in payload.default_decision_domains if tag.strip()],
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
                    publisher_type=str(row.get("publisher_type") or "independent"),
                    source_class=str(row.get("source_class") or "external_commentary"),
                    default_decision_domains=[str(value) for value in (row.get("default_decision_domains") or [])],
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
                    publisher_type=(suggestion.publisher_type or "independent").strip().lower(),
                    source_class=(suggestion.source_class or "external_commentary").strip().lower(),
                    default_decision_domains=[tag.strip().lower() for tag in suggestion.default_decision_domains if tag.strip()],
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

    @app.post(
        "/v2/research/documents/{document_id}/suppress",
        response_model=ResearchDocumentModerationResponse,
    )
    def suppress_research_document_endpoint(
        document_id: str,
        reason: str = "manual",
        _: None = Depends(require_bearer),
    ) -> ResearchDocumentModerationResponse:
        updated = set_research_document_suppressed(
            app.state.engine,
            document_id=document_id,
            suppressed=True,
            reason=reason,
        )
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        return ResearchDocumentModerationResponse(
            document_id=document_id,
            suppressed=True,
            suppression_reason=reason.strip() or "manual",
            status="updated",
        )

    @app.post(
        "/v2/research/documents/{document_id}/unsuppress",
        response_model=ResearchDocumentModerationResponse,
    )
    def unsuppress_research_document_endpoint(
        document_id: str,
        _: None = Depends(require_bearer),
    ) -> ResearchDocumentModerationResponse:
        updated = set_research_document_suppressed(
            app.state.engine,
            document_id=document_id,
            suppressed=False,
        )
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        return ResearchDocumentModerationResponse(
            document_id=document_id,
            suppressed=False,
            suppression_reason=None,
            status="updated",
        )

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
        embedding_runtime = _embedding_runtime()
        embedding_model_id = str(embedding_runtime["model"])
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
                decision_domain=payload.decision_domain,
                content_types=payload.content_types or None,
                source_classes=payload.source_classes or None,
                publisher_types=payload.publisher_types or None,
                exclude_content_types=payload.exclude_content_types or None,
                evidence_types=payload.evidence_types or None,
                problem_tags=payload.problem_tags or None,
                intervention_tags=payload.intervention_tags or None,
                tradeoff_dimensions=payload.tradeoff_dimensions or None,
                corpus_preference=payload.corpus_preference,
                source_trust_min=payload.source_trust_min,
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
                signal_value = min(1.0, float(row.get("document_signal_score") or 0.0))
                source_class = str(row.get("source_class") or "external_commentary")
                trust_value = 1.0 if source_class == "internal_authoritative" else 0.8 if source_class == "external_primary" else 0.55
                intent_fit = 0.5
                if payload.intent_mode == "decision_support":
                    if payload.decision_domain and payload.decision_domain in (row.get("decision_domains") or []):
                        intent_fit = 1.0
                    elif row.get("recommendations") or row.get("tradeoffs"):
                        intent_fit = 0.8
                elif payload.intent_mode == "editorial":
                    has_metric = bool(row.get("metrics"))
                    has_quote = bool(row.get("notable_quotes"))
                    intent_fit = 1.0 if has_metric or has_quote else 0.55
                if "metrics" in payload.must_have and not row.get("metrics"):
                    continue
                if "quotes" in payload.must_have and not row.get("notable_quotes"):
                    continue
                if "recommendations" in payload.must_have and not row.get("recommendations"):
                    continue
                if "tradeoffs" in payload.must_have and not row.get("tradeoffs"):
                    continue
                if "internal" in payload.must_have and source_class != "internal_authoritative":
                    continue
                if "recent" in payload.must_have and recency_value < 0.4:
                    continue
                if payload.problem_tags:
                    row_problem_tags = {str(value) for value in (row.get("problem_tags") or [])}
                    if not row_problem_tags.intersection({tag.strip().lower() for tag in payload.problem_tags}):
                        continue
                if payload.intervention_tags:
                    row_intervention_tags = {str(value) for value in (row.get("intervention_tags") or [])}
                    if not row_intervention_tags.intersection({tag.strip().lower() for tag in payload.intervention_tags}):
                        continue
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
                score["signal"] = signal_value
                score["trust"] = trust_value
                score["intent_fit"] = intent_fit
                score["total"] = min(1.0, float(score.get("total") or 0.0) + 0.1 * signal_value + 0.05 * trust_value + 0.1 * intent_fit)
                merged = dict(row)
                merged["_score"] = score
                ranked.append(merged)
            if payload.sort_mode == "recent":
                ranked.sort(key=lambda row: (row.get("published_at") or datetime.fromtimestamp(0, tz=timezone.utc), float((row.get("_score") or {}).get("total") or 0.0)), reverse=True)
            elif payload.sort_mode == "signal":
                ranked.sort(key=lambda row: (float(row.get("document_signal_score") or 0.0), float((row.get("_score") or {}).get("total") or 0.0)), reverse=True)
            elif payload.sort_mode == "novelty":
                ranked.sort(key=lambda row: (len(row.get("topic_tags") or []), float((row.get("_score") or {}).get("total") or 0.0)), reverse=True)
            else:
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
            grouped_rows: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for row in ranked:
                document_id = str(row.get("document_id") or "")
                if document_id:
                    grouped_rows[document_id].append(row)

            for document_id, doc_rows in grouped_rows.items():
                if document_id in seen_docs:
                    continue
                best = doc_rows[0]
                score = best.get("_score") or {}
                total_score = float(score.get("total") or 0.0)
                if payload.min_relevance_score is not None and total_score < payload.min_relevance_score:
                    continue
                citations: List[ResearchCitation] = []
                signals: List[ResearchSignal] = []
                summary_parts: List[str] = []
                for row in doc_rows[:3]:
                    chunk_id = str(row.get("chunk_id") or "")
                    snippet = _clean_snippet(str(row.get("snippet") or row.get("content") or ""))
                    if not chunk_id or not snippet:
                        continue
                    citation = ResearchCitation(document_id=document_id, chunk_id=chunk_id)
                    citations.append(citation)
                    returned_chunk_ids.append(chunk_id)
                    heading_path = []
                    chunk_meta = row.get("chunk_meta") or {}
                    if isinstance(chunk_meta, dict):
                        heading_path = [str(part) for part in (chunk_meta.get("heading_path") or []) if str(part).strip()]
                    why = "Hybrid relevance from lexical, embedding, recency, and source weighting."
                    if heading_path:
                        why = f"{why} Section context: {' > '.join(heading_path[:3])}."
                    signals.append(
                        ResearchSignal(
                            claim=_trim_text(snippet, 240),
                            why=why,
                            cite=citation,
                        )
                    )
                    summary_parts.append(snippet)
                if not citations:
                    continue
                items.append(
                    ResearchContextPackItem(
                        document_id=document_id,
                        source_id=str(best.get("source_id") or ""),
                        title=str(best.get("title") or ""),
                        canonical_url=str(best.get("canonical_url") or ""),
                        published_at=best.get("published_at"),
                        summary=_trim_text(str(best.get("summary_short") or " ".join(summary_parts)), DEFAULT_RESEARCH_MAX_CHARS),
                        content_type=str(best.get("content_type") or "company_blog"),
                        publisher_type=str(best.get("publisher_type") or "independent"),
                        source_class=str(best.get("source_class") or "external_commentary"),
                        topic_tags=[str(value) for value in (best.get("topic_tags") or [])],
                        decision_domains=[str(value) for value in (best.get("decision_domains") or [])],
                        metrics=_map_metric_items(best.get("metrics")),
                        notable_quotes=_map_quote_items(best.get("notable_quotes")),
                        tradeoffs=_map_tradeoff_items(best.get("tradeoffs")),
                        recommendations=_map_recommendation_items(best.get("recommendations")),
                        document_signal_score=float(best.get("document_signal_score") or 0.0),
                        evidence_quality=float(best.get("evidence_quality") or 0.0),
                        corroboration_count=int(best.get("corroboration_count") or 0),
                        contradiction_count=int(best.get("contradiction_count") or 0),
                        freshness_score=float(best.get("freshness_score") or 0.0),
                        coverage_score=float(best.get("coverage_score") or 0.0),
                        problem_tags=_map_text_list(best.get("problem_tags")),
                        intervention_tags=_map_text_list(best.get("intervention_tags")),
                        tradeoff_dimensions=_map_text_list(best.get("tradeoff_dimensions")),
                        signals=signals,
                        citations=citations,
                        score_breakdown=ResearchScoreBreakdown(
                            total=total_score,
                            lexical=float(score.get("lexical") or 0.0),
                            embedding=float(score.get("embedding") or 0.0),
                            recency=float(score.get("recency") or 0.0),
                            source_weight=float(score.get("source_weight") or 0.0),
                            signal=float(score.get("signal") or 0.0),
                            trust=float(score.get("trust") or 0.0),
                            intent_fit=float(score.get("intent_fit") or 0.0),
                        ),
                    )
                )
                seen_docs.add(document_id)
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
                    embedding_model_id=embedding_model_id,
                    embedding_mode=str(embedding_runtime["mode"]),
                    embedding_warning=embedding_runtime.get("warning"),
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
            chunk_meta = row.get("chunk_meta") or {}
            heading_path = []
            if isinstance(chunk_meta, dict):
                heading_path = [str(part) for part in (chunk_meta.get("heading_path") or []) if str(part).strip()]
            chunks.append(
                {
                    "chunk_id": str(row.get("chunk_id") or ""),
                    "snippet": _trim_text(snippet, max_chars),
                    "score": float(row.get("score")) if row.get("score") is not None else None,
                    "heading_path": heading_path,
                }
            )
        return ResearchChunkSearchResponse(document_id=document_id, chunks=chunks)

    @app.post("/v2/research/evidence/search", response_model=ResearchEvidenceSearchResponse)
    def research_evidence_search_endpoint(
        payload: ResearchContextPackRequest,
        _: None = Depends(require_bearer),
    ) -> ResearchEvidenceSearchResponse:
        trace_id = str(uuid.uuid4())
        start_time = time.perf_counter()
        topic_key = payload.topic_key.strip().lower()
        rows = search_research_evidence(
            app.state.engine,
            topic_key=topic_key,
            query=payload.query,
            evidence_types=payload.evidence_types or None,
            problem_tags=payload.problem_tags or None,
            intervention_tags=payload.intervention_tags or None,
            tradeoff_dimensions=payload.tradeoff_dimensions or None,
            decision_domain=payload.decision_domain,
            corpus_preference=payload.corpus_preference,
            source_trust_min=payload.source_trust_min,
            recency_days=payload.recency_days,
            limit=max(payload.max_items or DEFAULT_RESEARCH_MAX_ITEMS, 1) * 4,
        )
        items = [_map_evidence_item(row) for row in rows]
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        contradictions_present = any(item.contradiction_count > 0 for item in items)
        coverage_summary = {
            "mean_coverage_score": round(sum(item.coverage_score for item in items) / max(len(items), 1), 4),
            "mean_evidence_quality": round(sum(item.evidence_quality for item in items) / max(len(items), 1), 4),
            "internal_coverage_score": round(sum(item.internal_coverage_score for item in items) / max(len(items), 1), 4),
            "external_coverage_score": round(sum(item.external_coverage_score for item in items) / max(len(items), 1), 4),
        }
        create_research_query_log(
            app.state.engine,
            trace_id=trace_id,
            topic_key=topic_key,
            query_text=payload.query,
            source_ids=payload.source_ids,
            token_budget=payload.token_budget,
            max_items=payload.max_items,
            recency_days=payload.recency_days,
            min_relevance_score=payload.min_relevance_score,
            candidate_count=len(rows),
            returned_document_ids=[item.document_id for item in items],
            returned_chunk_ids=[item.chunk_id for item in items],
            timing_ms=elapsed_ms,
            status="ok",
        )
        return ResearchEvidenceSearchResponse(
            query=payload.query,
            topic_key=topic_key,
            items=items,
            contradictions_present=contradictions_present,
            coverage_summary=coverage_summary,
            trace=ResearchContextPackTrace(
                trace_id=trace_id,
                retrieved_document_ids=[item.document_id for item in items],
                timing_ms={"total": elapsed_ms},
                embedding_model_id=str(_embedding_runtime()["model"]),
                embedding_mode=str(_embedding_runtime()["mode"]),
                embedding_warning=_embedding_runtime().get("warning"),
            ),
        )

    @app.post("/v2/research/evidence/related", response_model=ResearchEvidenceRelatedResponse)
    def research_evidence_related_endpoint(
        payload: ResearchContextPackRequest,
        _: None = Depends(require_bearer),
    ) -> ResearchEvidenceRelatedResponse:
        topic_key = payload.topic_key.strip().lower()
        seed_rows = search_research_evidence(
            app.state.engine,
            topic_key=topic_key,
            query=payload.query,
            evidence_types=payload.evidence_types or None,
            problem_tags=payload.problem_tags or None,
            intervention_tags=payload.intervention_tags or None,
            tradeoff_dimensions=payload.tradeoff_dimensions or None,
            decision_domain=payload.decision_domain,
            corpus_preference=payload.corpus_preference,
            source_trust_min=payload.source_trust_min,
            recency_days=payload.recency_days,
            limit=max(payload.max_items or DEFAULT_RESEARCH_MAX_ITEMS, 1),
        )
        seed_items = [_map_evidence_item(row) for row in seed_rows]
        relation_types = None
        if payload.relation_intent == "supporting":
            relation_types = ["supports", "refines"]
        elif payload.relation_intent == "conflicting":
            relation_types = ["contradicts", "supersedes"]
        relation_rows = list_research_evidence_relations(
            app.state.engine,
            insight_ids=[item.insight_id for item in seed_items],
            relation_types=relation_types,
            limit=max((payload.max_items or DEFAULT_RESEARCH_MAX_ITEMS) * 10, 20),
        )
        related_ids = []
        for relation in relation_rows:
            related_ids.append(str(relation.get("from_insight_id")))
            related_ids.append(str(relation.get("to_insight_id")))
        related_ids = [value for value in related_ids if value and value not in {item.insight_id for item in seed_items}]
        related_lookup = {str(row.get("insight_id") or ""): row for row in list_research_document_insights(app.state.engine, topic_key=topic_key, limit=200)}
        related_items = [_map_evidence_item(related_lookup[item_id]) for item_id in related_ids if item_id in related_lookup][: max(payload.max_items or DEFAULT_RESEARCH_MAX_ITEMS, 1) * 4]
        return ResearchEvidenceRelatedResponse(
            topic_key=topic_key,
            relation_intent=payload.relation_intent or "related",
            seed_items=seed_items,
            related_items=related_items,
            relations=[
                ResearchEvidenceRelation(
                    relation_id=str(row.get("relation_id") or ""),
                    relation_type=str(row.get("relation_type") or ""),
                    confidence=float(row.get("confidence") or 0.0),
                    explanation=str(row.get("explanation") or ""),
                    from_insight_id=str(row.get("from_insight_id") or ""),
                    to_insight_id=str(row.get("to_insight_id") or ""),
                )
                for row in relation_rows
            ],
            coverage_summary={
                "seed_count": float(len(seed_items)),
                "related_count": float(len(related_items)),
            },
        )

    @app.post("/v2/research/evidence/compare", response_model=ResearchEvidenceCompareResponse)
    def research_evidence_compare_endpoint(
        payload: ResearchContextPackRequest,
        _: None = Depends(require_bearer),
    ) -> ResearchEvidenceCompareResponse:
        trace_id = str(uuid.uuid4())
        start_time = time.perf_counter()
        topic_key = payload.topic_key.strip().lower()
        rows = search_research_evidence(
            app.state.engine,
            topic_key=topic_key,
            query=payload.query,
            evidence_types=payload.evidence_types or None,
            problem_tags=payload.problem_tags or None,
            intervention_tags=payload.intervention_tags or None,
            tradeoff_dimensions=payload.tradeoff_dimensions or None,
            decision_domain=payload.decision_domain,
            corpus_preference=payload.corpus_preference,
            source_trust_min=payload.source_trust_min,
            recency_days=payload.recency_days,
            limit=max((payload.max_items or DEFAULT_RESEARCH_MAX_ITEMS) * 8, 12),
        )
        grouped: Dict[str, List[ResearchEvidenceItem]] = defaultdict(list)
        for row in rows:
            item = _map_evidence_item(row)
            label = item.problem_tags[0] if item.problem_tags else (item.intervention_tags[0] if item.intervention_tags else item.evidence_type)
            grouped[label].append(item)
        clusters: List[ResearchEvidenceCompareCluster] = []
        contradictions_present = False
        overall_tradeoffs: List[str] = []
        for label, items in list(grouped.items())[: max(payload.max_items or DEFAULT_RESEARCH_MAX_ITEMS, 1)]:
            contradictions_present = contradictions_present or any(item.contradiction_count > 0 for item in items)
            strongest_support = [item.text for item in sorted(items, key=lambda value: value.evidence_quality, reverse=True)[:2]]
            strongest_contradictions = [item.text for item in items if item.contradiction_count > 0][:2]
            tradeoffs = sorted({dimension for item in items for dimension in item.tradeoff_dimensions})[:4]
            overall_tradeoffs.extend(tradeoffs)
            clusters.append(
                ResearchEvidenceCompareCluster(
                    label=label,
                    items=items[:4],
                    strongest_support=strongest_support,
                    strongest_contradictions=strongest_contradictions,
                    tradeoffs=tradeoffs,
                    coverage_score=round(sum(item.coverage_score for item in items) / max(len(items), 1), 4),
                    confidence=_determine_confidence(
                        max((item.evidence_quality for item in items), default=0.0),
                        sum(1 for item in items if item.evidence_quality >= 0.6),
                    ),
                )
            )
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return ResearchEvidenceCompareResponse(
            query=payload.query,
            topic_key=topic_key,
            clusters=clusters,
            overall_tradeoffs=sorted(set(overall_tradeoffs))[:8],
            contradictions_present=contradictions_present,
            coverage_summary={
                "cluster_count": float(len(clusters)),
                "mean_cluster_coverage": round(sum(cluster.coverage_score for cluster in clusters) / max(len(clusters), 1), 4),
            },
            trace=ResearchContextPackTrace(
                trace_id=trace_id,
                retrieved_document_ids=sorted({item.document_id for cluster in clusters for item in cluster.items}),
                timing_ms={"total": elapsed_ms},
                embedding_model_id=str(_embedding_runtime()["model"]),
                embedding_mode=str(_embedding_runtime()["mode"]),
                embedding_warning=_embedding_runtime().get("warning"),
            ),
        )

    @app.post("/v2/research/decision/pack", response_model=ResearchDecisionPackResponse)
    def research_decision_pack_endpoint(
        payload: ResearchContextPackRequest,
        _: None = Depends(require_bearer),
    ) -> ResearchDecisionPackResponse:
        effective_payload = payload.model_copy(
            update={
                "intent_mode": "decision_support",
                "sort_mode": payload.sort_mode or "signal",
                "must_have": payload.must_have or [],
            }
        )
        pack = research_context_pack_endpoint(effective_payload, None)
        items = list(pack.pack.items)
        alternatives: List[ResearchDecisionAlternative] = []
        tradeoffs: List[ResearchTradeoff] = []
        workflow_recommendations: List[ResearchRecommendation] = []
        citations: List[ResearchCitation] = []
        for item in items:
            if item.citations:
                citations.extend(item.citations[:1])
            if item.tradeoffs:
                tradeoffs.extend(item.tradeoffs[:2])
            if item.recommendations:
                workflow_recommendations.extend(item.recommendations[:2])
            alternatives.append(
                ResearchDecisionAlternative(
                    title=item.title,
                    summary=item.summary,
                    citations=item.citations[:2],
                )
            )
        recommended = workflow_recommendations[0].action if workflow_recommendations else (items[0].summary if items else "Gather more evidence before committing to a single approach.")
        risks = [
            ResearchDecisionRisk(
                risk="Evidence is skewed toward the currently indexed corpus.",
                mitigation="Cross-check against additional internal artifacts and recent primary sources.",
            )
        ]
        if payload.decision_domain:
            risks.append(
                ResearchDecisionRisk(
                    risk=f"Domain fit may be incomplete for {payload.decision_domain}.",
                    mitigation="Add more domain-specific sources or internal artifacts to the topic.",
                )
            )
        return ResearchDecisionPackResponse(
            query=payload.query,
            topic_key=payload.topic_key.strip().lower(),
            decision_domain=(payload.decision_domain or "").strip().lower(),
            recommended_approach=recommended,
            alternatives=alternatives[:3],
            tradeoffs=tradeoffs[:5],
            risks=risks,
            workflow_recommendations=workflow_recommendations[:5],
            implementation_notes=[item.summary for item in items[:3]],
            supporting_evidence=items,
            open_questions=[] if items else ["No supporting evidence returned from the current corpus."],
            confidence=pack.retrieval_confidence,
            trace=pack.trace,
        )

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
        embedding_runtime = _embedding_runtime()
        guard_state = _validate_runtime_corpus(app.state.settings, app.state.engine)
        app.state.runtime_guard = guard_state
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
            corpus_guard_enabled=bool(guard_state.get("guard_enabled")),
            corpus_guard_min_documents=int(guard_state.get("min_documents") or 0),
            corpus_guard_current_documents=int(guard_state.get("current_documents") or 0),
            corpus_guard_remaining_documents=int(guard_state.get("remaining_documents") or 0),
            corpus_guard_progress_pct=float(guard_state.get("progress_pct") or 0.0),
            corpus_guard_ready=bool(guard_state.get("ready", True)),
            corpus_guard_status=str(guard_state.get("status") or "ready"),
            corpus_guard_message=str(guard_state.get("message") or "") or None,
            active_embedding_model=str(embedding_runtime["model"]),
            active_embedding_mode=str(embedding_runtime["mode"]),
            embedding_warning=embedding_runtime.get("warning"),
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

    @app.get("/v2/research/ops/documents", response_model=ResearchDocumentStagesResponse)
    def research_ops_documents_endpoint(
        topic_key: str,
        _: None = Depends(require_bearer),
    ) -> ResearchDocumentStagesResponse:
        normalized_topic = topic_key.strip().lower()
        rows = list_research_document_stage_counts(
            app.state.engine,
            topic_key=normalized_topic,
        )
        items = [
            ResearchDocumentStageCount(
                status=str(row.get("status") or "unknown"),
                count=int(row.get("count") or 0),
            )
            for row in rows
        ]
        return ResearchDocumentStagesResponse(topic_key=normalized_topic, items=items)

    @app.get("/v2/research/ops/storage", response_model=ResearchStorageUsageResponse)
    def research_ops_storage_endpoint(
        topic_key: str,
        _: None = Depends(require_bearer),
    ) -> ResearchStorageUsageResponse:
        normalized_topic = topic_key.strip().lower()
        usage = get_research_storage_usage(
            app.state.engine,
            topic_key=normalized_topic,
        )
        raw_payload_bytes = int(usage.get("raw_payload_bytes") or 0)
        extracted_text_bytes = int(usage.get("extracted_text_bytes") or 0)
        chunks_bytes = int(usage.get("chunks_bytes") or 0)
        embeddings_bytes = int(usage.get("embeddings_bytes") or 0)
        return ResearchStorageUsageResponse(
            topic_key=normalized_topic,
            documents_count=int(usage.get("documents_count") or 0),
            chunks_count=int(usage.get("chunks_count") or 0),
            embeddings_count=int(usage.get("embeddings_count") or 0),
            raw_payload_bytes=raw_payload_bytes,
            extracted_text_bytes=extracted_text_bytes,
            chunks_bytes=chunks_bytes,
            embeddings_bytes=embeddings_bytes,
            total_bytes=raw_payload_bytes + extracted_text_bytes + chunks_bytes + embeddings_bytes,
        )

    @app.get("/v2/research/ops/progress", response_model=ResearchOpsProgressResponse)
    def research_ops_progress_endpoint(
        topic_key: str,
        run_limit: int = 10,
        _: None = Depends(require_bearer),
    ) -> ResearchOpsProgressResponse:
        normalized_topic = topic_key.strip().lower()
        embedding_runtime = _embedding_runtime()
        guard_state = _validate_runtime_corpus(app.state.settings, app.state.engine)
        app.state.runtime_guard = guard_state
        run_rows = list_research_run_progress(
            app.state.engine,
            topic_key=normalized_topic,
            limit=max(min(run_limit, 50), 1),
        )
        runs: List[ResearchRunProgressRecord] = []
        queued_runs = 0
        running_runs = 0
        for row in run_rows:
            status_value = str(row.get("status") or "queued")
            if status_value == "queued":
                queued_runs += 1
            elif status_value == "running":
                running_runs += 1
            runs.append(
                ResearchRunProgressRecord(
                    run_id=str(row.get("run_id") or ""),
                    trigger=str(row.get("trigger") or ""),
                    status=status_value,
                    created_at=row.get("created_at"),
                    started_at=row.get("started_at"),
                    finished_at=row.get("finished_at"),
                    elapsed_seconds=_elapsed_seconds(row.get("started_at"), row.get("finished_at")),
                    sources_selected=int(row.get("sources_selected") or 0),
                    items_seen=int(row.get("items_seen") or 0),
                    items_new=int(row.get("items_new") or 0),
                    items_deduped=int(row.get("items_deduped") or 0),
                    items_failed=int(row.get("items_failed") or 0),
                )
            )

        pipeline = get_research_pipeline_counts(app.state.engine, topic_key=normalized_topic)
        chunks_count = int(pipeline.get("chunks_count") or 0)
        embeddings_count = int(pipeline.get("embeddings_count") or 0)
        embedding_coverage_pct = 0.0
        if chunks_count > 0:
            embedding_coverage_pct = min(100.0, (float(embeddings_count) / float(chunks_count)) * 100.0)

        ai_rows = get_research_ai_usage_by_model(app.state.engine, topic_key=normalized_topic)
        ai_models: List[ResearchAiUsageModelRecord] = []
        ai_external_calls_estimate = 0
        ai_estimated_tokens_total = 0
        ai_estimated_tokens_24h = 0
        for row in ai_rows:
            model_id = str(row.get("embedding_model_id") or "")
            docs_count = int(row.get("documents_count") or 0)
            chunks_for_model = int(row.get("chunks_count") or 0)
            tokens_total = int(row.get("estimated_tokens_total") or 0)
            tokens_24h = int(row.get("estimated_tokens_24h") or 0)
            external_api = bool(model_id and not model_id.lower().startswith("hash"))
            if external_api:
                ai_external_calls_estimate += docs_count
                ai_estimated_tokens_total += tokens_total
                ai_estimated_tokens_24h += tokens_24h
            ai_models.append(
                ResearchAiUsageModelRecord(
                    embedding_model_id=model_id,
                    documents_count=docs_count,
                    chunks_count=chunks_for_model,
                    estimated_tokens_total=tokens_total,
                    estimated_tokens_24h=tokens_24h,
                    external_api=external_api,
                )
            )

        db_size_bytes = get_context_db_size_bytes(app.state.engine)
        disk_total_bytes = 0
        disk_free_bytes = 0
        try:
            fs = os.statvfs("/")
            disk_total_bytes = int(fs.f_frsize * fs.f_blocks)
            disk_free_bytes = int(fs.f_frsize * fs.f_bavail)
        except Exception:
            disk_total_bytes = 0
            disk_free_bytes = 0
        disk_used_bytes = max(disk_total_bytes - disk_free_bytes, 0)
        disk_used_pct = (float(disk_used_bytes) / float(disk_total_bytes) * 100.0) if disk_total_bytes > 0 else 0.0
        cpu_count = int(os.cpu_count() or 0)
        cpu_load_1m = 0.0
        cpu_load_5m = 0.0
        cpu_load_15m = 0.0
        try:
            load_1m, load_5m, load_15m = os.getloadavg()
            cpu_load_1m = float(load_1m)
            cpu_load_5m = float(load_5m)
            cpu_load_15m = float(load_15m)
        except Exception:
            cpu_load_1m = 0.0
            cpu_load_5m = 0.0
            cpu_load_15m = 0.0
        mem = _read_meminfo_bytes()

        return ResearchOpsProgressResponse(
            topic_key=normalized_topic,
            queued_runs=queued_runs,
            running_runs=running_runs,
            stages={
                "discovered": int(pipeline.get("discovered_count") or 0),
                "fetched": int(pipeline.get("fetched_count") or 0),
                "extracted": int(pipeline.get("extracted_count") or 0),
                "embedded": int(pipeline.get("embedded_count") or 0),
                "failed": int(pipeline.get("failed_count") or 0),
            },
            chunks_count=chunks_count,
            embeddings_count=embeddings_count,
            embedding_coverage_pct=embedding_coverage_pct,
            db_size_bytes=db_size_bytes,
            disk_total_bytes=disk_total_bytes,
            disk_used_bytes=disk_used_bytes,
            disk_free_bytes=disk_free_bytes,
            disk_used_pct=disk_used_pct,
            cpu_count=cpu_count,
            cpu_load_1m=cpu_load_1m,
            cpu_load_5m=cpu_load_5m,
            cpu_load_15m=cpu_load_15m,
            memory_total_bytes=int(mem.get("memory_total_bytes") or 0),
            memory_available_bytes=int(mem.get("memory_available_bytes") or 0),
            memory_used_bytes=int(mem.get("memory_used_bytes") or 0),
            memory_used_pct=float(mem.get("memory_used_pct") or 0.0),
            ai_external_calls_estimate=ai_external_calls_estimate,
            ai_estimated_tokens_total=ai_estimated_tokens_total,
            ai_estimated_tokens_24h=ai_estimated_tokens_24h,
            corpus_guard_enabled=bool(guard_state.get("guard_enabled")),
            corpus_guard_min_documents=int(guard_state.get("min_documents") or 0),
            corpus_guard_current_documents=int(guard_state.get("current_documents") or 0),
            corpus_guard_remaining_documents=int(guard_state.get("remaining_documents") or 0),
            corpus_guard_progress_pct=float(guard_state.get("progress_pct") or 0.0),
            corpus_guard_ready=bool(guard_state.get("ready", True)),
            corpus_guard_status=str(guard_state.get("status") or "ready"),
            corpus_guard_message=str(guard_state.get("message") or "") or None,
            active_embedding_model=str(embedding_runtime["model"]),
            active_embedding_mode=str(embedding_runtime["mode"]),
            embedding_warning=embedding_runtime.get("warning"),
            ai_models=ai_models,
            runs=runs,
        )

    @app.get("/v2/research/topics", response_model=ResearchTopicListResponse)
    def research_topics_endpoint(
        limit: int = 20,
        _: None = Depends(require_bearer),
    ) -> ResearchTopicListResponse:
        rows = list_research_topics(app.state.engine, limit=max(min(limit, 50), 1))
        return ResearchTopicListResponse(
            items=[
                ResearchTopicSummary(
                    topic_key=str(row.get("topic_key") or ""),
                    label=str(row.get("label") or _topic_label(str(row.get("topic_key") or ""))),
                    description=str(row.get("description") or ""),
                    source_count=int(row.get("source_count") or 0),
                    document_count=int(row.get("document_count") or 0),
                    embedded_document_count=int(row.get("embedded_document_count") or 0),
                    last_published_at=row.get("last_published_at"),
                    last_ingested_at=row.get("last_ingested_at"),
                )
                for row in rows
            ]
        )

    @app.get("/v2/research/topics/search", response_model=ResearchTopicSearchResponse)
    def research_topics_search_endpoint(
        query: str,
        limit: int = 10,
        _: None = Depends(require_bearer),
    ) -> ResearchTopicSearchResponse:
        rows = list_research_topics(app.state.engine, query=query, limit=max(min(limit, 25), 1))
        return ResearchTopicSearchResponse(
            query=query,
            items=[
                ResearchTopicSummary(
                    topic_key=str(row.get("topic_key") or ""),
                    label=str(row.get("label") or _topic_label(str(row.get("topic_key") or ""))),
                    description=str(row.get("description") or ""),
                    source_count=int(row.get("source_count") or 0),
                    document_count=int(row.get("document_count") or 0),
                    embedded_document_count=int(row.get("embedded_document_count") or 0),
                    last_published_at=row.get("last_published_at"),
                    last_ingested_at=row.get("last_ingested_at"),
                )
                for row in rows
            ],
        )

    @app.get("/v2/research/topics/{topic_key}", response_model=ResearchTopicDetailResponse)
    def research_topic_detail_endpoint(
        topic_key: str,
        _: None = Depends(require_bearer),
    ) -> ResearchTopicDetailResponse:
        normalized_topic = topic_key.strip().lower()
        detail = get_research_topic_detail(app.state.engine, topic_key=normalized_topic)
        if not detail:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
        top_sources = list_research_source_metrics_for_topic(app.state.engine, topic_key=normalized_topic, limit=5)
        top_themes = collect_research_topic_themes(app.state.engine, topic_key=normalized_topic, limit=6)
        suggested_queries = [
            f"best practices for {normalized_topic.replace('_', ' ')}",
            f"recent changes in {normalized_topic.replace('_', ' ')}",
            f"architecture guidance for {normalized_topic.replace('_', ' ')}",
        ]
        return ResearchTopicDetailResponse(
            topic_key=normalized_topic,
            label=str(detail.get("label") or _topic_label(normalized_topic)),
            description=str(detail.get("description") or ""),
            source_count=int(detail.get("source_count") or 0),
            document_count=int(detail.get("document_count") or 0),
            embedded_document_count=int(detail.get("embedded_document_count") or 0),
            last_published_at=detail.get("last_published_at"),
            last_ingested_at=detail.get("last_ingested_at"),
            top_sources=[
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
                for row in top_sources
            ],
            top_themes=[
                ResearchTopicTheme(name=str(row.get("name") or ""), score=float(row.get("score") or 0.0))
                for row in top_themes
            ],
            suggested_queries=suggested_queries,
        )

    @app.get("/v2/research/topics/{topic_key}/documents", response_model=ResearchTopicDocumentsResponse)
    def research_topic_documents_endpoint(
        topic_key: str,
        limit: int = 10,
        sort: str = "recent",
        _: None = Depends(require_bearer),
    ) -> ResearchTopicDocumentsResponse:
        normalized_topic = topic_key.strip().lower()
        rows = list_research_documents_for_topic(
            app.state.engine,
            topic_key=normalized_topic,
            limit=max(min(limit, 25), 1),
            sort=sort,
        )
        return ResearchTopicDocumentsResponse(
            topic_key=normalized_topic,
            items=[
                ResearchTopicDocument(
                    document_id=str(row.get("document_id") or ""),
                    source_id=str(row.get("source_id") or ""),
                    title=str(row.get("title") or ""),
                    canonical_url=str(row.get("canonical_url") or ""),
                    published_at=row.get("published_at"),
                    summary=_trim_text(str(row.get("summary") or ""), 320),
                    content_type=str(row.get("content_type") or "company_blog"),
                    publisher_type=str(row.get("publisher_type") or "independent"),
                    source_class=str(row.get("source_class") or "external_commentary"),
                    topic_tags=[str(value) for value in (row.get("topic_tags") or [])],
                    decision_domains=[str(value) for value in (row.get("decision_domains") or [])],
                    metrics=_map_metric_items(row.get("metrics")),
                    notable_quotes=_map_quote_items(row.get("notable_quotes")),
                    citations=[],
                )
                for row in rows
            ],
        )

    @app.post("/v2/research/topics/{topic_key}/summarize", response_model=ResearchTopicSummarizeResponse)
    def research_topic_summarize_endpoint(
        topic_key: str,
        payload: ResearchTopicSummarizeRequest,
        _: None = Depends(require_bearer),
    ) -> ResearchTopicSummarizeResponse:
        normalized_topic = topic_key.strip().lower()
        focus_query = payload.focus.strip() if payload.focus else normalized_topic.replace("_", " ")
        detail = get_research_topic_detail(app.state.engine, topic_key=normalized_topic)
        if not detail:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
        topic_search = search_research_chunks(
            app.state.engine,
            topic_key=normalized_topic,
            query=focus_query,
            recency_days=payload.recency_days,
            limit=max(payload.max_items * 4, payload.max_items),
        )
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in topic_search:
            document_id = str(row.get("document_id") or "")
            if document_id:
                grouped[document_id].append(row)
        items: List[ResearchTopicDocument] = []
        citations: List[ResearchCitation] = []
        for document_id, doc_rows in list(grouped.items())[: payload.max_items]:
            best = doc_rows[0]
            row_citations: List[ResearchCitation] = []
            snippets: List[str] = []
            for row in doc_rows[:2]:
                chunk_id = str(row.get("chunk_id") or "")
                if not chunk_id:
                    continue
                citation = ResearchCitation(document_id=document_id, chunk_id=chunk_id)
                row_citations.append(citation)
                citations.append(citation)
                snippets.append(_clean_snippet(str(row.get("snippet") or row.get("content") or "")))
            items.append(
                ResearchTopicDocument(
                    document_id=document_id,
                    source_id=str(best.get("source_id") or ""),
                    title=str(best.get("title") or ""),
                    canonical_url=str(best.get("canonical_url") or ""),
                    published_at=best.get("published_at"),
                    summary=_trim_text(str(best.get("summary_short") or " ".join(snippets)), 320),
                    content_type=str(best.get("content_type") or "company_blog"),
                    publisher_type=str(best.get("publisher_type") or "independent"),
                    source_class=str(best.get("source_class") or "external_commentary"),
                    topic_tags=[str(value) for value in (best.get("topic_tags") or [])],
                    decision_domains=[str(value) for value in (best.get("decision_domains") or [])],
                    metrics=_map_metric_items(best.get("metrics")),
                    notable_quotes=_map_quote_items(best.get("notable_quotes")),
                    citations=row_citations,
                )
            )
        themes = collect_research_topic_themes(app.state.engine, topic_key=normalized_topic, limit=6)
        suggested_queries = [
            f"{focus_query} implementation patterns",
            f"{focus_query} architecture tradeoffs",
            f"{focus_query} recent recommendations",
        ]
        return ResearchTopicSummarizeResponse(
            topic_key=normalized_topic,
            focus=payload.focus,
            synthesis=_summarize_topic_documents(normalized_topic, [item.model_dump(mode="python") for item in items], themes, payload.focus),
            themes=[
                ResearchTopicTheme(name=str(row.get("name") or ""), score=float(row.get("score") or 0.0))
                for row in themes
            ],
            suggested_queries=suggested_queries,
            items=items,
            citations=citations[: payload.max_items * 2],
        )

    @app.get("/v2/research/topics/{topic_key}/weekly", response_model=ResearchWeeklyDigestResponse)
    def research_topic_weekly_endpoint(
        topic_key: str,
        days: int = 7,
        limit: int = 5,
        _: None = Depends(require_bearer),
    ) -> ResearchWeeklyDigestResponse:
        normalized_topic = topic_key.strip().lower()
        rows = list_recent_research_documents(app.state.engine, topic_key=normalized_topic, days=max(days, 1), limit=max(limit * 6, 12))
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            tags = [str(value).strip().lower() for value in (row.get("topic_tags") or []) if str(value).strip()]
            cluster_key = ",".join(tags[:2]) or str(row.get("content_type") or "general")
            grouped[cluster_key].append(row)
        items: List[ResearchWeeklyDigestItem] = []
        for cluster_key, cluster_rows in list(grouped.items())[: max(limit, 1)]:
            representative = cluster_rows[0]
            metrics = _map_metric_items(representative.get("metrics"))
            quotes = _map_quote_items(representative.get("notable_quotes"))
            citations = []
            if metrics:
                citations.append(ResearchCitation(document_id=str(representative.get("document_id") or ""), chunk_id=metrics[0].chunk_id))
            elif quotes:
                citations.append(ResearchCitation(document_id=str(representative.get("document_id") or ""), chunk_id=quotes[0].chunk_id))
            items.append(
                ResearchWeeklyDigestItem(
                    cluster_key=cluster_key,
                    cluster_title=", ".join([part for part in cluster_key.split(",") if part]) or str(representative.get("title") or "Recent development"),
                    cluster_summary=str(representative.get("summary_short") or representative.get("summary") or ""),
                    why_it_matters=str(representative.get("why_it_matters") or ""),
                    top_metric=metrics[0] if metrics else None,
                    top_quote=quotes[0] if quotes else None,
                    citations=citations,
                    document_ids=[str(row.get("document_id") or "") for row in cluster_rows[:4]],
                )
            )
        return ResearchWeeklyDigestResponse(topic_key=normalized_topic, days=max(days, 1), items=items)

    @app.get("/v2/research/topics/{topic_key}/domains/{decision_domain}/summary", response_model=ResearchDomainSummaryResponse)
    def research_topic_domain_summary_endpoint(
        topic_key: str,
        decision_domain: str,
        _: None = Depends(require_bearer),
    ) -> ResearchDomainSummaryResponse:
        normalized_topic = topic_key.strip().lower()
        normalized_domain = decision_domain.strip().lower()
        insights = list_research_document_insights(
            app.state.engine,
            topic_key=normalized_topic,
            decision_domain=normalized_domain,
            limit=40,
        )
        recommendations = _map_recommendation_items([row.get("normalized_payload") for row in insights if row.get("insight_type") == "recommendation"])
        tradeoffs = _map_tradeoff_items([row.get("normalized_payload") for row in insights if row.get("insight_type") == "tradeoff"])
        workflow_patterns = [str((row.get("normalized_payload") or {}).get("pattern") or row.get("text") or "") for row in insights if row.get("insight_type") == "workflow_pattern"]
        citations = [
            ResearchCitation(document_id=str(row.get("document_id") or ""), chunk_id=str(row.get("chunk_id") or ""))
            for row in insights[:8]
            if str(row.get("document_id") or "").strip() and str(row.get("chunk_id") or "").strip()
        ]
        if recommendations:
            summary = recommendations[0].action
        elif workflow_patterns:
            summary = workflow_patterns[0]
        else:
            summary = f"No high-confidence domain summary available yet for {normalized_domain}."
        return ResearchDomainSummaryResponse(
            topic_key=normalized_topic,
            decision_domain=normalized_domain,
            summary=summary,
            recommendations=recommendations[:5],
            tradeoffs=tradeoffs[:5],
            workflow_patterns=workflow_patterns[:5],
            citations=citations,
        )

    @app.get("/v2/research/ops/dashboard", response_class=HTMLResponse)
    def research_ops_dashboard_endpoint() -> HTMLResponse:
        runtime_info = dict(app.state.runtime_banner)
        runtime_info["guard"] = dict(app.state.runtime_guard or {})
        return HTMLResponse(
            content=_render_ops_dashboard_html(
                default_token=app.state.settings.context_api_token.strip(),
                default_topic=app.state.settings.context_api_research_topic_key.strip() or "ai_research",
                runtime_info=runtime_info,
            )
        )

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
