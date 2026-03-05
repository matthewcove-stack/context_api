from __future__ import annotations

import os
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.research.worker import run_once
from app.storage.db import count_research_bootstrap_events, create_db_engine


class _BootstrapFixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/feed":
            body = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>Bootstrap Feed</title>
    <item><guid>c1</guid><link>{self.server.base_url}/article-1</link></item>
    <item><guid>c2</guid><link>{self.server.base_url}/article-2</link></item>
  </channel>
</rss>"""
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            return
        if self.path.startswith("/article-1"):
            html = "<html><head><title>Onboarding One</title></head><body><p>GPU supply is stabilizing.</p></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            return
        if self.path.startswith("/article-2"):
            html = "<html><head><title>Onboarding Two</title></head><body><p>HBM capacity is improving.</p></body></html>"
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
    server = HTTPServer(("127.0.0.1", 0), _BootstrapFixtureHandler)
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


def test_bootstrap_creates_sources_and_run() -> None:
    server, base_url = _start_server()
    topic_key = f"bootstrap-{uuid.uuid4().hex[:8]}"
    settings = _build_settings()
    client = TestClient(create_app(settings))
    headers = {"Authorization": f"Bearer {settings.context_api_token}"}

    response = client.post(
        "/v2/research/sources/bootstrap",
        json={
            "topic_key": topic_key,
            "suggestions": [
                {
                    "kind": "rss",
                    "name": "Primary Feed",
                    "base_url": f"{base_url}/feed",
                    "tags": ["seed"],
                }
            ],
            "trigger_ingest": True,
            "trigger": "event",
            "idempotency_key": "bootstrap-1",
        },
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["created"] == 1
    assert payload["summary"]["invalid"] == 0
    assert payload["ingest"]["triggered"] is True
    assert payload["ingest"]["run_id"]
    assert payload["results"][0]["status"] in {"created", "updated"}
    server.shutdown()


def test_bootstrap_dedupes_and_handles_invalid_urls() -> None:
    server, base_url = _start_server()
    topic_key = f"bootstrap-{uuid.uuid4().hex[:8]}"
    settings = _build_settings()
    client = TestClient(create_app(settings))
    headers = {"Authorization": f"Bearer {settings.context_api_token}"}

    response = client.post(
        "/v2/research/sources/bootstrap",
        json={
            "topic_key": topic_key,
            "suggestions": [
                {"kind": "rss", "name": "Feed 1", "base_url": f"{base_url}/feed"},
                {"kind": "rss", "name": "Feed 1 dup", "base_url": f"{base_url}/feed?utm_source=test"},
                {"kind": "rss", "name": "Bad", "base_url": "http:///bad"},
            ],
            "trigger_ingest": False,
        },
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["received"] == 3
    assert payload["summary"]["invalid"] == 1
    assert payload["summary"]["skipped_duplicate"] == 1
    assert payload["summary"]["valid"] == 1
    statuses = [item["status"] for item in payload["results"]]
    assert "invalid" in statuses
    assert "skipped_duplicate" in statuses
    server.shutdown()


def test_bootstrap_idempotency_returns_same_result() -> None:
    server, base_url = _start_server()
    topic_key = f"bootstrap-{uuid.uuid4().hex[:8]}"
    settings = _build_settings()
    client = TestClient(create_app(settings))
    headers = {"Authorization": f"Bearer {settings.context_api_token}"}

    body = {
        "topic_key": topic_key,
        "suggestions": [{"kind": "rss", "name": "Primary Feed", "base_url": f"{base_url}/feed"}],
        "trigger_ingest": True,
        "idempotency_key": "stable-key",
    }
    first = client.post("/v2/research/sources/bootstrap", json=body, headers=headers)
    second = client.post("/v2/research/sources/bootstrap", json=body, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["summary"] == second.json()["summary"]
    assert first.json()["ingest"]["run_id"] == second.json()["ingest"]["run_id"]

    engine = create_db_engine(settings.database_url)
    assert count_research_bootstrap_events(engine, topic_key=topic_key) == 1
    server.shutdown()


def test_bootstrap_dry_run_makes_no_writes() -> None:
    server, base_url = _start_server()
    topic_key = f"bootstrap-{uuid.uuid4().hex[:8]}"
    settings = _build_settings()
    client = TestClient(create_app(settings))
    headers = {"Authorization": f"Bearer {settings.context_api_token}"}

    response = client.post(
        "/v2/research/sources/bootstrap",
        json={
            "topic_key": topic_key,
            "suggestions": [{"kind": "rss", "name": "Primary Feed", "base_url": f"{base_url}/feed"}],
            "trigger_ingest": True,
            "dry_run": True,
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["ingest"]["triggered"] is False
    sources = client.get(f"/v2/research/sources?topic_key={topic_key}", headers=headers)
    assert sources.status_code == 200
    assert sources.json()["items"] == []

    engine = create_db_engine(settings.database_url)
    assert count_research_bootstrap_events(engine, topic_key=topic_key) == 0
    server.shutdown()


def test_bootstrap_to_worker_to_context_pack() -> None:
    server, base_url = _start_server()
    topic_key = f"bootstrap-{uuid.uuid4().hex[:8]}"
    settings = _build_settings()
    client = TestClient(create_app(settings))
    headers = {"Authorization": f"Bearer {settings.context_api_token}"}

    bootstrap = client.post(
        "/v2/research/sources/bootstrap",
        json={
            "topic_key": topic_key,
            "suggestions": [{"kind": "rss", "name": "Primary Feed", "base_url": f"{base_url}/feed"}],
            "trigger_ingest": True,
        },
        headers=headers,
    )
    assert bootstrap.status_code == 200
    run_id = bootstrap.json()["ingest"]["run_id"]
    assert run_id

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
        json={"query": "gpu supply", "topic_key": topic_key, "max_items": 2},
        headers=headers,
    )
    assert pack.status_code == 200
    assert pack.json()["pack"]["items"]
    server.shutdown()


def test_bootstrap_status_reflects_latest_run() -> None:
    server, base_url = _start_server()
    topic_key = f"bootstrap-{uuid.uuid4().hex[:8]}"
    settings = _build_settings()
    client = TestClient(create_app(settings))
    headers = {"Authorization": f"Bearer {settings.context_api_token}"}
    bootstrap = client.post(
        "/v2/research/sources/bootstrap",
        json={
            "topic_key": topic_key,
            "suggestions": [{"kind": "rss", "name": "Primary Feed", "base_url": f"{base_url}/feed"}],
            "trigger_ingest": True,
        },
        headers=headers,
    )
    assert bootstrap.status_code == 200
    status = client.get(f"/v2/research/bootstrap/status?topic_key={topic_key}", headers=headers)
    assert status.status_code == 200
    payload = status.json()
    assert payload["latest_bootstrap"] is not None
    assert payload["latest_bootstrap"]["summary"]["received"] == 1
    assert payload["latest_bootstrap"]["run_id"] == bootstrap.json()["ingest"]["run_id"]
    server.shutdown()


def test_bootstrap_limit_enforced(monkeypatch) -> None:
    server, base_url = _start_server()
    topic_key = f"bootstrap-{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("RESEARCH_BOOTSTRAP_MAX_SUGGESTIONS", "1")
    settings = _build_settings()
    client = TestClient(create_app(settings))
    headers = {"Authorization": f"Bearer {settings.context_api_token}"}

    response = client.post(
        "/v2/research/sources/bootstrap",
        json={
            "topic_key": topic_key,
            "suggestions": [
                {"kind": "rss", "name": "Primary Feed", "base_url": f"{base_url}/feed"},
                {"kind": "rss", "name": "Secondary Feed", "base_url": f"{base_url}/feed?x=1"},
            ],
        },
        headers=headers,
    )
    assert response.status_code == 400
    assert "exceeds limit" in response.json()["detail"]
    server.shutdown()
