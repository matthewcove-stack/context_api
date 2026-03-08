from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SearchToolRequest(BaseModel):
    query: str = Field(min_length=1)
    topic_key: str = Field(min_length=1)
    source_ids: List[str] = Field(default_factory=list)
    token_budget: Optional[int] = Field(default=None, ge=1)
    recency_days: Optional[int] = Field(default=None, ge=0)
    max_items: int = Field(default=6, ge=1, le=20)
    min_relevance_score: Optional[float] = None
    intent_mode: Optional[str] = None
    decision_domain: Optional[str] = None
    content_types: List[str] = Field(default_factory=list)
    source_classes: List[str] = Field(default_factory=list)
    publisher_types: List[str] = Field(default_factory=list)
    must_have: List[str] = Field(default_factory=list)
    exclude_content_types: List[str] = Field(default_factory=list)
    sort_mode: Optional[str] = None
    evidence_types: List[str] = Field(default_factory=list)
    problem_tags: List[str] = Field(default_factory=list)
    intervention_tags: List[str] = Field(default_factory=list)
    tradeoff_dimensions: List[str] = Field(default_factory=list)
    corpus_preference: Optional[str] = None
    relation_intent: Optional[str] = None
    source_trust_min: Optional[float] = None
    coverage_bias: Optional[str] = None


class SearchCitation(BaseModel):
    document_id: str
    chunk_id: str


class SearchSignal(BaseModel):
    claim: str
    why: str
    cite: SearchCitation


class SearchScoreBreakdown(BaseModel):
    total: float
    lexical: float
    embedding: float = 0.0
    recency: float = 0.0
    source_weight: float = 0.0


class SearchResultItem(BaseModel):
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
    metrics: List[Dict[str, object]] = Field(default_factory=list)
    notable_quotes: List[Dict[str, object]] = Field(default_factory=list)
    tradeoffs: List[Dict[str, object]] = Field(default_factory=list)
    recommendations: List[Dict[str, object]] = Field(default_factory=list)
    document_signal_score: float = 0.0
    evidence_quality: float = 0.0
    corroboration_count: int = 0
    contradiction_count: int = 0
    freshness_score: float = 0.0
    coverage_score: float = 0.0
    problem_tags: List[str] = Field(default_factory=list)
    intervention_tags: List[str] = Field(default_factory=list)
    tradeoff_dimensions: List[str] = Field(default_factory=list)
    signals: List[SearchSignal] = Field(default_factory=list)
    citations: List[SearchCitation] = Field(default_factory=list)
    score_breakdown: SearchScoreBreakdown


class SearchToolResponse(BaseModel):
    retrieval_confidence: Literal["high", "med", "low"]
    next_action: Literal["proceed", "refine_query", "expand_sections"]
    trace_id: str
    retrieved_document_ids: List[str] = Field(default_factory=list)
    timing_ms: Dict[str, int] = Field(default_factory=dict)
    embedding_model_id: str = ""
    embedding_mode: str = ""
    embedding_warning: Optional[str] = None
    items: List[SearchResultItem] = Field(default_factory=list)


class FetchToolRequest(BaseModel):
    document_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    max_chunks: int = Field(default=6, ge=1, le=20)
    max_chars: int = Field(default=600, ge=80, le=4000)


class FetchChunk(BaseModel):
    chunk_id: str
    snippet: str
    score: Optional[float] = None
    heading_path: List[str] = Field(default_factory=list)


class FetchToolResponse(BaseModel):
    document_id: str
    chunks: List[FetchChunk] = Field(default_factory=list)


class TopicSummary(BaseModel):
    topic_key: str
    label: str
    description: str
    source_count: int = 0
    document_count: int = 0
    embedded_document_count: int = 0
    last_published_at: Optional[datetime] = None
    last_ingested_at: Optional[datetime] = None


class TopicSearchToolResponse(BaseModel):
    query: str
    items: List[TopicSummary] = Field(default_factory=list)


class TopicDocument(BaseModel):
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
    metrics: List[Dict[str, object]] = Field(default_factory=list)
    notable_quotes: List[Dict[str, object]] = Field(default_factory=list)
    citations: List[SearchCitation] = Field(default_factory=list)


class TopicDetailToolResponse(BaseModel):
    topic_key: str
    label: str
    description: str
    source_count: int = 0
    document_count: int = 0
    embedded_document_count: int = 0
    last_published_at: Optional[datetime] = None
    last_ingested_at: Optional[datetime] = None
    top_sources: List[Dict[str, object]] = Field(default_factory=list)
    top_themes: List[Dict[str, object]] = Field(default_factory=list)
    suggested_queries: List[str] = Field(default_factory=list)


class TopicDocumentsToolResponse(BaseModel):
    topic_key: str
    items: List[TopicDocument] = Field(default_factory=list)


class TopicSummarizeToolResponse(BaseModel):
    topic_key: str
    focus: Optional[str] = None
    synthesis: str
    themes: List[Dict[str, object]] = Field(default_factory=list)
    suggested_queries: List[str] = Field(default_factory=list)
    items: List[TopicDocument] = Field(default_factory=list)
    citations: List[SearchCitation] = Field(default_factory=list)


class DecisionSearchToolResponse(BaseModel):
    query: str
    topic_key: str
    decision_domain: str = ""
    recommended_approach: str
    alternatives: List[Dict[str, object]] = Field(default_factory=list)
    tradeoffs: List[Dict[str, object]] = Field(default_factory=list)
    risks: List[Dict[str, object]] = Field(default_factory=list)
    workflow_recommendations: List[Dict[str, object]] = Field(default_factory=list)
    implementation_notes: List[str] = Field(default_factory=list)
    supporting_evidence: List[SearchResultItem] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    confidence: str
    trace_id: str
    timing_ms: Dict[str, int] = Field(default_factory=dict)


class WeeklyDigestToolResponse(BaseModel):
    topic_key: str
    days: int
    items: List[Dict[str, object]] = Field(default_factory=list)


class DomainSummaryToolResponse(BaseModel):
    topic_key: str
    decision_domain: str
    summary: str
    recommendations: List[Dict[str, object]] = Field(default_factory=list)
    tradeoffs: List[Dict[str, object]] = Field(default_factory=list)
    workflow_patterns: List[str] = Field(default_factory=list)
    citations: List[SearchCitation] = Field(default_factory=list)


class EvidenceToolResponse(BaseModel):
    query: str
    topic_key: str
    contradictions_present: bool = False
    coverage_summary: Dict[str, float] = Field(default_factory=dict)
    trace_id: str = ""
    timing_ms: Dict[str, int] = Field(default_factory=dict)
    items: List[Dict[str, object]] = Field(default_factory=list)


class RelatedEvidenceToolResponse(BaseModel):
    topic_key: str
    relation_intent: str = "related"
    seed_items: List[Dict[str, object]] = Field(default_factory=list)
    related_items: List[Dict[str, object]] = Field(default_factory=list)
    relations: List[Dict[str, object]] = Field(default_factory=list)
    coverage_summary: Dict[str, float] = Field(default_factory=dict)


class CompareEvidenceToolResponse(BaseModel):
    query: str
    topic_key: str
    clusters: List[Dict[str, object]] = Field(default_factory=list)
    overall_tradeoffs: List[str] = Field(default_factory=list)
    contradictions_present: bool = False
    coverage_summary: Dict[str, float] = Field(default_factory=dict)
    trace_id: str = ""
    timing_ms: Dict[str, int] = Field(default_factory=dict)
