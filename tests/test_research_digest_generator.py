from __future__ import annotations

from datetime import date, datetime, timezone
from app.research.digest_generator import (
    CandidateDocument,
    DraftDigestContent,
    DraftDigestItem,
    GeneratorRequest,
    OutputDigest,
    build_output_digest,
    compute_target_dates,
    quality_gate_digest,
    select_distinct_candidates,
)


def _candidate(
    *,
    document_id: str,
    source_name: str,
    title: str,
    url: str,
    score: float,
    topic_tags: list[str] | None = None,
) -> CandidateDocument:
    return CandidateDocument(
        document_id=document_id,
        source_id=f"src-{document_id}",
        source_name=source_name,
        title=title,
        canonical_url=url,
        published_at=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc),
        summary_short=f"Summary for {document_id}",
        why_it_matters=f"Why {document_id} matters",
        metrics=[],
        notable_quotes=[],
        topic_tags=topic_tags or ["agents"],
        decision_domains=["ai_product_engineering"],
        content_type="benchmark",
        publisher_type="vendor",
        source_class="external_primary",
        document_signal_score=score,
        novelty_score=0.0,
        evidence_density_score=0.0,
    )


def test_compute_target_dates_skips_existing_backfill_dates() -> None:
    request = GeneratorRequest(
        mode="backfill-missing",
        target_date=None,
        start_date=date(2026, 3, 10),
        end_date=date(2026, 3, 13),
        force=False,
        dry_run=False,
    )

    result = compute_target_dates(
        settings=type("Settings", (), {"backfill_start_date": None, "backfill_end_date": None})(),
        request=request,
        earliest_date=date(2026, 3, 9),
        existing_dates={date(2026, 3, 11), date(2026, 3, 13)},
    )

    assert result == [date(2026, 3, 10), date(2026, 3, 12)]


def test_select_distinct_candidates_limits_duplicates_and_sources() -> None:
    candidates = [
        _candidate(document_id="doc-1", source_name="Source A", title="Same Story", url="https://a.example.com/1", score=2.0),
        _candidate(document_id="doc-2", source_name="Source A", title="Same Story", url="https://a.example.com/2", score=1.9),
        _candidate(document_id="doc-3", source_name="Source A", title="Different Story", url="https://a.example.com/3", score=1.8),
        _candidate(document_id="doc-4", source_name="Source B", title="Another Story", url="https://b.example.com/1", score=1.7),
        _candidate(document_id="doc-5", source_name="Source C", title="Third Story", url="https://c.example.com/1", score=1.6),
    ]

    selected = select_distinct_candidates(candidates, max_items=4, source_limit_per_digest=1)

    assert [candidate.document_id for candidate in selected] == ["doc-1", "doc-4", "doc-5"]


def test_quality_gate_rejects_low_diversity_digest() -> None:
    digest = OutputDigest(
        date="2026-03-12",
        windowStart="2026-03-12T00:00:00+00:00",
        windowEnd="2026-03-13T00:00:00+00:00",
        title="Digest",
        intro="Intro",
        summary="Summary",
        generatedAt="2026-03-13T00:00:00+00:00",
        generatorModel="gpt-5.2",
        backfill=False,
        items=[
            {
                "documentId": "doc-1",
                "headline": "Headline 1",
                "summary": "Summary 1",
                "sourceName": "Same Source",
                "sourceUrl": "https://example.com/1",
                "publishedAt": "2026-03-12T00:00:00+00:00",
                "tags": ["agents"],
                "whyItMatters": "Why it matters 1",
            },
            {
                "documentId": "doc-2",
                "headline": "Headline 2",
                "summary": "Summary 2",
                "sourceName": "Same Source",
                "sourceUrl": "https://example.com/2",
                "publishedAt": "2026-03-12T00:00:00+00:00",
                "tags": ["infra"],
                "whyItMatters": "Why it matters 2",
            },
            {
                "documentId": "doc-3",
                "headline": "Headline 3",
                "summary": "Summary 3",
                "sourceName": "Same Source",
                "sourceUrl": "https://example.com/3",
                "publishedAt": "2026-03-12T00:00:00+00:00",
                "tags": ["benchmarks"],
                "whyItMatters": "Why it matters 3",
            },
        ],
    )

    assert quality_gate_digest(digest, min_items=3) == "insufficient source diversity"


def test_build_output_digest_preserves_grounded_metadata() -> None:
    candidate = _candidate(
        document_id="doc-1",
        source_name="Source A",
        title="Title",
        url="https://example.com/article",
        score=1.5,
        topic_tags=["agents", "security"],
    )
    draft = DraftDigestContent(
        title="Daily AI Research Digest",
        intro="A strong day for agent infrastructure.",
        summary="The biggest signal was production-facing agent systems.",
        items=[
            DraftDigestItem(
                document_id="doc-1",
                headline="Agent systems are hardening",
                summary="Multi-agent systems are moving closer to production practice.",
                why_it_matters="This is relevant because teams can now reuse concrete orchestration patterns.",
            )
        ],
    )

    digest = build_output_digest(
        settings=type("Settings", (), {"model": "gpt-5.2"})(),
        target_date=date(2026, 3, 12),
        backfill=False,
        window_start=datetime(2026, 3, 12, 0, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 3, 13, 0, 0, tzinfo=timezone.utc),
        draft=draft,
        candidates=[candidate],
    )

    assert digest.items[0].documentId == "doc-1"
    assert digest.items[0].sourceName == "Source A"
    assert digest.items[0].sourceUrl == "https://example.com/article"
    assert digest.items[0].tags == ["agents", "security"]
