from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from fastapi.testclient import TestClient

from app.config import Settings
from app.intel import enrich as enrich_module
from app.intel.worker import run_once
from app.main import create_app
from app.storage.db import create_db_engine


class _ArticleHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/article":
            self.send_response(404)
            self.end_headers()
            return
        html = """
        <html>
          <head><title>Sample Article</title></head>
          <body>
            <p>Signal snippet here.</p>
            <p>Second paragraph with more context.</p>
          </body>
        </html>
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, *_args: object, **_kwargs: object) -> None:
        return


def _start_fixture_server() -> tuple[HTTPServer, str]:
    server = HTTPServer(("127.0.0.1", 0), _ArticleHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}/article"


def build_settings() -> Settings:
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        context_api_token=os.environ.get("CONTEXT_API_TOKEN", "change-me"),
        version="0.0.0",
        git_sha="test",
    )


def test_ingest_urls_end_to_end(monkeypatch) -> None:
    server, url = _start_fixture_server()
    settings = build_settings()
    app = create_app(settings)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {settings.context_api_token}"}

    def fake_call_llm(prompt: str, *, model: str, api_key: str):
        return (
            {
                "summary": "Summary of the sample article.",
                "signals": [
                    {
                        "claim": "Key claim",
                        "why": "Reasoning based on the article.",
                        "supporting_snippet": "Signal snippet here.",
                        "cite": {"section_id": "s01"},
                    }
                ],
                "topics": ["ai"],
                "freshness_half_life_days": 30,
            },
            {"token_usage": {"total_tokens": 42}},
        )

    monkeypatch.setattr(enrich_module, "call_llm", fake_call_llm)

    ingest = client.post(
        "/v2/intel/ingest_urls",
        json={"urls": [url], "topics": ["ai"], "tags": ["test"], "enrich": True},
        headers=headers,
    )
    assert ingest.status_code == 200
    result = ingest.json()["results"][0]
    assert result["status"] == "queued"
    article_id = result["article_id"]

    engine = create_db_engine(settings.database_url)
    processed = run_once(engine, enrich=True)
    assert processed is True

    status = client.get(f"/v2/intel/articles/{article_id}", headers=headers)
    assert status.status_code == 200
    status_data = status.json()
    assert status_data["status"] in ("enriched", "partial")
    assert status_data["summary"]
    assert status_data["signals"]

    pack = client.post(
        "/v2/context/pack",
        json={"query": "Signal snippet", "max_items": 1},
        headers=headers,
    )
    assert pack.status_code == 200
    pack_data = pack.json()
    assert pack_data["pack"]["items"]

    server.shutdown()
