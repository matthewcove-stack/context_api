from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.intel.enrich import EnrichmentOutput
from app.storage.db import canonicalize_url, compute_article_id


def test_canonicalize_url_strips_tracking() -> None:
    url = "https://example.com/path/?utm_source=newsletter&b=2#section"
    assert canonicalize_url(url) == "https://example.com/path?b=2"


def test_article_id_is_stable() -> None:
    canonical = "https://example.com/path?b=2"
    assert compute_article_id(canonical) == compute_article_id(canonical)


def test_enrichment_schema_requires_cite_pointer() -> None:
    payload = {
        "summary": "Summary",
        "signals": [
            {
                "claim": "Claim",
                "why": "Why",
                "supporting_snippet": "Snippet",
            }
        ],
        "topics": ["ai"],
    }
    with pytest.raises(ValidationError):
        EnrichmentOutput.model_validate(payload)
