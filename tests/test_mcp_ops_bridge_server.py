from __future__ import annotations

import pytest

from app.mcp_bridge_ops.client import OpsBridgeClientError
from app.mcp_bridge_ops.server import OpsBridgeRuntimeSettings, ingest_status, ops_summary, sources_bootstrap


class _FakeClient:
    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return None

    def sources_bootstrap(self, payload):
        return type(
            "Resp",
            (),
            {"model_dump": lambda self, mode="json": {"topic_key": payload.topic_key, "ingest": {"triggered": False}}},
        )()

    def ingest_status(self, run_id: str):
        return type(
            "Resp",
            (),
            {"model_dump": lambda self, mode="json": {"run_id": run_id, "status": "queued", "counters": {}, "errors": []}},
        )()

    def ops_summary(self, topic_key: str):
        return type(
            "Resp",
            (),
            {
                "model_dump": lambda self, mode="json": {
                    "topic_key": topic_key,
                    "sources_total": 0,
                    "sources_enabled": 0,
                    "sources_in_cooldown": 0,
                    "documents_total": 0,
                    "documents_embedded": 0,
                    "documents_failed": 0,
                    "runs_open": 0,
                    "runs_failed_24h": 0,
                    "run_failure_rate_24h": 0.0,
                    "retrieval_queries_24h": 0,
                    "retrieval_errors_24h": 0,
                }
            },
        )()


def test_ops_bridge_tools_happy_path(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.mcp_bridge_ops.server._load_settings",
        lambda: OpsBridgeRuntimeSettings(
            context_api_base_url="http://context-api.local",
            context_api_token="token",
            timeout_s=10.0,
            transport="stdio",
        ),
    )
    monkeypatch.setattr("app.mcp_bridge_ops.server.ContextApiOpsBridgeClient", _FakeClient)

    bootstrap = sources_bootstrap(
        topic_key="ai_supply",
        suggestions=[{"kind": "rss", "name": "Feed", "base_url": "https://example.com/feed"}],
    )
    assert bootstrap["topic_key"] == "ai_supply"

    status = ingest_status("run_1")
    assert status["run_id"] == "run_1"

    summary = ops_summary("ai_supply")
    assert summary["topic_key"] == "ai_supply"


def test_ops_bridge_tool_maps_client_failure(monkeypatch) -> None:
    class _FailingClient(_FakeClient):
        def sources_bootstrap(self, payload):
            raise OpsBridgeClientError("bootstrap failed")

    monkeypatch.setattr(
        "app.mcp_bridge_ops.server._load_settings",
        lambda: OpsBridgeRuntimeSettings(
            context_api_base_url="http://context-api.local",
            context_api_token="token",
            timeout_s=10.0,
            transport="stdio",
        ),
    )
    monkeypatch.setattr("app.mcp_bridge_ops.server.ContextApiOpsBridgeClient", _FailingClient)

    with pytest.raises(ValueError) as exc_info:
        sources_bootstrap(
            topic_key="ai_supply",
            suggestions=[{"kind": "rss", "name": "Feed", "base_url": "https://example.com/feed"}],
        )
    assert "bootstrap failed" in str(exc_info.value)
