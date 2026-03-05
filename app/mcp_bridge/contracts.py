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
    signals: List[SearchSignal] = Field(default_factory=list)
    citations: List[SearchCitation] = Field(default_factory=list)
    score_breakdown: SearchScoreBreakdown


class SearchToolResponse(BaseModel):
    retrieval_confidence: Literal["high", "med", "low"]
    next_action: Literal["proceed", "refine_query", "expand_sections"]
    trace_id: str
    retrieved_document_ids: List[str] = Field(default_factory=list)
    timing_ms: Dict[str, int] = Field(default_factory=dict)
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


class FetchToolResponse(BaseModel):
    document_id: str
    chunks: List[FetchChunk] = Field(default_factory=list)

