from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.research.contracts import ResearchBootstrapResult, ResearchBootstrapSummary


class SourcesBootstrapToolRequest(BaseModel):
    topic_key: str = Field(min_length=1)
    suggestions: list[dict] = Field(min_length=1, max_length=200)
    trigger_ingest: bool = True
    trigger: Literal["manual", "event"] = "event"
    idempotency_key: Optional[str] = None
    dry_run: bool = False


class SourcesBootstrapToolResponse(BaseModel):
    topic_key: str
    summary: ResearchBootstrapSummary
    results: list[ResearchBootstrapResult]
    ingest: dict


class IngestStatusToolResponse(BaseModel):
    run_id: str
    status: Literal["queued", "running", "completed", "failed"]
    counters: dict
    errors: list[str] = Field(default_factory=list)


class OpsSummaryToolResponse(BaseModel):
    topic_key: str
    sources_total: int
    sources_enabled: int
    sources_in_cooldown: int
    documents_total: int
    documents_embedded: int
    documents_failed: int
    runs_open: int
    runs_failed_24h: int
    run_failure_rate_24h: float
    retrieval_queries_24h: int
    retrieval_errors_24h: int
