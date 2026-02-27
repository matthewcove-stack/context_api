from __future__ import annotations

import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.research.worker import enqueue_due_schedule_runs, run_once
from app.storage.db import (
    count_research_chunks,
    count_research_documents,
    count_research_documents_by_status,
    count_research_embeddings,
    create_db_engine,
    list_research_documents,
)


class _ResearchFixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/feed":
            body = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>Research Feed</title>
    <item><guid>a1</guid><link>{self.server.base_url}/article-1</link></item>
    <item><guid>a1-tracking</guid><link>{self.server.base_url}/article-1?utm_source=test</link></item>
    <item><guid>a2</guid><link>{self.server.base_url}/article-2</link></item>
  </channel>
</rss>"""
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            return
        if self.path.startswith("/article-1"):
            html = "<html><head><title>Article One</title></head><body><p>A1 body.</p></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            return
        if self.path.startswith("/article-2"):
            html = "<html><head><title>Article Two</title></head><body><p>A2 body.</p></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
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
    server = HTTPServer(("127.0.0.1", 0), _ResearchFixtureHandler)
    host, port = server.server_address
    base_url = f"http://{host}:{port}"
    setattr(server, "base_url", base_url)
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


def test_phase1_manual_run_ingests_and_dedupes() -> None:
    server, base_url = _start_server()
    topic_key = f"phase1-{uuid.uuid4().hex[:8]}"
    settings = _build_settings()
    app = create_app(settings)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {settings.context_api_token}"}

    upsert = client.post(
        "/v2/research/sources/upsert",
        json={
            "topic_key": topic_key,
            "kind": "rss",
            "name": "Fixture feed",
            "base_url": f"{base_url}/feed",
            "poll_interval_minutes": 60,
            "rate_limit_per_hour": 3600,
            "robots_mode": "strict",
            "enabled": True,
            "tags": ["test"],
        },
        headers=headers,
    )
    assert upsert.status_code == 200
    source_id = upsert.json()["source_id"]
    assert upsert.json()["status"] == "created"

    upsert_again = client.post(
        "/v2/research/sources/upsert",
        json={
            "topic_key": topic_key,
            "kind": "rss",
            "name": "Fixture feed updated",
            "base_url": f"{base_url}/feed",
            "poll_interval_minutes": 60,
            "rate_limit_per_hour": 3600,
            "robots_mode": "strict",
            "enabled": True,
            "tags": ["test", "updated"],
        },
        headers=headers,
    )
    assert upsert_again.status_code == 200
    assert upsert_again.json()["status"] == "updated"

    run_1 = client.post(
        "/v2/research/ingest/run",
        json={
            "topic_key": topic_key,
            "source_ids": [source_id],
            "trigger": "manual",
            "idempotency_key": "manual-run-1",
        },
        headers=headers,
    )
    assert run_1.status_code == 200
    run_id = run_1.json()["run_id"]
    assert run_1.json()["status"] == "queued"

    run_1_repeat = client.post(
        "/v2/research/ingest/run",
        json={
            "topic_key": topic_key,
            "source_ids": [source_id],
            "trigger": "manual",
            "idempotency_key": "manual-run-1",
        },
        headers=headers,
    )
    assert run_1_repeat.status_code == 200
    assert run_1_repeat.json()["run_id"] == run_id

    engine = create_db_engine(settings.database_url)
    for _ in range(10):
        run_once(engine)
        status = client.get(f"/v2/research/ingest/runs/{run_id}", headers=headers)
        if status.status_code == 200 and status.json()["status"] in {"completed", "failed"}:
            break
    status = client.get(f"/v2/research/ingest/runs/{run_id}", headers=headers)
    assert status.status_code == 200
    payload = status.json()
    assert payload["status"] == "completed"
    assert payload["counters"]["items_seen"] >= 3
    assert payload["counters"]["items_new"] >= 2
    assert payload["counters"]["items_deduped"] >= 1

    assert count_research_documents(engine, source_id=source_id) == 2
    assert count_research_documents_by_status(engine, source_id=source_id, status="embedded") == 2
    docs = list_research_documents(engine, source_id=source_id)
    for doc in docs:
        document_id = str(doc["document_id"])
        assert count_research_chunks(engine, document_id=document_id) >= 1
        assert count_research_embeddings(engine, document_id=document_id, embedding_model_id="hash-64") >= 1
    server.shutdown()


def test_phase1_schedule_enqueue_due_sources() -> None:
    server, base_url = _start_server()
    topic_key = f"schedule-{uuid.uuid4().hex[:8]}"
    settings = _build_settings()
    app = create_app(settings)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {settings.context_api_token}"}

    upsert = client.post(
        "/v2/research/sources/upsert",
        json={
            "topic_key": topic_key,
            "kind": "rss",
            "name": "Schedule feed",
            "base_url": f"{base_url}/feed",
            "poll_interval_minutes": 60,
            "rate_limit_per_hour": 3600,
            "robots_mode": "strict",
            "enabled": True,
            "tags": [],
        },
        headers=headers,
    )
    assert upsert.status_code == 200

    engine = create_db_engine(settings.database_url)
    created = enqueue_due_schedule_runs(engine)
    assert created >= 1
    created_again = enqueue_due_schedule_runs(engine)
    assert created_again == 0
    server.shutdown()
