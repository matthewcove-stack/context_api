from __future__ import annotations

import json

import httpx
import pytest

from app.mcp_bridge.client import BridgeClientError, ContextApiBridgeClient
from app.research.contracts import ResearchChunkSearchRequest, ResearchContextPackRequest


def test_bridge_client_search_posts_expected_payload_and_headers() -> None:
    captured = {"auth": "", "body": {}, "path": ""}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization", "")
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "pack": {
                    "items": [
                        {
                            "document_id": "doc_1",
                            "source_id": "src_1",
                            "title": "GPU Supply Update",
                            "canonical_url": "https://example.com/doc-1",
                            "published_at": None,
                            "summary": "Supply constraints easing in Q3.",
                            "signals": [
                                {
                                    "claim": "Supply constraints easing in Q3.",
                                    "why": "Hybrid relevance from lexical and embedding scoring.",
                                    "cite": {"document_id": "doc_1", "chunk_id": "chk_1"},
                                }
                            ],
                            "citations": [{"document_id": "doc_1", "chunk_id": "chk_1"}],
                            "score_breakdown": {
                                "total": 0.91,
                                "lexical": 0.8,
                                "embedding": 0.9,
                                "recency": 0.6,
                                "source_weight": 1.0,
                            },
                        }
                    ]
                },
                "retrieval_confidence": "high",
                "next_action": "proceed",
                "trace": {
                    "trace_id": "trace_1",
                    "retrieved_document_ids": ["doc_1"],
                    "timing_ms": {"total": 120},
                },
            },
        )

    transport = httpx.MockTransport(handler)
    payload = ResearchContextPackRequest(query="gpu supply", topic_key="ai_supply")
    with ContextApiBridgeClient(
        base_url="http://context-api.local",
        token="test-token",
        transport=transport,
    ) as client:
        response = client.search(payload)

    assert captured["auth"] == "Bearer test-token"
    assert captured["path"] == "/v2/research/context/pack"
    assert captured["body"]["query"] == "gpu supply"
    assert captured["body"]["topic_key"] == "ai_supply"
    assert response.trace.trace_id == "trace_1"
    assert response.pack.items[0].document_id == "doc_1"


def test_bridge_client_fetch_raises_bridge_error_on_http_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Document not found"})

    transport = httpx.MockTransport(handler)
    payload = ResearchChunkSearchRequest(query="latency", max_chunks=3, max_chars=200)

    with ContextApiBridgeClient(
        base_url="http://context-api.local",
        token="test-token",
        transport=transport,
    ) as client:
        with pytest.raises(BridgeClientError) as exc_info:
            client.fetch_document_chunks(document_id="missing-doc", payload=payload)

    assert "Document not found" in str(exc_info.value)

