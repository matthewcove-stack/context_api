from __future__ import annotations

import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.research.worker import run_once
from app.storage.db import count_research_query_logs, create_db_engine


class _RetrievalFixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/feed":
            body = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>Retrieval Feed</title>
    <item><guid>b1</guid><link>{self.server.base_url}/article-1</link></item>
    <item><guid>b2</guid><link>{self.server.base_url}/article-2</link></item>
  </channel>
</rss>"""
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            return
        if self.path.startswith("/article-1"):
            html = """
            <html><head><title>GPU Supply Watch</title></head>
            <body>
            <p>GPU supply chain disruptions are easing this quarter.</p>
            <p>Lead times for packaging are still elevated.</p>
            </body></html>
            """
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            return
        if self.path.startswith("/article-2"):
            html = """
            <html><head><title>Semiconductor Capacity</title></head>
            <body>
            <p>Semiconductor fabs report improving yields and supply.</p>
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
    server = HTTPServer(("127.0.0.1", 0), _RetrievalFixtureHandler)
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


def test_phase4_research_retrieval_and_query_logging() -> None:
    server, base_url = _start_server()
    topic_key = f"phase4-{uuid.uuid4().hex[:8]}"
    settings = _build_settings()
    app = create_app(settings)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {settings.context_api_token}"}

    upsert = client.post(
        "/v2/research/sources/upsert",
        json={
            "topic_key": topic_key,
            "kind": "rss",
            "name": "Retrieval feed",
            "base_url": f"{base_url}/feed",
            "poll_interval_minutes": 60,
            "rate_limit_per_hour": 3600,
            "robots_mode": "strict",
            "enabled": True,
            "tags": ["retrieval"],
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
            "idempotency_key": "phase4-run-1",
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
    status = client.get(f"/v2/research/ingest/runs/{run_id}", headers=headers)
    assert status.status_code == 200
    assert status.json()["status"] == "completed"

    pack = client.post(
        "/v2/research/context/pack",
        json={
            "query": "gpu supply chain",
            "topic_key": topic_key,
            "max_items": 2,
        },
        headers=headers,
    )
    assert pack.status_code == 200
    pack_data = pack.json()
    assert pack_data["pack"]["items"]
    assert pack_data["trace"]["trace_id"]
    first_item = pack_data["pack"]["items"][0]
    assert first_item["document_id"]
    assert first_item["citations"]
    assert first_item["score_breakdown"]["total"] >= 0.0

    chunks = client.post(
        f"/v2/research/documents/{first_item['document_id']}/chunks:search",
        json={"query": "supply", "max_chunks": 2, "max_chars": 180},
        headers=headers,
    )
    assert chunks.status_code == 200
    chunk_items = chunks.json()["chunks"]
    assert chunk_items
    assert chunk_items[0]["chunk_id"]
    assert chunk_items[0]["snippet"]

    assert count_research_query_logs(engine, topic_key=topic_key) >= 1
    server.shutdown()
