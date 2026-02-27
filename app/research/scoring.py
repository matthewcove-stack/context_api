from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    a_list = [float(value) for value in a]
    b_list = [float(value) for value in b]
    if not a_list or not b_list or len(a_list) != len(b_list):
        return 0.0
    dot = sum(x * y for x, y in zip(a_list, b_list))
    norm_a = math.sqrt(sum(x * x for x in a_list))
    norm_b = math.sqrt(sum(y * y for y in b_list))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def recency_score(
    published_at: Optional[datetime],
    *,
    now: Optional[datetime] = None,
    half_life_days: float = 30.0,
) -> float:
    if not published_at:
        return 0.5
    now = now or datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    age_seconds = max((now - published_at).total_seconds(), 0.0)
    half_life_seconds = max(half_life_days * 24 * 3600, 1.0)
    return _clamp(0.5 ** (age_seconds / half_life_seconds))


def source_weight_score(source_weight: float) -> float:
    return _clamp(source_weight / 2.0)


def lexical_score(raw_lexical: float) -> float:
    return _clamp(raw_lexical)


def embedding_score(cosine: float) -> float:
    return _clamp((cosine + 1.0) / 2.0)


def blend_score(
    *,
    lexical: float,
    embedding: float,
    recency: float,
    source_weight: float,
    lexical_weight: float = 0.45,
    embedding_weight: float = 0.35,
    recency_weight: float = 0.15,
    source_weight_factor: float = 0.05,
) -> Dict[str, float]:
    total = (
        lexical_weight * lexical
        + embedding_weight * embedding
        + recency_weight * recency
        + source_weight_factor * source_weight
    )
    return {
        "total": _clamp(total),
        "lexical": _clamp(lexical),
        "embedding": _clamp(embedding),
        "recency": _clamp(recency),
        "source_weight": _clamp(source_weight),
    }
