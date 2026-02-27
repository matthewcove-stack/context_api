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
    status: Literal["discovered", "fetched", "extracted", "enriched", "failed"] = "discovered"
    fetch_meta: Dict[str, Any] = Field(default_factory=dict)
    extraction_meta: Dict[str, Any] = Field(default_factory=dict)
    enrichment_meta: Dict[str, Any] = Field(default_factory=dict)
