from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field
from pydantic import AliasChoices


class ProjectUpsert(BaseModel):
    project_id: str = Field(validation_alias=AliasChoices("project_id", "id"))
    name: str
    status: Optional[str] = None
    updated_at: Optional[datetime] = None
    raw: Optional[Dict[str, Any]] = None


class TaskUpsert(BaseModel):
    task_id: str = Field(validation_alias=AliasChoices("task_id", "id"))
    title: str
    status: Optional[str] = None
    priority: Optional[str] = None
    due: Optional[str] = None
    project_id: Optional[str] = None
    updated_at: Optional[datetime] = None
    raw: Optional[Dict[str, Any]] = None


class SyncProjectsRequest(BaseModel):
    source: Optional[str] = None
    items: List[ProjectUpsert]


class SyncTasksRequest(BaseModel):
    source: Optional[str] = None
    items: List[TaskUpsert]


class SearchRequest(BaseModel):
    query: str
    limit: int = 5


class TaskSearchRequest(BaseModel):
    query: str
    limit: int = 5
    project_id: Optional[str] = None
    status: Optional[str] = None


class SearchResult(BaseModel):
    id: str
    label: str
    score: float
    status: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class SearchResponse(BaseModel):
    results: List[SearchResult]


class ProjectResponse(BaseModel):
    project_id: str
    name: str
    status: Optional[str] = None
    updated_at: Optional[datetime] = None
    source: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class TaskResponse(BaseModel):
    task_id: str
    title: str
    status: Optional[str] = None
    priority: Optional[str] = None
    due: Optional[str] = None
    project_id: Optional[str] = None
    updated_at: Optional[datetime] = None
    source: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class ContextPackRequest(BaseModel):
    query: str
    topics: Optional[List[str]] = None
    token_budget: Optional[int] = None
    recency_days: Optional[int] = None
    max_items: Optional[int] = None


class CitePointer(BaseModel):
    article_id: str
    section_id: Optional[str] = None


class SignalItem(BaseModel):
    claim: str
    why: str
    tradeoff: Optional[str] = None
    cite: CitePointer


class CitationItem(BaseModel):
    url: str
    article_id: str
    section_id: Optional[str] = None


class ContextPackItem(BaseModel):
    article_id: str
    title: str
    url: str
    summary: str
    signals: List[SignalItem]
    citations: List[CitationItem]


class ContextPack(BaseModel):
    items: List[ContextPackItem]


class TraceInfo(BaseModel):
    trace_id: str
    retrieved_article_ids: List[str]
    timing_ms: Optional[Dict[str, Any]] = None


class ContextPackResponse(BaseModel):
    pack: ContextPack
    retrieval_confidence: Literal["high", "med", "low"]
    next_action: Literal["proceed", "refine_query", "expand_sections"]
    trace: TraceInfo


class OutlineItem(BaseModel):
    section_id: str
    heading: str
    blurb: Optional[str] = None


class OutlineResponse(BaseModel):
    article_id: str
    outline: List[OutlineItem]


class SectionsRequest(BaseModel):
    section_ids: List[str]


class SectionItem(BaseModel):
    section_id: str
    heading: str
    content: str
    rank: int


class SectionsResponse(BaseModel):
    article_id: str
    sections: List[SectionItem]


class ChunkSearchRequest(BaseModel):
    query: str
    max_chars: Optional[int] = None
    max_chunks: Optional[int] = None


class ChunkItem(BaseModel):
    section_id: str
    snippet: str
    score: Optional[float] = None


class ChunkSearchResponse(BaseModel):
    article_id: str
    chunks: List[ChunkItem]


class IntelIngestRequest(BaseModel):
    fixture_bundle: str


class IntelIngestResponse(BaseModel):
    ingested_article_ids: List[str]


class IntelIngestUrlsRequest(BaseModel):
    urls: List[str]
    topics: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    force_refetch: Optional[bool] = False
    enrich: Optional[bool] = True


class IntelIngestUrlsResult(BaseModel):
    url: str
    status: Literal["queued", "deduped", "failed"]
    article_id: Optional[str] = None
    job_id: Optional[str] = None
    reason: Optional[str] = None


class IntelIngestUrlsResponse(BaseModel):
    results: List[IntelIngestUrlsResult]


class IntelArticleFetchMeta(BaseModel):
    http_status: Optional[int] = None
    content_type: Optional[str] = None
    fetched_at: Optional[str] = None
    warnings: Optional[List[str]] = None


class IntelArticleExtractionMeta(BaseModel):
    method: Optional[str] = None
    confidence: Optional[float] = None
    warnings: Optional[List[str]] = None


class IntelArticleEnrichmentMeta(BaseModel):
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    confidence: Optional[float] = None
    token_usage: Optional[Dict[str, Any]] = None
    warnings: Optional[List[str]] = None


class IntelArticleStatusMeta(BaseModel):
    fetch: Optional[IntelArticleFetchMeta] = None
    extraction: Optional[IntelArticleExtractionMeta] = None
    enrichment: Optional[IntelArticleEnrichmentMeta] = None


class IntelArticleStatusResponse(BaseModel):
    article_id: str
    url: str
    title: Optional[str] = None
    status: Literal["queued", "extracted", "enriched", "failed", "partial"]
    topics: List[str]
    summary: Optional[str] = None
    signals: Optional[List[Dict[str, Any]]] = None
    outline: Optional[List[Dict[str, Any]]] = None
    meta: Optional[IntelArticleStatusMeta] = None
    last_error: Optional[str] = None
