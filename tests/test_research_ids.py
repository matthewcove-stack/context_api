from __future__ import annotations

from app.research.ids import compute_chunk_id, compute_document_id, compute_source_id


def test_source_id_is_deterministic() -> None:
    first = compute_source_id(topic_key="ai_supply", kind="rss", base_url="https://example.com/feed?utm_source=x")
    second = compute_source_id(topic_key="ai_supply", kind="rss", base_url="https://example.com/feed")
    assert first == second


def test_document_id_is_deterministic() -> None:
    source_id = compute_source_id(topic_key="ai_supply", kind="rss", base_url="https://example.com/feed")
    first = compute_document_id(
        source_id=source_id,
        canonical_url="https://example.com/post?id=1&utm_campaign=abc",
        external_id="POST-1",
    )
    second = compute_document_id(
        source_id=source_id,
        canonical_url="https://example.com/post?id=1",
        external_id="post-1",
    )
    assert first == second


def test_chunk_id_is_deterministic_with_whitespace_variants() -> None:
    first = compute_chunk_id(document_id="doc_a", ordinal=1, content="hello   world")
    second = compute_chunk_id(document_id="doc_a", ordinal=1, content="hello world")
    assert first == second
