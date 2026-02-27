from __future__ import annotations

from app.research.contracts import (
    ResearchFeedbackRequest,
    ResearchContextPackRequest,
    ResearchIngestRunRequest,
    ResearchSourceUpsertRequest,
)


def test_research_source_upsert_contract_defaults() -> None:
    payload = ResearchSourceUpsertRequest(
        topic_key="ai_supply",
        kind="rss",
        name="Example Feed",
        base_url="https://example.com/feed",
    )
    assert payload.poll_interval_minutes == 60
    assert payload.rate_limit_per_hour == 30
    assert payload.source_weight == 1.0
    assert payload.robots_mode == "strict"


def test_research_ingest_request_contract_defaults() -> None:
    payload = ResearchIngestRunRequest(topic_key="ai_supply", trigger="manual")
    assert payload.source_ids == []
    assert payload.idempotency_key is None


def test_research_context_pack_request_defaults() -> None:
    payload = ResearchContextPackRequest(query="gpu supply", topic_key="ai_supply")
    assert payload.source_ids == []
    assert payload.max_items is None


def test_research_feedback_contract() -> None:
    payload = ResearchFeedbackRequest(
        trace_id="trace_1",
        document_id="doc_1",
        chunk_id="chk_1",
        verdict="useful",
    )
    assert payload.query_log_id is None
