from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Literal, Optional, Sequence

from pydantic import BaseModel, Field

from app.research.digest_generator import OutputDigest, OutputDigestCta, OutputDigestShare, parse_date


DistributionMode = Literal["assets", "weekly", "all"]


class DistributionAssetEmail(BaseModel):
    subject: str
    preview: str
    body: str


class DistributionAssetBundle(BaseModel):
    date: str
    issuePath: str
    generatedAt: str
    share: OutputDigestShare
    topTakeaways: List[str] = Field(default_factory=list)
    founderLinkedInPost: str
    companyLinkedInPost: str
    shortSocialVariants: List[str] = Field(default_factory=list)
    emailTeaser: DistributionAssetEmail


class WeeklyDigestIssue(BaseModel):
    date: str
    title: str
    issueSummary: str
    href: str
    topics: List[str] = Field(default_factory=list)


class WeeklyDigest(BaseModel):
    weekId: str
    weekStart: str
    weekEnd: str
    generatedAt: str
    title: str
    intro: str
    issueSummary: str
    topThemes: List[str] = Field(default_factory=list)
    topTakeaways: List[str] = Field(default_factory=list)
    issueDates: List[str] = Field(default_factory=list)
    issues: List[WeeklyDigestIssue] = Field(default_factory=list)
    share: OutputDigestShare
    primaryCta: OutputDigestCta
    secondaryCta: OutputDigestCta


@dataclass(frozen=True)
class DistributionGeneratorSettings:
    output_repo: Path
    digest_dir: Path
    assets_dir: Path
    weekly_dir: Path


class DistributionGenerationError(RuntimeError):
    pass


def load_settings() -> DistributionGeneratorSettings:
    output_repo = Path(
        os.getenv("DAILY_DIGEST_OUTPUT_REPO", r"C:\Users\Matth\Documents\workspace\lambic_labs_website")
    ).expanduser()
    digest_dir = output_repo / Path(os.getenv("DAILY_DIGEST_WEBSITE_CONTENT_DIR", "apps/web/content/research-digests"))
    assets_dir = output_repo / Path(
        os.getenv("DAILY_DIGEST_ASSETS_CONTENT_DIR", "apps/web/content/research-digest-assets")
    )
    weekly_dir = output_repo / Path(
        os.getenv("DAILY_DIGEST_WEEKLY_CONTENT_DIR", "apps/web/content/research-weekly")
    )
    return DistributionGeneratorSettings(
        output_repo=output_repo,
        digest_dir=digest_dir,
        assets_dir=assets_dir,
        weekly_dir=weekly_dir,
    )


def parse_request(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Lambic AI Brief distribution artifacts.")
    parser.add_argument("--mode", choices=["assets", "weekly", "all"], default="all")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def _normalize_sentence(value: str) -> str:
    return " ".join((value or "").strip().split())


def _trim_text(value: str, limit: int) -> str:
    compact = _normalize_sentence(value)
    if len(compact) <= limit:
        return compact
    trimmed = compact[: max(limit - 1, 1)].rsplit(" ", 1)[0].strip()
    return f"{trimmed}…"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def render_json(payload: BaseModel) -> str:
    return json.dumps(payload.model_dump(mode="json", exclude_none=True), indent=2, ensure_ascii=True) + "\n"


def load_daily_digests(settings: DistributionGeneratorSettings) -> List[OutputDigest]:
    if not settings.digest_dir.exists():
        return []
    digests: List[OutputDigest] = []
    for path in sorted(settings.digest_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        digests.append(OutputDigest.model_validate(payload))
    digests.sort(key=lambda item: item.date, reverse=True)
    return digests


def build_distribution_asset(digest: OutputDigest) -> DistributionAssetBundle:
    share = digest.share or OutputDigestShare(
        title=f"{digest.title} | Lambic AI Brief",
        description=digest.issueSummary,
        canonicalPath=f"/brief/{digest.date}",
    )
    issue_url = f"https://lambiclabs.com{share.canonicalPath}"
    takeaways = list(dict.fromkeys([point for point in digest.topThings[:3] if point]))
    headline = _trim_text(digest.issueSummary, 240)
    founder_post = "\n\n".join(
        [
            f"{digest.title}",
            headline,
            "Three things worth carrying forward:",
            *[f"- {_trim_text(point, 180)}" for point in takeaways[:3]],
            issue_url,
        ]
    )
    company_post = "\n\n".join(
        [
            f"New Lambic AI Brief: {digest.title}",
            _trim_text(digest.summary, 280),
            "Read the full issue:",
            issue_url,
        ]
    )
    short_social = [
        _trim_text(f"{digest.title}: {takeaway} {issue_url}", 280)
        for takeaway in takeaways[:3]
    ]
    return DistributionAssetBundle(
        date=digest.date,
        issuePath=share.canonicalPath,
        generatedAt=datetime.now(timezone.utc).isoformat(),
        share=share,
        topTakeaways=takeaways,
        founderLinkedInPost=founder_post,
        companyLinkedInPost=company_post,
        shortSocialVariants=short_social,
        emailTeaser=DistributionAssetEmail(
            subject=f"Lambic AI Brief: {digest.title}",
            preview=_trim_text(digest.issueSummary, 140),
            body="\n\n".join(
                [
                    _trim_text(digest.summary, 280),
                    *(f"- {_trim_text(point, 180)}" for point in takeaways[:3]),
                    issue_url,
                ]
            ),
        ),
    )


def write_distribution_asset(settings: DistributionGeneratorSettings, asset: DistributionAssetBundle) -> Path:
    ensure_dir(settings.assets_dir)
    filepath = settings.assets_dir / f"{asset.date}.json"
    filepath.write_text(render_json(asset), encoding="utf-8")
    return filepath


def _week_key(value: str) -> tuple[int, int]:
    parsed = parse_date(value)
    iso_year, iso_week, _ = parsed.isocalendar()
    return iso_year, iso_week


def _week_id(value: date) -> str:
    iso_year, iso_week, _ = value.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _week_bounds(value: date) -> tuple[date, date]:
    week_start = value - timedelta(days=value.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def build_weekly_digest(week_id: str, digests: Sequence[OutputDigest]) -> WeeklyDigest:
    ordered = sorted(digests, key=lambda item: item.date, reverse=True)
    newest = ordered[0]
    first_date = parse_date(ordered[-1].date)
    week_start, week_end = _week_bounds(first_date)
    topic_counts: Dict[str, int] = {}
    takeaways: List[str] = []
    for digest in ordered:
        for topic in digest.topics:
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
        for point in digest.topThings:
            normalized = _normalize_sentence(point)
            if normalized and normalized not in takeaways:
                takeaways.append(normalized)
    top_themes = [topic for topic, _ in sorted(topic_counts.items(), key=lambda item: (-item[1], item[0]))[:4]]
    summary_parts = [_trim_text(digest.issueSummary, 140) for digest in ordered[:3]]
    if top_themes:
        title = f"This week in AI engineering: {', '.join(top_themes[:3])}"
    else:
        title = f"Lambic AI Brief Weekly - {week_id}"
    intro = _trim_text(
        " ".join(
            [
                f"This weekly Lambic AI Brief rounds up the clearest practical signals from {len(ordered)} daily issues.",
                f"The main themes were {', '.join(top_themes[:3])}." if top_themes else "",
            ]
        ).strip(),
        320,
    )
    issue_summary = _trim_text(" ".join(part for part in summary_parts if part), 220)
    canonical_path = f"/brief/weekly/{week_id}"
    return WeeklyDigest(
        weekId=week_id,
        weekStart=week_start.isoformat(),
        weekEnd=week_end.isoformat(),
        generatedAt=datetime.now(timezone.utc).isoformat(),
        title=title,
        intro=intro or f"Weekly roundup for {week_id}.",
        issueSummary=issue_summary or newest.issueSummary,
        topThemes=top_themes,
        topTakeaways=takeaways[:5],
        issueDates=[digest.date for digest in ordered],
        issues=[
            WeeklyDigestIssue(
                date=digest.date,
                title=digest.title,
                issueSummary=digest.issueSummary,
                href=f"/brief/{digest.date}",
                topics=digest.topics,
            )
            for digest in ordered
        ],
        share=OutputDigestShare(
            title=f"{title} | Lambic AI Brief",
            description=issue_summary or newest.issueSummary,
            canonicalPath=canonical_path,
        ),
        primaryCta=OutputDigestCta(
            label="Get the next weekly roundup",
            href="/brief/subscribe",
            kind="subscribe",
        ),
        secondaryCta=OutputDigestCta(
            label="Browse daily issues",
            href="/brief",
            kind="archive",
        ),
    )


def build_weekly_digests(digests: Sequence[OutputDigest]) -> List[WeeklyDigest]:
    grouped: Dict[tuple[int, int], List[OutputDigest]] = {}
    for digest in digests:
        grouped.setdefault(_week_key(digest.date), []).append(digest)
    weekly: List[WeeklyDigest] = []
    for group in sorted(grouped.keys(), reverse=True):
        week_digests = grouped[group]
        if len(week_digests) < 2:
            continue
        week_id = _week_id(parse_date(week_digests[0].date))
        weekly.append(build_weekly_digest(week_id, week_digests))
    return weekly


def write_weekly_digest(settings: DistributionGeneratorSettings, digest: WeeklyDigest) -> Path:
    ensure_dir(settings.weekly_dir)
    filepath = settings.weekly_dir / f"{digest.weekId}.json"
    filepath.write_text(render_json(digest), encoding="utf-8")
    return filepath


def execute_generation(
    *,
    settings: DistributionGeneratorSettings,
    mode: DistributionMode,
    dry_run: bool,
) -> dict:
    digests = load_daily_digests(settings)
    if not digests:
        raise DistributionGenerationError("No daily digests found to derive distribution artifacts from")
    generated_assets: List[str] = []
    generated_weeklies: List[str] = []
    if mode in {"assets", "all"}:
        for digest in digests:
            asset = build_distribution_asset(digest)
            if not dry_run:
                write_distribution_asset(settings, asset)
            generated_assets.append(asset.date)
    if mode in {"weekly", "all"}:
        weekly_digests = build_weekly_digests(digests)
        for digest in weekly_digests:
            if not dry_run:
                write_weekly_digest(settings, digest)
            generated_weeklies.append(digest.weekId)
    return {
        "mode": mode,
        "daily_digest_count": len(digests),
        "generated_assets": generated_assets,
        "generated_weeklies": generated_weeklies,
    }
