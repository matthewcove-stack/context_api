from __future__ import annotations

from pathlib import Path

from app.research.digest_generator import OutputDigest, OutputDigestItem
from app.research.distribution_generator import (
    DistributionGeneratorSettings,
    build_distribution_asset,
    build_weekly_digests,
    execute_generation,
    render_json,
)


def _digest(date: str, *, title: str, issue_summary: str, topics: list[str], top_things: list[str]) -> OutputDigest:
    return OutputDigest(
        date=date,
        windowStart=f"{date}T00:00:00+00:00",
        windowEnd=f"{date}T23:59:59+00:00",
        title=title,
        intro="Intro copy for the issue.",
        summary="Summary copy for the issue that is long enough for validation.",
        issueSummary=issue_summary,
        topThings=top_things,
        topics=topics,
        coverageDays=1,
        generatedAt="2026-03-14T00:00:00+00:00",
        generatorModel="gpt-5.2",
        backfill=False,
        items=[
            OutputDigestItem(
                documentId=f"doc-{date}",
                headline="Item headline",
                category="tooling",
                whatHappened="A relevant change happened and the summary is complete.",
                sourceName="Source A",
                sourceUrl="https://example.com/source",
                publishedAt=f"{date}T12:00:00+00:00",
                tags=topics,
                whyItMatters="This matters because teams need practical implementation signals.",
                engineeringTakeaway="Turn the lesson into a concrete engineering decision or release gate.",
            )
        ],
    )


def test_build_distribution_asset_uses_digest_share_defaults() -> None:
    digest = _digest(
        "2026-03-12",
        title="Agent orchestration hardens",
        issue_summary="Routing and verification loops are becoming primary engineering levers.",
        topics=["agents", "evals"],
        top_things=[
            "Treat agent quality as an orchestration problem rather than a prompt-only problem.",
            "Verification loops are becoming part of the baseline system design.",
        ],
    )

    asset = build_distribution_asset(digest)

    assert asset.date == "2026-03-12"
    assert asset.issuePath == "/brief/2026-03-12"
    assert asset.share.canonicalPath == "/brief/2026-03-12"
    assert asset.topTakeaways[0].startswith("Treat agent quality")
    assert "https://lambiclabs.com/brief/2026-03-12" in asset.founderLinkedInPost


def test_build_weekly_digests_groups_by_iso_week_and_keeps_topics() -> None:
    digests = [
        _digest(
            "2026-03-12",
            title="Issue A",
            issue_summary="Issue A summary.",
            topics=["agents", "tooling"],
            top_things=["A practical point from issue A."],
        ),
        _digest(
            "2026-03-11",
            title="Issue B",
            issue_summary="Issue B summary.",
            topics=["agents", "infrastructure"],
            top_things=["A practical point from issue B."],
        ),
    ]

    weekly = build_weekly_digests(digests)

    assert len(weekly) == 1
    assert weekly[0].weekId == "2026-W11"
    assert weekly[0].issues[0].date == "2026-03-12"
    assert "agents" in weekly[0].topThemes
    assert weekly[0].share.canonicalPath == "/brief/weekly/2026-W11"
    assert weekly[0].editorial.editorialFrame


def test_execute_generation_refreshes_outputs_and_removes_stale_files(tmp_path: Path) -> None:
    output_repo = tmp_path / "website"
    digest_dir = output_repo / "apps" / "web" / "content" / "research-digests"
    assets_dir = output_repo / "apps" / "web" / "content" / "research-digest-assets"
    weekly_dir = output_repo / "apps" / "web" / "content" / "research-weekly"
    digest_dir.mkdir(parents=True)
    assets_dir.mkdir(parents=True)
    weekly_dir.mkdir(parents=True)

    digests = [
        _digest(
            "2026-03-12",
            title="Issue A",
            issue_summary="Issue A summary.",
            topics=["agents", "tooling"],
            top_things=["A practical point from issue A."],
        ),
        _digest(
            "2026-03-11",
            title="Issue B",
            issue_summary="Issue B summary.",
            topics=["agents", "infrastructure"],
            top_things=["A practical point from issue B."],
        ),
    ]
    for digest in digests:
        (digest_dir / f"{digest.date}.json").write_text(render_json(digest), encoding="utf-8")
    (assets_dir / "stale.json").write_text("{}", encoding="utf-8")
    (weekly_dir / "stale.json").write_text("{}", encoding="utf-8")

    report = execute_generation(
        settings=DistributionGeneratorSettings(
            output_repo=output_repo,
            digest_dir=digest_dir,
            assets_dir=assets_dir,
            weekly_dir=weekly_dir,
        ),
        mode="all",
        dry_run=False,
    )

    assert sorted(report["generated_assets"]) == ["2026-03-11", "2026-03-12"]
    assert report["generated_weeklies"] == ["2026-W11"]
    assert not (assets_dir / "stale.json").exists()
    assert not (weekly_dir / "stale.json").exists()
