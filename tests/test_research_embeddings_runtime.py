from __future__ import annotations

import pytest

from app.research.embeddings import embed_texts, resolve_embedding_runtime


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
