from __future__ import annotations

import os
import uuid

import pytest

from app.research import worker
from app.storage.db import (
    claim_next_research_ingestion_run,
    create_db_engine,
    create_research_ingestion_run,
    mark_research_ingestion_run_finished,
    touch_research_ingestion_run,
)


def _source() -> dict:
    return {
        "source_id": "source-1",
        "base_url_canonical": "https://example.com/feed.xml",
        "kind": "rss",
        "robots_mode": "strict",
        "max_items_per_run": 10,
        "rate_limit_per_hour": 60,
    }


def test_source_processing_heartbeats_before_fetch_and_each_item(monkeypatch) -> None:
    heartbeats: list[str] = []
    monkeypatch.setattr(
        worker,
        "touch_research_ingestion_run",
        lambda engine, run_id: heartbeats.append(str(run_id)) or True,
    )
    monkeypatch.setattr(worker, "source_url_allowed", lambda url: True)
    monkeypatch.setattr(worker, "_fetch_with_retries", lambda url: {"status_code": 200, "html": "feed"})
    monkeypatch.setattr(
        worker,
        "discover_candidate_items",
        lambda **kwargs: [
            {"url": "https://example.com/one"},
            {"url": "https://example.com/two"},
        ],
    )
    monkeypatch.setattr(worker, "is_allowed_by_robots", lambda **kwargs: True)
    monkeypatch.setattr(worker, "upsert_research_document_seed", lambda *args, **kwargs: "deduped")
    monkeypatch.setattr(worker, "get_research_document", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker, "set_research_source_polled", lambda *args, **kwargs: None)

    counters = worker._process_source(object(), run_id="run-1", source=_source())

    assert counters["deduped"] == 2
    assert heartbeats == ["run-1", "run-1", "run-1"]


def test_source_processing_stops_if_run_is_no_longer_active(monkeypatch) -> None:
    monkeypatch.setattr(worker, "touch_research_ingestion_run", lambda *args, **kwargs: False)

    with pytest.raises(worker.ResearchRunInactive):
        worker._process_source(object(), run_id="run-1", source=_source())


def test_process_run_does_not_reopen_an_inactive_run(monkeypatch) -> None:
    finished: list[str] = []
    monkeypatch.setattr(worker, "list_research_sources", lambda *args, **kwargs: [_source()])
    monkeypatch.setattr(
        worker,
        "_process_source",
        lambda *args, **kwargs: (_ for _ in ()).throw(worker.ResearchRunInactive("closed")),
    )
    monkeypatch.setattr(
        worker,
        "mark_research_ingestion_run_finished",
        lambda engine, run_id, status: finished.append(status),
    )

    worker.process_run(object(), {"run_id": "run-1", "topic_key": "ai_research", "selected_source_ids": []})

    assert finished == []


def test_run_heartbeat_only_touches_running_rows() -> None:
    engine = create_db_engine(os.environ["DATABASE_URL"])
    run = create_research_ingestion_run(
        engine,
        topic_key=f"heartbeat-{uuid.uuid4().hex[:8]}",
        trigger="manual",
        requested_source_ids=[],
        selected_source_ids=[],
        idempotency_key=None,
    )

    assert touch_research_ingestion_run(engine, run_id=run["run_id"]) is False
    claimed = claim_next_research_ingestion_run(engine)
    assert claimed is not None
    assert str(claimed["run_id"]) == str(run["run_id"])
    assert touch_research_ingestion_run(engine, run_id=run["run_id"]) is True

    mark_research_ingestion_run_finished(engine, run_id=run["run_id"], status="completed")
    assert touch_research_ingestion_run(engine, run_id=run["run_id"]) is False
