from __future__ import annotations

import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.research.worker import enqueue_due_schedule_runs, run_once
from app.storage.db import create_db_engine, get_research_source_policy, list_due_research_sources


class _HardeningFixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/feed":
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"upstream failure")
            return
        if self.path == "/robots.txt":
            robots = "User-agent: *\nAllow: /\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(robots.encode("utf-8"))
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *_args: object, **_kwargs: object) -> None:
        return


def _start_server() -> tuple[HTTPServer, str]:
    server = HTTPServer(("127.0.0.1", 0), _HardeningFixtureHandler)
    host, port = server.server_address
    base_url = f"http://{host}:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, base_url


def _build_settings() -> Settings:
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        context_api_token=os.environ.get("CONTEXT_API_TOKEN", "change-me"),
        version="0.0.0",
        git_sha="test",
    )


def test_phase6_source_cooldown_and_schedule_backpressure(monkeypatch) -> None:
    server, base_url = _start_server()
    topic_key = f"phase6-{uuid.uuid4().hex[:8]}"
    settings = _build_settings()
    app = create_app(settings)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {settings.context_api_token}"}

    upsert = client.post(
        "/v2/research/sources/upsert",
        json={
            "topic_key": topic_key,
            "kind": "rss",
            "name": "Hardening feed",
            "base_url": f"{base_url}/feed",
            "poll_interval_minutes": 1,
            "rate_limit_per_hour": 3600,
            "robots_mode": "strict",
            "enabled": True,
            "tags": ["hardening"],
        },
        headers=headers,
    )
    assert upsert.status_code == 200
    source_id = upsert.json()["source_id"]

    run_resp = client.post(
        "/v2/research/ingest/run",
        json={
            "topic_key": topic_key,
            "source_ids": [source_id],
            "trigger": "manual",
            "idempotency_key": "phase6-run-1",
        },
        headers=headers,
    )
    assert run_resp.status_code == 200
    run_id = run_resp.json()["run_id"]

    monkeypatch.setenv("RESEARCH_SOURCE_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("RESEARCH_SOURCE_COOLDOWN_MINUTES", "120")
    engine = create_db_engine(settings.database_url)
    run_once(engine)

    status = client.get(f"/v2/research/ingest/runs/{run_id}", headers=headers)
    assert status.status_code == 200
    payload = status.json()
    assert payload["status"] == "completed"
    assert payload["counters"]["items_failed"] >= 1

    policy = get_research_source_policy(engine, source_id=source_id)
    assert policy is not None
    assert int(policy.get("consecutive_failures") or 0) >= 1
    assert policy.get("cooldown_until") is not None

    due = list_due_research_sources(engine)
    due_source_ids = {str(row.get("source_id") or "") for row in due}
    assert source_id not in due_source_ids

    created = enqueue_due_schedule_runs(engine)
    assert created == 0
    server.shutdown()
