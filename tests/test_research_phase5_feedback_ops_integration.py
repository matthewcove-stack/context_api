from __future__ import annotations

import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.research.worker import run_once
from app.storage.db import count_research_feedback, create_db_engine


class _FeedbackFixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/feed":
            body = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>Feedback Feed</title>
    <item><guid>c1</guid><link>{self.server.base_url}/article-1</link></item>
  </channel>
</rss>"""
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            return
        if self.path.startswith("/article-1"):
            html = """
            <html><head><title>Packaging Capacity Update</title></head>
            <body>
            <p>Advanced packaging lead times improved slightly this month.</p>
            </body></html>
            """
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
    server = HTTPServer(("127.0.0.1", 0), _FeedbackFixtureHandler)
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


def test_phase5_feedback_and_ops_summary() -> None:
    server, base_url = _start_server()
    topic_key = f"phase5-{uuid.uuid4().hex[:8]}"
    settings = _build_settings()
    app = create_app(settings)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {settings.context_api_token}"}

    upsert = client.post(
        "/v2/research/sources/upsert",
        json={
            "topic_key": topic_key,
            "kind": "rss",
            "name": "Feedback feed",
            "base_url": f"{base_url}/feed",
            "poll_interval_minutes": 60,
            "rate_limit_per_hour": 3600,
            "source_weight": 1.5,
            "robots_mode": "strict",
            "enabled": True,
            "tags": ["feedback"],
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
            "idempotency_key": "phase5-run-1",
        },
        headers=headers,
    )
    assert run_resp.status_code == 200
    run_id = run_resp.json()["run_id"]

    engine = create_db_engine(settings.database_url)
    for _ in range(10):
        run_once(engine)
        status = client.get(f"/v2/research/ingest/runs/{run_id}", headers=headers)
        if status.status_code == 200 and status.json()["status"] in {"completed", "failed"}:
            break

    pack = client.post(
        "/v2/research/context/pack",
        json={
            "query": "packaging lead times",
            "topic_key": topic_key,
            "max_items": 1,
        },
        headers=headers,
    )
    assert pack.status_code == 200
    pack_data = pack.json()
    item = pack_data["pack"]["items"][0]
    assert item["score_breakdown"]["embedding"] >= 0.0
    assert item["score_breakdown"]["recency"] >= 0.0
    assert item["score_breakdown"]["source_weight"] >= 0.0

    feedback = client.post(
        "/v2/research/retrieval/feedback",
        json={
            "trace_id": pack_data["trace"]["trace_id"],
            "document_id": item["document_id"],
            "chunk_id": item["citations"][0]["chunk_id"],
            "verdict": "useful",
            "notes": "good hit",
        },
        headers=headers,
    )
    assert feedback.status_code == 200
    assert feedback.json()["status"] == "recorded"
    assert count_research_feedback(engine, trace_id=pack_data["trace"]["trace_id"]) >= 1

    summary = client.get(f"/v2/research/ops/summary?topic_key={topic_key}", headers=headers)
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["sources_total"] >= 1
    assert payload["documents_total"] >= 1
    assert payload["retrieval_queries_24h"] >= 1

    sources = client.get(f"/v2/research/ops/sources?topic_key={topic_key}&limit=5", headers=headers)
    assert sources.status_code == 200
    source_items = sources.json()["items"]
    assert source_items
    assert source_items[0]["source_id"] == source_id
    assert source_items[0]["documents_total"] >= 1

    disable = client.post(f"/v2/research/sources/{source_id}/disable", headers=headers)
    assert disable.status_code == 200
    assert disable.json()["enabled"] is False

    enable = client.post(f"/v2/research/sources/{source_id}/enable", headers=headers)
    assert enable.status_code == 200
    assert enable.json()["enabled"] is True

    review_queue = client.get(f"/v2/research/review/queue?topic_key={topic_key}&limit=5", headers=headers)
    assert review_queue.status_code == 200
    queue_items = review_queue.json()["items"]
    assert queue_items
    assert queue_items[0]["trace_id"]

    redact = client.post(
        "/v2/research/governance/redact",
        json={"topic_key": topic_key, "older_than_days": 0},
        headers=headers,
    )
    assert redact.status_code == 200
    assert int(redact.json()["redacted_documents"]) >= 1
    server.shutdown()
