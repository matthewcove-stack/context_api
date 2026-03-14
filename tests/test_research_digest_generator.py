from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from app.research.digest_generator import (
    CandidateDocument,
    DraftDigestContent,
    DraftDigestItem,
    GeneratorRequest,
    OutputDigest,
    _fallback_engineering_takeaway,
    _is_low_value_candidate,
    _is_duplicate_takeaway,
    build_output_digest,
    choose_quote,
    compute_target_dates,
    determine_digest_window,
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
        issueSummary="Issue summary",
        topThings=["Thing one is important for builders.", "Thing two clarifies the operational implication."],
        topics=["agents"],
        coverageDays=1,
        generatedAt="2026-03-13T00:00:00+00:00",
        generatorModel="gpt-5.2",
        backfill=False,
        share={
            "title": "Digest",
            "description": "Issue summary",
            "canonicalPath": "/brief/2026-03-12",
        },
        primaryCta={
            "label": "Get new issues by email",
            "href": "mailto:hello@lambiclabs.com?subject=Subscribe%20me%20to%20Lambic%20AI%20Brief",
            "kind": "subscribe",
        },
        secondaryCta={
            "label": "Browse the archive",
            "href": "/brief",
            "kind": "archive",
        },
        items=[
            {
                "documentId": "doc-1",
                "headline": "Headline 1",
                "category": "agents",
                "whatHappened": "Something important happened in a way that matters operationally.",
                "sourceName": "Same Source",
                "sourceUrl": "https://example.com/1",
                "publishedAt": "2026-03-12T00:00:00+00:00",
                "tags": ["agents"],
                "whyItMatters": "Why it matters 1",
                "engineeringTakeaway": "Engineering takeaway 1",
            },
            {
                "documentId": "doc-2",
                "headline": "Headline 2",
                "category": "agents",
                "whatHappened": "A second important development landed and is easy to verify.",
                "sourceName": "Same Source",
                "sourceUrl": "https://example.com/2",
                "publishedAt": "2026-03-12T00:00:00+00:00",
                "tags": ["infra"],
                "whyItMatters": "Why it matters 2",
                "engineeringTakeaway": "Engineering takeaway 2",
            },
            {
                "documentId": "doc-3",
                "headline": "Headline 3",
                "category": "agents",
                "whatHappened": "A third item rounds out the issue and keeps the structure consistent.",
                "sourceName": "Same Source",
                "sourceUrl": "https://example.com/3",
                "publishedAt": "2026-03-12T00:00:00+00:00",
                "tags": ["benchmarks"],
                "whyItMatters": "Why it matters 3",
                "engineeringTakeaway": "Engineering takeaway 3",
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
        issue_summary="Agent systems are moving from prototypes to operational patterns.",
        top_things=[
            "Production-facing agent orchestration patterns are becoming more reusable.",
            "Teams can now copy concrete workflow designs instead of inventing them from scratch.",
        ],
        items=[
            DraftDigestItem(
                document_id="doc-1",
                headline="Agent systems are hardening",
                what_happened="Multi-agent systems are moving closer to production practice.",
                why_it_matters="This is relevant because teams can now reuse concrete orchestration patterns.",
                engineering_takeaway="Treat orchestration patterns as reusable product infrastructure, not one-off prompts.",
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
    assert digest.items[0].category == "evals"
    assert digest.items[0].engineeringTakeaway.startswith("Treat orchestration patterns")
    assert digest.items[0].tags == ["evals", "agents"]
    assert digest.issueSummary == "Agent systems are moving from prototypes to operational patterns."
    assert digest.topThings[0].startswith("Production-facing agent orchestration")
    assert digest.share is not None
    assert digest.share.canonicalPath == "/brief/2026-03-12"
    assert digest.primaryCta is not None
    assert digest.primaryCta.kind == "subscribe"
    assert digest.secondaryCta is not None
    assert digest.secondaryCta.href == "/brief"


def test_determine_digest_window_rolls_forward_unpublished_gap() -> None:
    request = GeneratorRequest(
        mode="daily",
        target_date=date(2026, 3, 12),
        start_date=None,
        end_date=None,
        force=False,
        dry_run=False,
    )

    window_start, window_end = determine_digest_window(
        target_date=date(2026, 3, 12),
        existing_dates={date(2026, 3, 10)},
        request=request,
    )

    assert window_start.isoformat() == "2026-03-11T00:00:00+00:00"
    assert window_end.isoformat() == "2026-03-13T00:00:00+00:00"


def test_low_value_candidate_filter_rejects_generic_navigation_pages() -> None:
    candidate = _candidate(
        document_id="doc-generic",
        source_name="Source A",
        title="Research - Google DeepMind",
        url="https://deepmind.google/research/",
        score=1.0,
    )

    assert _is_low_value_candidate(candidate) is True


def test_low_value_candidate_filter_rejects_pagination_and_landing_pages() -> None:
    page_candidate = _candidate(
        document_id="doc-page",
        source_name="LangChain Blog",
        title="Agent patterns roundup",
        url="https://blog.langchain.dev/page/2/",
        score=1.0,
    )
    landing_candidate = _candidate(
        document_id="doc-landing",
        source_name="LlamaIndex Blog",
        title="OCR comparison",
        url="https://landing.llamaindex.ai/llamaparsevsllms",
        score=1.0,
    )

    assert _is_low_value_candidate(page_candidate) is True
    assert _is_low_value_candidate(landing_candidate) is True


def test_candidate_builder_should_prefer_effective_timestamp_when_raw_published_at_is_stale() -> None:
    published_at = datetime(2024, 5, 31, 0, 0, tzinfo=timezone.utc)
    effective_at = datetime(2026, 3, 8, 0, 0, tzinfo=timezone.utc)

    chosen = effective_at or published_at

    assert chosen.isoformat() == "2026-03-08T00:00:00+00:00"


def test_stale_published_at_should_be_treated_as_ineligible_for_daily_digest_window() -> None:
    published_at = datetime(2024, 5, 31, 0, 0, tzinfo=timezone.utc)
    effective_at = datetime(2026, 3, 8, 0, 0, tzinfo=timezone.utc)

    is_stale = published_at < effective_at - timedelta(days=45)

    assert is_stale is True


def test_duplicate_takeaway_detection_and_fallback() -> None:
    why_it_matters = "Agent quality failures are often multi-turn and tool-dependent, so ad hoc spot checks miss regressions."
    engineering_takeaway = "Agent quality failures are often multi-turn and tool-dependent, so ad hoc spot checks miss regressions."
    candidate = _candidate(
        document_id="doc-fallback",
        source_name="Source A",
        title="Benchmark contamination in web evals",
        url="https://example.com/fallback",
        score=1.0,
    )
    candidate.summary_short = "Benchmark contamination is becoming a practical issue in browsing evaluations."

    assert _is_duplicate_takeaway(why_it_matters, engineering_takeaway) is True
    assert _fallback_engineering_takeaway("evals", candidate).startswith("Isolate benchmark corpora")


def test_choose_quote_rejects_unfinished_or_unbalanced_quotes() -> None:
    candidate = _candidate(
        document_id="doc-quote",
        source_name="Source A",
        title="Quoted story",
        url="https://example.com/story",
        score=1.0,
    )
    candidate.notable_quotes = [
        {"speaker": "", "text": 'The Safety Net": Acting somewhat like a unit-testing layer, runs the agent against curated'}
    ]

    assert choose_quote(candidate) is None
