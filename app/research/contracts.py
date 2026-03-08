from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


InsightType = Literal[
    "metric",
    "quote",
    "claim",
    "tradeoff",
    "recommendation",
    "workflow_pattern",
    "implementation_note",
    "failure_mode",
    "assumption",
    "constraint",
    "open_question",
    "benchmark_result",
    "observation",
    "decision_pattern",
]
IntentMode = Literal["general", "decision_support", "editorial"]
SortMode = Literal["relevance", "recent", "signal", "novelty"]
MustHaveValue = Literal["metrics", "quotes", "recommendations", "tradeoffs", "recent", "internal"]
CorpusPreference = Literal["internal", "external", "mixed"]
RelationIntent = Literal["supporting", "conflicting", "related"]
CoverageBias = Literal["precision", "breadth", "balanced"]


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
    publisher_type: str = "independent"
    source_class: str = "external_commentary"
    default_decision_domains: List[str] = Field(default_factory=list)


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
    publisher_type: str = "independent"
    source_class: str = "external_commentary"
    default_decision_domains: List[str] = Field(default_factory=list)
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
    published_at_confidence: float = 0.0
    status: Literal["discovered", "fetched", "extracted", "embedded", "enriched", "failed"] = "discovered"
    content_type: str = "company_blog"
    publisher_type: str = "independent"
    source_class: str = "external_commentary"
    summary_short: str = ""
    why_it_matters: str = ""
    topic_tags: List[str] = Field(default_factory=list)
    entity_tags: List[str] = Field(default_factory=list)
    use_case_tags: List[str] = Field(default_factory=list)
    decision_domains: List[str] = Field(default_factory=list)
    quality_signals: Dict[str, Any] = Field(default_factory=dict)
    metrics: List[Dict[str, Any]] = Field(default_factory=list)
    notable_quotes: List[Dict[str, Any]] = Field(default_factory=list)
    key_claims: List[Dict[str, Any]] = Field(default_factory=list)
    tradeoffs: List[Dict[str, Any]] = Field(default_factory=list)
    recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    novelty_score: float = 0.0
    evidence_density_score: float = 0.0
    document_signal_score: float = 0.0
    embedding_ready: bool = False
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
    intent_mode: IntentMode = "general"
    decision_domain: Optional[str] = None
    content_types: List[str] = Field(default_factory=list)
    source_classes: List[str] = Field(default_factory=list)
    publisher_types: List[str] = Field(default_factory=list)
    must_have: List[MustHaveValue] = Field(default_factory=list)
    exclude_content_types: List[str] = Field(default_factory=list)
    sort_mode: SortMode = "relevance"
    evidence_types: List[InsightType] = Field(default_factory=list)
    problem_tags: List[str] = Field(default_factory=list)
    intervention_tags: List[str] = Field(default_factory=list)
    tradeoff_dimensions: List[str] = Field(default_factory=list)
    corpus_preference: CorpusPreference = "mixed"
    relation_intent: Optional[RelationIntent] = None
    source_trust_min: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    coverage_bias: CoverageBias = "balanced"


class ResearchCitation(BaseModel):
    document_id: str
    chunk_id: str


class ResearchMetric(BaseModel):
    name: str
    value: str
    unit: str = ""
    qualifier: str = ""
    snippet: str = ""
    chunk_id: str


class ResearchQuote(BaseModel):
    speaker: str = ""
    text: str
    snippet: str = ""
    chunk_id: str


class ResearchTradeoff(BaseModel):
    benefit: str
    cost: str
    condition: str = ""
    chunk_id: str


class ResearchRecommendation(BaseModel):
    action: str
    rationale: str
    applicability: str = ""
    chunk_id: str


class ResearchScoreBreakdown(BaseModel):
    total: float
    lexical: float
    embedding: float = 0.0
    recency: float = 0.0
    source_weight: float = 0.0
    signal: float = 0.0
    trust: float = 0.0
    intent_fit: float = 0.0


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
    content_type: str = "company_blog"
    publisher_type: str = "independent"
    source_class: str = "external_commentary"
    topic_tags: List[str] = Field(default_factory=list)
    decision_domains: List[str] = Field(default_factory=list)
    metrics: List[ResearchMetric] = Field(default_factory=list)
    notable_quotes: List[ResearchQuote] = Field(default_factory=list)
    tradeoffs: List[ResearchTradeoff] = Field(default_factory=list)
    recommendations: List[ResearchRecommendation] = Field(default_factory=list)
    document_signal_score: float = 0.0
    evidence_quality: float = 0.0
    corroboration_count: int = 0
    contradiction_count: int = 0
    freshness_score: float = 0.0
    coverage_score: float = 0.0
    problem_tags: List[str] = Field(default_factory=list)
    intervention_tags: List[str] = Field(default_factory=list)
    tradeoff_dimensions: List[str] = Field(default_factory=list)
    signals: List[ResearchSignal] = Field(default_factory=list)
    citations: List[ResearchCitation] = Field(default_factory=list)
    score_breakdown: ResearchScoreBreakdown


class ResearchContextPack(BaseModel):
    items: List[ResearchContextPackItem] = Field(default_factory=list)


class ResearchContextPackTrace(BaseModel):
    trace_id: str
    retrieved_document_ids: List[str] = Field(default_factory=list)
    timing_ms: Dict[str, int] = Field(default_factory=dict)
    embedding_model_id: str = ""
    embedding_mode: str = ""
    embedding_warning: Optional[str] = None


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
    heading_path: List[str] = Field(default_factory=list)


class ResearchChunkSearchResponse(BaseModel):
    document_id: str
    chunks: List[ResearchChunkRecord] = Field(default_factory=list)


class ResearchEvidenceItem(BaseModel):
    insight_id: str
    document_id: str
    chunk_id: str
    evidence_type: InsightType
    text: str
    normalized_payload: Dict[str, Any] = Field(default_factory=dict)
    title: str = ""
    canonical_url: str = ""
    published_at: Optional[datetime] = None
    source_id: str = ""
    source_class: str = "external_commentary"
    publisher_type: str = "independent"
    topic_tags: List[str] = Field(default_factory=list)
    entity_tags: List[str] = Field(default_factory=list)
    decision_domains: List[str] = Field(default_factory=list)
    problem_tags: List[str] = Field(default_factory=list)
    intervention_tags: List[str] = Field(default_factory=list)
    tradeoff_dimensions: List[str] = Field(default_factory=list)
    applicability_conditions: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    evidence_strength: float = 0.0
    source_trust_tier: float = 0.0
    freshness_score: float = 0.0
    corroboration_count: int = 0
    contradiction_count: int = 0
    coverage_score: float = 0.0
    internal_coverage_score: float = 0.0
    external_coverage_score: float = 0.0
    evidence_quality: float = 0.0
    staleness_flag: bool = False
    superseded_flag: bool = False
    citation: ResearchCitation


class ResearchEvidenceSearchResponse(BaseModel):
    query: str
    topic_key: str
    items: List[ResearchEvidenceItem] = Field(default_factory=list)
    contradictions_present: bool = False
    coverage_summary: Dict[str, float] = Field(default_factory=dict)
    trace: ResearchContextPackTrace


class ResearchEvidenceRelation(BaseModel):
    relation_id: str
    relation_type: str
    confidence: float = 0.0
    explanation: str = ""
    from_insight_id: str
    to_insight_id: str


class ResearchEvidenceRelatedResponse(BaseModel):
    topic_key: str
    relation_intent: RelationIntent = "related"
    seed_items: List[ResearchEvidenceItem] = Field(default_factory=list)
    related_items: List[ResearchEvidenceItem] = Field(default_factory=list)
    relations: List[ResearchEvidenceRelation] = Field(default_factory=list)
    coverage_summary: Dict[str, float] = Field(default_factory=dict)


class ResearchEvidenceCompareCluster(BaseModel):
    label: str
    items: List[ResearchEvidenceItem] = Field(default_factory=list)
    strongest_support: List[str] = Field(default_factory=list)
    strongest_contradictions: List[str] = Field(default_factory=list)
    tradeoffs: List[str] = Field(default_factory=list)
    coverage_score: float = 0.0
    confidence: Literal["high", "med", "low"] = "low"


class ResearchEvidenceCompareResponse(BaseModel):
    query: str
    topic_key: str
    clusters: List[ResearchEvidenceCompareCluster] = Field(default_factory=list)
    overall_tradeoffs: List[str] = Field(default_factory=list)
    contradictions_present: bool = False
    coverage_summary: Dict[str, float] = Field(default_factory=dict)
    trace: ResearchContextPackTrace


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
    corpus_guard_enabled: bool = False
    corpus_guard_min_documents: int = 0
    corpus_guard_current_documents: int = 0
    corpus_guard_remaining_documents: int = 0
    corpus_guard_progress_pct: float = 0.0
    corpus_guard_ready: bool = True
    corpus_guard_status: str = "ready"
    corpus_guard_message: Optional[str] = None
    active_embedding_model: str = ""
    active_embedding_mode: str = ""
    embedding_warning: Optional[str] = None


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


class ResearchStorageUsageResponse(BaseModel):
    topic_key: str
    documents_count: int = 0
    chunks_count: int = 0
    embeddings_count: int = 0
    raw_payload_bytes: int = 0
    extracted_text_bytes: int = 0
    chunks_bytes: int = 0
    embeddings_bytes: int = 0
    total_bytes: int = 0


class ResearchRunProgressRecord(BaseModel):
    run_id: str
    trigger: str
    status: str
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    elapsed_seconds: int = 0
    sources_selected: int = 0
    items_seen: int = 0
    items_new: int = 0
    items_deduped: int = 0
    items_failed: int = 0


class ResearchAiUsageModelRecord(BaseModel):
    embedding_model_id: str
    documents_count: int = 0
    chunks_count: int = 0
    estimated_tokens_total: int = 0
    estimated_tokens_24h: int = 0
    external_api: bool = False


class ResearchOpsProgressResponse(BaseModel):
    topic_key: str
    queued_runs: int = 0
    running_runs: int = 0
    stages: Dict[str, int] = Field(default_factory=dict)
    chunks_count: int = 0
    embeddings_count: int = 0
    embedding_coverage_pct: float = 0.0
    db_size_bytes: int = 0
    disk_total_bytes: int = 0
    disk_used_bytes: int = 0
    disk_free_bytes: int = 0
    disk_used_pct: float = 0.0
    cpu_count: int = 0
    cpu_load_1m: float = 0.0
    cpu_load_5m: float = 0.0
    cpu_load_15m: float = 0.0
    memory_total_bytes: int = 0
    memory_available_bytes: int = 0
    memory_used_bytes: int = 0
    memory_used_pct: float = 0.0
    ai_external_calls_estimate: int = 0
    ai_estimated_tokens_total: int = 0
    ai_estimated_tokens_24h: int = 0
    corpus_guard_enabled: bool = False
    corpus_guard_min_documents: int = 0
    corpus_guard_current_documents: int = 0
    corpus_guard_remaining_documents: int = 0
    corpus_guard_progress_pct: float = 0.0
    corpus_guard_ready: bool = True
    corpus_guard_status: str = "ready"
    corpus_guard_message: Optional[str] = None
    active_embedding_model: str = ""
    active_embedding_mode: str = ""
    embedding_warning: Optional[str] = None
    ai_models: List[ResearchAiUsageModelRecord] = Field(default_factory=list)
    runs: List[ResearchRunProgressRecord] = Field(default_factory=list)


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
    publisher_type: Optional[str] = None
    source_class: Optional[str] = None
    default_decision_domains: List[str] = Field(default_factory=list)
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


class ResearchTopicSummary(BaseModel):
    topic_key: str
    label: str
    description: str
    source_count: int = 0
    document_count: int = 0
    embedded_document_count: int = 0
    last_published_at: Optional[datetime] = None
    last_ingested_at: Optional[datetime] = None


class ResearchTopicListResponse(BaseModel):
    items: List[ResearchTopicSummary] = Field(default_factory=list)


class ResearchTopicTheme(BaseModel):
    name: str
    score: float = 0.0


class ResearchTopicDocument(BaseModel):
    document_id: str
    source_id: str
    title: str
    canonical_url: str
    published_at: Optional[datetime] = None
    summary: str = ""
    content_type: str = "company_blog"
    publisher_type: str = "independent"
    source_class: str = "external_commentary"
    topic_tags: List[str] = Field(default_factory=list)
    decision_domains: List[str] = Field(default_factory=list)
    metrics: List[ResearchMetric] = Field(default_factory=list)
    notable_quotes: List[ResearchQuote] = Field(default_factory=list)
    citations: List[ResearchCitation] = Field(default_factory=list)


class ResearchTopicDetailResponse(BaseModel):
    topic_key: str
    label: str
    description: str
    source_count: int = 0
    document_count: int = 0
    embedded_document_count: int = 0
    last_published_at: Optional[datetime] = None
    last_ingested_at: Optional[datetime] = None
    top_sources: List[ResearchSourceMetricRecord] = Field(default_factory=list)
    top_themes: List[ResearchTopicTheme] = Field(default_factory=list)
    suggested_queries: List[str] = Field(default_factory=list)


class ResearchTopicDocumentsResponse(BaseModel):
    topic_key: str
    items: List[ResearchTopicDocument] = Field(default_factory=list)


class ResearchTopicSearchResponse(BaseModel):
    query: str
    items: List[ResearchTopicSummary] = Field(default_factory=list)


class ResearchTopicSummarizeRequest(BaseModel):
    focus: Optional[str] = None
    recency_days: Optional[int] = Field(default=None, ge=0)
    max_items: int = Field(default=5, ge=1, le=10)


class ResearchTopicSummarizeResponse(BaseModel):
    topic_key: str
    focus: Optional[str] = None
    synthesis: str
    themes: List[ResearchTopicTheme] = Field(default_factory=list)
    suggested_queries: List[str] = Field(default_factory=list)
    items: List[ResearchTopicDocument] = Field(default_factory=list)
    citations: List[ResearchCitation] = Field(default_factory=list)


class ResearchDecisionAlternative(BaseModel):
    title: str
    summary: str
    citations: List[ResearchCitation] = Field(default_factory=list)


class ResearchDecisionRisk(BaseModel):
    risk: str
    mitigation: str = ""


class ResearchDecisionPackResponse(BaseModel):
    query: str
    topic_key: str
    decision_domain: str = ""
    recommended_approach: str
    alternatives: List[ResearchDecisionAlternative] = Field(default_factory=list)
    tradeoffs: List[ResearchTradeoff] = Field(default_factory=list)
    risks: List[ResearchDecisionRisk] = Field(default_factory=list)
    workflow_recommendations: List[ResearchRecommendation] = Field(default_factory=list)
    implementation_notes: List[str] = Field(default_factory=list)
    supporting_evidence: List[ResearchContextPackItem] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    confidence: Literal["high", "med", "low"]
    trace: ResearchContextPackTrace


class ResearchWeeklyDigestItem(BaseModel):
    cluster_key: str
    cluster_title: str
    cluster_summary: str
    why_it_matters: str = ""
    top_metric: Optional[ResearchMetric] = None
    top_quote: Optional[ResearchQuote] = None
    citations: List[ResearchCitation] = Field(default_factory=list)
    document_ids: List[str] = Field(default_factory=list)


class ResearchWeeklyDigestResponse(BaseModel):
    topic_key: str
    days: int
    items: List[ResearchWeeklyDigestItem] = Field(default_factory=list)


class ResearchDomainSummaryResponse(BaseModel):
    topic_key: str
    decision_domain: str
    summary: str
    recommendations: List[ResearchRecommendation] = Field(default_factory=list)
    tradeoffs: List[ResearchTradeoff] = Field(default_factory=list)
    workflow_patterns: List[str] = Field(default_factory=list)
    citations: List[ResearchCitation] = Field(default_factory=list)
