from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ResearchSourceUpsertRequest(BaseModel):
    topic_key: str
    kind: Literal["rss", "atom", "site_map", "html_listing", "api"]
    name: str
    base_url: str
    poll_interval_minutes: int = Field(default=60, ge=1, le=1440)
    rate_limit_per_hour: int = Field(default=30, ge=1, le=3600)
    source_weight: float = Field(default=1.0, ge=0.0, le=5.0)
    robots_mode: Literal["strict", "ignore"] = "strict"
    enabled: bool = True
    tags: List[str] = Field(default_factory=list)


class ResearchSourceUpsertResponse(BaseModel):
    source_id: str
    status: Literal["created", "updated"]


class ResearchSourceRecord(BaseModel):
    source_id: str
    topic_key: str
    kind: str
    name: str
    base_url_original: str
    base_url_canonical: str
    enabled: bool
    tags: List[str] = Field(default_factory=list)
    poll_interval_minutes: int
    rate_limit_per_hour: int
    source_weight: float = 1.0
    consecutive_failures: int = 0
    cooldown_until: Optional[datetime] = None
    last_error: Optional[str] = None
    robots_mode: Literal["strict", "ignore"]
    max_items_per_run: int


class ResearchSourceListResponse(BaseModel):
    items: List[ResearchSourceRecord]


class ResearchIngestRunRequest(BaseModel):
    topic_key: str
    source_ids: List[str] = Field(default_factory=list)
    trigger: Literal["manual", "schedule", "event"]
    idempotency_key: Optional[str] = None
    max_items_per_source: Optional[int] = Field(default=None, ge=1, le=1000)


class ResearchIngestRunResponse(BaseModel):
    run_id: str
    status: Literal["queued", "running", "completed", "failed"]
    sources_selected: int


class ResearchRunCounters(BaseModel):
    items_seen: int = 0
    items_new: int = 0
    items_deduped: int = 0
    items_failed: int = 0


class ResearchIngestRunStatusResponse(BaseModel):
    run_id: str
    status: Literal["queued", "running", "completed", "failed"]
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    counters: ResearchRunCounters = Field(default_factory=ResearchRunCounters)
    errors: List[str] = Field(default_factory=list)


class ResearchDocumentRecord(BaseModel):
    document_id: str
    source_id: str
    canonical_url: str
    url_original: Optional[str] = None
    title: Optional[str] = None
    published_at: Optional[datetime] = None
    status: Literal["discovered", "fetched", "extracted", "embedded", "enriched", "failed"] = "discovered"
    fetch_meta: Dict[str, Any] = Field(default_factory=dict)
    extraction_meta: Dict[str, Any] = Field(default_factory=dict)
    enrichment_meta: Dict[str, Any] = Field(default_factory=dict)


class ResearchContextPackRequest(BaseModel):
    query: str
    topic_key: str
    source_ids: List[str] = Field(default_factory=list)
    token_budget: Optional[int] = None
    recency_days: Optional[int] = Field(default=None, ge=0)
    max_items: Optional[int] = Field(default=None, ge=1, le=20)
    min_relevance_score: Optional[float] = None


class ResearchCitation(BaseModel):
    document_id: str
    chunk_id: str


class ResearchScoreBreakdown(BaseModel):
    total: float
    lexical: float
    embedding: float = 0.0
    recency: float = 0.0
    source_weight: float = 0.0


class ResearchSignal(BaseModel):
    claim: str
    why: str
    cite: ResearchCitation


class ResearchContextPackItem(BaseModel):
    document_id: str
    source_id: str
    title: str
    canonical_url: str
    published_at: Optional[datetime] = None
    summary: str
    signals: List[ResearchSignal] = Field(default_factory=list)
    citations: List[ResearchCitation] = Field(default_factory=list)
    score_breakdown: ResearchScoreBreakdown


class ResearchContextPack(BaseModel):
    items: List[ResearchContextPackItem] = Field(default_factory=list)


class ResearchContextPackTrace(BaseModel):
    trace_id: str
    retrieved_document_ids: List[str] = Field(default_factory=list)
    timing_ms: Dict[str, int] = Field(default_factory=dict)


class ResearchContextPackResponse(BaseModel):
    pack: ResearchContextPack
    retrieval_confidence: Literal["high", "med", "low"]
    next_action: Literal["proceed", "refine_query", "expand_sections"]
    trace: ResearchContextPackTrace


class ResearchChunkSearchRequest(BaseModel):
    query: str
    max_chars: Optional[int] = None
    max_chunks: Optional[int] = None


class ResearchChunkRecord(BaseModel):
    chunk_id: str
    snippet: str
    score: Optional[float] = None


class ResearchChunkSearchResponse(BaseModel):
    document_id: str
    chunks: List[ResearchChunkRecord] = Field(default_factory=list)


class ResearchFeedbackRequest(BaseModel):
    trace_id: str
    query_log_id: Optional[str] = None
    document_id: str
    chunk_id: str
    verdict: Literal["useful", "not_useful"]
    notes: Optional[str] = None


class ResearchFeedbackResponse(BaseModel):
    feedback_id: str
    status: Literal["recorded"]


class ResearchOpsSummaryResponse(BaseModel):
    topic_key: str
    sources_total: int = 0
    sources_enabled: int = 0
    sources_in_cooldown: int = 0
    documents_total: int = 0
    documents_embedded: int = 0
    documents_failed: int = 0
    runs_open: int = 0
    runs_failed_24h: int = 0
    run_failure_rate_24h: float = 0.0
    retrieval_queries_24h: int = 0
    retrieval_errors_24h: int = 0


class ResearchSourceMetricRecord(BaseModel):
    source_id: str
    name: str
    enabled: bool
    last_polled_at: Optional[datetime] = None
    consecutive_failures: int = 0
    cooldown_until: Optional[datetime] = None
    last_error: Optional[str] = None
    documents_total: int = 0
    documents_embedded: int = 0
    documents_failed: int = 0
    retrieval_queries_24h: int = 0


class ResearchSourceMetricsResponse(BaseModel):
    topic_key: str
    items: List[ResearchSourceMetricRecord] = Field(default_factory=list)


class ResearchDocumentStageCount(BaseModel):
    status: str
    count: int


class ResearchDocumentStagesResponse(BaseModel):
    topic_key: str
    items: List[ResearchDocumentStageCount] = Field(default_factory=list)


class ResearchSourceModerationResponse(BaseModel):
    source_id: str
    enabled: bool
    status: Literal["updated"]


class ResearchRedactRequest(BaseModel):
    topic_key: str
    older_than_days: int = Field(default=30, ge=0, le=3650)


class ResearchRedactResponse(BaseModel):
    topic_key: str
    older_than_days: int
    redacted_documents: int


class ResearchReviewQueueItem(BaseModel):
    query_log_id: str
    trace_id: str
    query_text: str
    candidate_count: int = 0
    returned_document_ids: List[str] = Field(default_factory=list)
    returned_chunk_ids: List[str] = Field(default_factory=list)
    status: str
    error: Optional[str] = None
    useful_count: int = 0
    not_useful_count: int = 0
    created_at: Optional[datetime] = None


class ResearchReviewQueueResponse(BaseModel):
    topic_key: str
    items: List[ResearchReviewQueueItem] = Field(default_factory=list)


class SourceSuggestion(BaseModel):
    kind: Literal["rss", "atom", "site_map", "html_listing", "api"]
    name: str
    base_url: str
    tags: List[str] = Field(default_factory=list)
    poll_interval_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    rate_limit_per_hour: Optional[int] = Field(default=None, ge=1, le=3600)
    source_weight: Optional[float] = Field(default=None, ge=0.0, le=5.0)
    robots_mode: Optional[Literal["strict", "ignore"]] = None


class ResearchBootstrapRequest(BaseModel):
    topic_key: str
    suggestions: List[SourceSuggestion] = Field(min_length=1, max_length=1000)
    trigger_ingest: bool = True
    trigger: Literal["manual", "event"] = "event"
    idempotency_key: Optional[str] = None
    dry_run: bool = False


class ResearchBootstrapSummary(BaseModel):
    received: int = 0
    valid: int = 0
    invalid: int = 0
    created: int = 0
    updated: int = 0
    skipped_duplicate: int = 0


class ResearchBootstrapResult(BaseModel):
    index: int
    status: Literal["created", "updated", "invalid", "skipped_duplicate"]
    reason: Optional[str] = None
    source_id: Optional[str] = None


class ResearchBootstrapIngest(BaseModel):
    triggered: bool
    run_id: Optional[str] = None
    status: Optional[Literal["queued", "running", "completed", "failed"]] = None


class ResearchBootstrapResponse(BaseModel):
    topic_key: str
    summary: ResearchBootstrapSummary
    results: List[ResearchBootstrapResult] = Field(default_factory=list)
    ingest: ResearchBootstrapIngest


class ResearchBootstrapStatusEvent(BaseModel):
    event_id: str
    request_hash: str
    idempotency_key: Optional[str] = None
    summary: ResearchBootstrapSummary
    run_id: Optional[str] = None
    run_status: Optional[Literal["queued", "running", "completed", "failed"]] = None
    created_at: Optional[datetime] = None


class ResearchBootstrapStatusResponse(BaseModel):
    topic_key: str
    latest_bootstrap: Optional[ResearchBootstrapStatusEvent] = None
