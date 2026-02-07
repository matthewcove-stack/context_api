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
