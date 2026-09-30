from __future__ import annotations

import pytest
import httpx

from app.research import embeddings
from app.research.embeddings import embed_texts, resolve_embedding_runtime


@pytest.fixture(autouse=True)
def clear_cooldowns():
    embeddings._provider_cooldowns.clear()
    yield
    embeddings._provider_cooldowns.clear()


@pytest.mark.parametrize("status,code,error_type,exit_status", [
    (429, "credit_balance_exhausted", "insufficient_quota", 78),
    (429, "insufficient_quota", "insufficient_quota", 78),
    (401, "invalid_api_key", "invalid_request_error", 78),
    (403, "permission_denied", "invalid_request_error", 78),
    (429, "rate_limit_exceeded", "requests", 75),
    (500, "server_error", "server_error", 75),
    (502, "server_error", "server_error", 75),
    (503, "server_error", "server_error", 75),
    (504, "server_error", "server_error", 75),
])
def test_provider_error_is_actionable_and_redacted(monkeypatch, status, code, error_type, exit_status):
    response = httpx.Response(status, json={"error": {
        "code": code, "type": error_type, "message": "Never log this secret: sk-private",
    }}, request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"))
    monkeypatch.setattr(embeddings.httpx, "post", lambda *a, **kw: response)
    with pytest.raises(embeddings.EmbeddingProviderError) as exc:
        embed_texts(texts=["hello"], model="text-embedding-3-small", api_key="test-key")
    assert exc.value.exit_status == exit_status
    assert exc.value.code == code
    assert "sk-private" not in str(exc.value)


def test_provider_cooldown_expires_and_is_scoped_to_credential(monkeypatch):
    now = [100.0]
    calls = []
    monkeypatch.setattr(embeddings.time, "monotonic", lambda: now[0])
    def post(*args, **kwargs):
        calls.append(kwargs)
        return httpx.Response(429, json={"error": {"code": "credit_balance_exhausted"}})
    monkeypatch.setattr(embeddings.httpx, "post", post)
    for key in ["one", "one", "two"]:
        with pytest.raises(embeddings.EmbeddingProviderError):
            embed_texts(texts=["hello"], model="test", api_key=key)
    assert len(calls) == 2
    now[0] += 901
    with pytest.raises(embeddings.EmbeddingProviderError):
        embed_texts(texts=["hello"], model="test", api_key="one")
    assert len(calls) == 3


def test_successful_embeddings_are_unchanged(monkeypatch):
    response = httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}]},
                             request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"))
    monkeypatch.setattr(embeddings.httpx, "post", lambda *a, **kw: response)
    assert embed_texts(texts=["hello"], model="test", api_key="test") == [[0.1, 0.2]]


def test_resolve_embedding_runtime_reports_openai_mode() -> None:
    runtime = resolve_embedding_runtime(model="text-embedding-3-small", api_key="sk-test")
    assert runtime["mode"] == "openai"
    assert runtime["warning"] is None


def test_embed_texts_requires_api_key_for_real_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RESEARCH_ALLOW_HASH_EMBEDDINGS", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        embed_texts(texts=["hello world"], model="text-embedding-3-small", api_key="")
    assert "OPENAI_API_KEY is missing" in str(exc_info.value)


def test_embed_texts_allows_explicit_hash_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_ALLOW_HASH_EMBEDDINGS", "true")
    vectors = embed_texts(texts=["hello world"], model="text-embedding-3-small", api_key="")
    assert len(vectors) == 1
    assert len(vectors[0]) == 64
