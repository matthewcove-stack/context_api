from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def build_settings() -> Settings:
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        context_api_token=os.environ.get("CONTEXT_API_TOKEN", "change-me"),
        version="0.0.0",
        git_sha="test",
    )


def test_intel_context_pack_and_expansion() -> None:
    settings = build_settings()
    app = create_app(settings)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {settings.context_api_token}"}

    ingest = client.post("/v2/intel/ingest", json={"fixture_bundle": "default"}, headers=headers)
    assert ingest.status_code == 200
    ingested_ids = ingest.json()["ingested_article_ids"]
    assert len(ingested_ids) >= 2

    pack = client.post(
        "/v2/context/pack",
        json={"query": "lead times for AI accelerators", "max_items": 2},
        headers=headers,
    )
    assert pack.status_code == 200
    data = pack.json()
    items = data["pack"]["items"]
    assert items
    assert data["trace"]["trace_id"]
    assert isinstance(data["trace"]["retrieved_article_ids"], list)
    for item in items:
        assert item["signals"]
        assert item["citations"]
        assert len(item["signals"]) <= 3
        for signal in item["signals"]:
            assert signal["cite"]["article_id"]

    article_id = ingested_ids[0]
    outline = client.get(f"/v2/intel/articles/{article_id}/outline", headers=headers)
    assert outline.status_code == 200
    outline_items = outline.json()["outline"]
    assert outline_items

    section_ids = [section["section_id"] for section in outline_items[:2]]
    sections = client.post(
        f"/v2/intel/articles/{article_id}/sections",
        json={"section_ids": section_ids},
        headers=headers,
    )
    assert sections.status_code == 200
    sections_data = sections.json()["sections"]
    assert sections_data
    for section in sections_data:
        assert section["content"]

    chunks = client.post(
        f"/v2/intel/articles/{article_id}/chunks:search",
        json={"query": "lead times", "max_chunks": 2, "max_chars": 200},
        headers=headers,
    )
    assert chunks.status_code == 200
    chunks_data = chunks.json()["chunks"]
    assert len(chunks_data) <= 2
    for chunk in chunks_data:
        assert chunk["section_id"]
        assert chunk["snippet"]
