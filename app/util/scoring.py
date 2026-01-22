from __future__ import annotations

from difflib import SequenceMatcher


def score_match(query: str, text: str) -> float:
    if not query or not text:
        return 0.0
    normalized_query = query.strip().lower()
    normalized_text = text.strip().lower()
    if not normalized_query or not normalized_text:
        return 0.0
    if normalized_query == normalized_text:
        return 1.0
    if normalized_text.startswith(normalized_query):
        return 0.95
    if normalized_query in normalized_text:
        return 0.8
    ratio = SequenceMatcher(None, normalized_query, normalized_text).ratio()
    return float(ratio)
