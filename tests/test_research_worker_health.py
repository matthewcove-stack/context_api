from __future__ import annotations

from app.research import worker


def _run(monkeypatch, counters: dict) -> tuple[list[str], list[str], list[str]]:
    successes: list[str] = []
    failures: list[str] = []
    statuses: list[str] = []
    monkeypatch.setattr(worker, "list_research_sources", lambda *args, **kwargs: [{"source_id": "source-1"}])
    monkeypatch.setattr(worker, "_process_source", lambda *args, **kwargs: counters)
    monkeypatch.setattr(worker, "update_research_run_counters", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker, "append_research_run_error", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker, "mark_research_source_success", lambda engine, source_id: successes.append(source_id))
    monkeypatch.setattr(
        worker,
        "mark_research_source_failure",
        lambda engine, source_id, **kwargs: failures.append(source_id),
    )
    monkeypatch.setattr(
        worker,
        "mark_research_ingestion_run_finished",
        lambda engine, run_id, status: statuses.append(status),
    )

    worker.process_run(object(), {"run_id": "run-1", "topic_key": "ai_research", "selected_source_ids": []})
    return successes, failures, statuses


def test_partial_item_failure_does_not_cool_down_healthy_source(monkeypatch) -> None:
    successes, failures, statuses = _run(
        monkeypatch,
        {
            "seen": 2,
            "new": 2,
            "deduped": 0,
            "succeeded": 1,
            "suppressed": 0,
            "failed": 1,
            "source_failed": False,
            "source_error": "item_fetch_failed",
        },
    )

    assert successes == ["source-1"]
    assert failures == []
    assert statuses == ["completed"]


def test_total_source_failure_marks_source_and_run_failed(monkeypatch) -> None:
    successes, failures, statuses = _run(
        monkeypatch,
        {
            "seen": 0,
            "new": 0,
            "deduped": 0,
            "succeeded": 0,
            "suppressed": 0,
            "failed": 1,
            "source_failed": True,
            "source_error": "source_fetch_failed status=500",
        },
    )

    assert successes == []
    assert failures == ["source-1"]
    assert statuses == ["failed"]


def test_drain_due_runs_enqueues_before_processing(monkeypatch) -> None:
    calls: list[str] = []
    outcomes = iter([True, True, False])
    monkeypatch.setattr(worker, "enqueue_due_schedule_runs", lambda engine: calls.append("enqueue") or 1)
    monkeypatch.setattr(worker, "run_once", lambda engine: calls.append("run") or next(outcomes))

    assert worker.drain_due_runs(object(), max_runs=10) == 2
    assert calls == ["enqueue", "run", "run", "run"]
