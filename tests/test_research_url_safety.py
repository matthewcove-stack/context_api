from __future__ import annotations

from app.research.url_safety import is_private_source_url, source_url_allowed


def test_private_source_url_detection() -> None:
    assert is_private_source_url("http://127.0.0.1:8765/feed") is True
    assert is_private_source_url("http://localhost/feed") is True
    assert is_private_source_url("http://10.0.0.4/feed") is True
    assert is_private_source_url("https://huggingface.co/blog/feed.xml") is False


def test_private_source_urls_require_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("RESEARCH_ALLOW_PRIVATE_SOURCE_URLS", raising=False)
    assert source_url_allowed("http://127.0.0.1/feed") is False
    monkeypatch.setenv("RESEARCH_ALLOW_PRIVATE_SOURCE_URLS", "true")
    assert source_url_allowed("http://127.0.0.1/feed") is True
