from __future__ import annotations

import json

import httpx
import pytest

from app.mcp_bridge_ops.client import ContextApiOpsBridgeClient, OpsBridgeClientError
from app.research.contracts import ResearchBootstrapRequest


def test_ops_bridge_client_bootstrap_posts_expected_payload_and_headers() -> None:
    captured = {"auth": "", "body": {}, "path": ""}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization", "")
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "topic_key": "ai_supply",
                "summary": {
                    "received": 1,
                    "valid": 1,
                    "invalid": 0,
                    "created": 1,
                    "updated": 0,
                    "skipped_duplicate": 0,
                },
                "results": [{"index": 0, "status": "created", "source_id": "src_1"}],
                "ingest": {"triggered": True, "run_id": "run_1", "status": "queued"},
            },
        )

    payload = ResearchBootstrapRequest(
        topic_key="ai_supply",
        suggestions=[{"kind": "rss", "name": "Feed", "base_url": "https://example.com/feed"}],
    )
    with ContextApiOpsBridgeClient(
        base_url="http://context-api.local",
        token="test-token",
        transport=httpx.MockTransport(handler),
    ) as client:
        response = client.sources_bootstrap(payload)

    assert captured["auth"] == "Bearer test-token"
    assert captured["path"] == "/v2/research/sources/bootstrap"
    assert captured["body"]["topic_key"] == "ai_supply"
    assert response.summary.created == 1
    assert response.ingest.run_id == "run_1"


def test_ops_bridge_client_ingest_status_raises_on_http_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Run not found"})

    with ContextApiOpsBridgeClient(
        base_url="http://context-api.local",
        token="test-token",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(OpsBridgeClientError) as exc_info:
            client.ingest_status("missing-run")
    assert "Run not found" in str(exc_info.value)
