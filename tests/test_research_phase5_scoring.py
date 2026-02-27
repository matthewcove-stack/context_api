from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.research.scoring import blend_score, cosine_similarity, recency_score


def test_cosine_similarity_for_identical_vectors() -> None:
    score = cosine_similarity([1.0, 0.0, 1.0], [1.0, 0.0, 1.0])
    assert score == pytest.approx(1.0)


def test_recency_score_decays_with_age() -> None:
    now = datetime.now(timezone.utc)
    fresh = recency_score(now, now=now, half_life_days=30)
    older = recency_score(now - timedelta(days=90), now=now, half_life_days=30)
    assert fresh > older


def test_blend_score_is_bounded() -> None:
    score = blend_score(lexical=0.9, embedding=0.8, recency=0.6, source_weight=0.5)
    assert 0.0 <= score["total"] <= 1.0
    assert score["lexical"] == 0.9
