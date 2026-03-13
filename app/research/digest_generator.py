from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.storage.db import create_db_engine, search_research_document_chunks


RunMode = Literal["daily", "backfill-range", "backfill-missing"]

ANNOUNCEMENT_PATTERNS = (
    "partner network",
    "office in",
    "office",
    "funding",
    "invests",
    "announces",
    "announcing",
    "launches",
    "launching",
)

PRIMARY_SOURCE_BOOST = {
    "external_primary": 1.1,
    "external_commentary": -0.2,
    "internal_primary": 0.8,
}

CONTENT_TYPE_BOOST = {
    "benchmark": 1.0,
    "paper": 0.9,
    "company_blog": 0.0,
    "guide": -0.2,
}


@dataclass(frozen=True)
class DigestGeneratorSettings:
    topic_key: str
    model: str
    openai_api_key: str
    context_api_token: str
    database_url: str
    output_repo: Path
    website_content_dir: Path
    author_name: str
    git_remote: str
    git_branch: str
    backfill_start_date: Optional[date]
    backfill_end_date: Optional[date]
    max_items: int
    min_items: int
    lookback_hours: int
    source_limit_per_digest: int
    validate_build: bool

    @property
    def digest_dir(self) -> Path:
        return self.output_repo / self.website_content_dir


@dataclass(frozen=True)
class GeneratorRequest:
    mode: RunMode
    target_date: Optional[date]
    start_date: Optional[date]
    end_date: Optional[date]
    force: bool
    dry_run: bool


@dataclass
class CandidateDocument:
    document_id: str
    source_id: str
    source_name: str
    title: str
    canonical_url: str
    published_at: datetime
    summary_short: str
    why_it_matters: str
    metrics: List[Dict[str, Any]]
    notable_quotes: List[Dict[str, Any]]
    topic_tags: List[str]
    decision_domains: List[str]
    content_type: str
    publisher_type: str
    source_class: str
    document_signal_score: float
    novelty_score: float
    evidence_density_score: float
    candidate_score: float = 0.0
    support_snippets: List[str] = field(default_factory=list)

    @property
    def source_domain(self) -> str:
        return urlparse(self.canonical_url).netloc.lower()


class DraftDigestItem(BaseModel):
    document_id: str
    headline: str
    summary: str
    why_it_matters: str


class DraftDigestContent(BaseModel):
    title: str
    intro: str
    summary: str
    items: List[DraftDigestItem] = Field(default_factory=list)


class OutputDigestMetric(BaseModel):
    name: str
    value: str
    unit: str = ""
    qualifier: str = ""


class OutputDigestQuote(BaseModel):
    speaker: str = ""
    text: str


class OutputDigestItem(BaseModel):
    documentId: str
    headline: str
    summary: str
    sourceName: str
    sourceUrl: str
    publishedAt: str
    tags: List[str] = Field(default_factory=list)
    whyItMatters: str
    metric: Optional[OutputDigestMetric] = None
    quote: Optional[OutputDigestQuote] = None


class OutputDigest(BaseModel):
    date: str
    windowStart: str
    windowEnd: str
    title: str
    intro: str
    summary: str
    generatedAt: str
    generatorModel: str
    backfill: bool
    items: List[OutputDigestItem] = Field(default_factory=list)


@dataclass
class DayRunResult:
    date: date
    status: Literal["generated", "skipped-existing", "skipped-weak", "failed", "dry-run"]
    reason: str = ""
    filepath: Optional[Path] = None


class DigestGenerationError(RuntimeError):
    pass


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def date_to_window(target_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y"}


def load_settings() -> DigestGeneratorSettings:
    output_repo = Path(
        os.getenv("DAILY_DIGEST_OUTPUT_REPO", r"C:\Users\Matth\Documents\workspace\lambic_labs_website")
    ).expanduser()
    website_content_dir = Path(os.getenv("DAILY_DIGEST_WEBSITE_CONTENT_DIR", "apps/web/content/research-digests"))
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise DigestGenerationError("DATABASE_URL is required")
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not openai_api_key:
        raise DigestGenerationError("OPENAI_API_KEY is required")
    context_api_token = os.getenv("CONTEXT_API_TOKEN", "").strip()
    if not context_api_token:
        raise DigestGenerationError("CONTEXT_API_TOKEN is required")
    return DigestGeneratorSettings(
        topic_key=os.getenv("DAILY_DIGEST_TOPIC_KEY", "ai_research").strip() or "ai_research",
        model=os.getenv("DAILY_DIGEST_MODEL", "gpt-5.2").strip() or "gpt-5.2",
        openai_api_key=openai_api_key,
        context_api_token=context_api_token,
        database_url=database_url,
        output_repo=output_repo,
        website_content_dir=website_content_dir,
        author_name=os.getenv("DAILY_DIGEST_AUTHOR_NAME", "Lambic Labs Research Editor").strip()
        or "Lambic Labs Research Editor",
        git_remote=os.getenv("DAILY_DIGEST_GIT_REMOTE", "origin").strip() or "origin",
        git_branch=os.getenv("DAILY_DIGEST_GIT_BRANCH", "main").strip() or "main",
        backfill_start_date=parse_date(os.getenv("DAILY_DIGEST_BACKFILL_START_DATE", "").strip())
        if os.getenv("DAILY_DIGEST_BACKFILL_START_DATE", "").strip()
        else None,
        backfill_end_date=parse_date(os.getenv("DAILY_DIGEST_BACKFILL_END_DATE", "").strip())
        if os.getenv("DAILY_DIGEST_BACKFILL_END_DATE", "").strip()
        else None,
        max_items=max(int(os.getenv("DAILY_DIGEST_MAX_ITEMS", "7")), 1),
        min_items=max(int(os.getenv("DAILY_DIGEST_MIN_ITEMS", "4")), 1),
        lookback_hours=max(int(os.getenv("DAILY_DIGEST_LOOKBACK_HOURS", "24")), 1),
        source_limit_per_digest=max(int(os.getenv("DAILY_DIGEST_SOURCE_LIMIT_PER_DIGEST", "2")), 1),
        validate_build=_env_bool("DAILY_DIGEST_VALIDATE_BUILD", True),
    )


def parse_request(argv: Optional[Sequence[str]] = None) -> GeneratorRequest:
    parser = argparse.ArgumentParser(description="Generate Lambic Labs daily research digests.")
    parser.add_argument("--mode", choices=["daily", "backfill-range", "backfill-missing"], default="daily")
    parser.add_argument("--date", dest="target_date")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return GeneratorRequest(
        mode=args.mode,
        target_date=parse_date(args.target_date) if args.target_date else None,
        start_date=parse_date(args.start_date) if args.start_date else None,
        end_date=parse_date(args.end_date) if args.end_date else None,
        force=bool(args.force),
        dry_run=bool(args.dry_run),
    )


def create_generator_engine(settings: DigestGeneratorSettings) -> Engine:
    return create_db_engine(settings.database_url)


def get_existing_digest_dates(digest_dir: Path) -> set[date]:
    if not digest_dir.exists():
        return set()
    dates: set[date] = set()
    for path in digest_dir.glob("*.json"):
        try:
            dates.add(parse_date(path.stem))
        except ValueError:
            continue
    return dates


def get_earliest_digestable_date(engine: Engine, topic_key: str) -> Optional[date]:
    sql = """
        SELECT min(date(coalesce(d.published_at, d.discovered_at) AT TIME ZONE 'UTC')) AS earliest_date
        FROM research_documents d
        JOIN research_sources s
          ON s.source_id = d.source_id
        WHERE s.topic_key = :topic_key
          AND d.status IN ('embedded', 'extracted', 'enriched')
          AND coalesce(d.suppressed, false) = false
    """
    with engine.begin() as conn:
        value = conn.execute(text(sql), {"topic_key": topic_key}).scalar_one_or_none()
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return parse_date(str(value))


def compute_target_dates(
    *,
    settings: DigestGeneratorSettings,
    request: GeneratorRequest,
    earliest_date: Optional[date],
    existing_dates: set[date],
) -> List[date]:
    if request.mode == "daily":
        target = request.target_date or (datetime.now(timezone.utc) - timedelta(days=1)).date()
        return [target]

    start = request.start_date or settings.backfill_start_date or earliest_date
    end = request.end_date or settings.backfill_end_date or (datetime.now(timezone.utc) - timedelta(days=1)).date()
    if start is None or end is None:
        return []
    if earliest_date and start < earliest_date:
        start = earliest_date
    if start > end:
        return []

    dates: List[date] = []
    current = start
    while current <= end:
        if request.mode == "backfill-missing" and not request.force and current in existing_dates:
            current += timedelta(days=1)
            continue
        dates.append(current)
        current += timedelta(days=1)
    return dates


def _clean_tag_list(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    cleaned: List[str] = []
    for value in values:
        text_value = str(value or "").strip()
        if text_value and text_value not in cleaned:
            cleaned.append(text_value)
    return cleaned


def _clean_mapping_list(values: Any) -> List[Dict[str, Any]]:
    if not isinstance(values, list):
        return []
    cleaned: List[Dict[str, Any]] = []
    for value in values:
        if isinstance(value, dict):
            cleaned.append(dict(value))
    return cleaned


def load_candidates_for_window(
    engine: Engine,
    *,
    topic_key: str,
    window_start: datetime,
    window_end: datetime,
) -> List[CandidateDocument]:
    sql = """
        SELECT
            d.document_id,
            d.source_id,
            s.name AS source_name,
            coalesce(d.title, d.canonical_url) AS title,
            d.canonical_url,
            coalesce(d.published_at, d.discovered_at) AS effective_at,
            d.published_at,
            coalesce(nullif(d.summary_short, ''), left(coalesce(d.extracted_text, ''), 360)) AS summary_short,
            coalesce(d.why_it_matters, '') AS why_it_matters,
            d.metrics,
            d.notable_quotes,
            d.topic_tags,
            d.decision_domains,
            d.content_type,
            d.publisher_type,
            d.source_class,
            coalesce(d.document_signal_score, 0.0) AS document_signal_score,
            coalesce(d.novelty_score, 0.0) AS novelty_score,
            coalesce(d.evidence_density_score, 0.0) AS evidence_density_score
        FROM research_documents d
        JOIN research_sources s
          ON s.source_id = d.source_id
        WHERE s.topic_key = :topic_key
          AND d.status IN ('embedded', 'extracted', 'enriched')
          AND coalesce(d.suppressed, false) = false
          AND coalesce(d.published_at, d.discovered_at) >= :window_start
          AND coalesce(d.published_at, d.discovered_at) < :window_end
        ORDER BY coalesce(d.published_at, d.discovered_at) DESC NULLS LAST, d.document_signal_score DESC, d.updated_at DESC
    """
    params = {"topic_key": topic_key, "window_start": window_start, "window_end": window_end}
    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    candidates: List[CandidateDocument] = []
    for row in rows:
        effective_at = row.get("published_at") or row.get("effective_at")
        if not isinstance(effective_at, datetime):
            continue
        candidates.append(
            CandidateDocument(
                document_id=str(row.get("document_id") or ""),
                source_id=str(row.get("source_id") or ""),
                source_name=str(row.get("source_name") or ""),
                title=str(row.get("title") or ""),
                canonical_url=str(row.get("canonical_url") or ""),
                published_at=effective_at.astimezone(timezone.utc),
                summary_short=str(row.get("summary_short") or ""),
                why_it_matters=str(row.get("why_it_matters") or ""),
                metrics=_clean_mapping_list(row.get("metrics")),
                notable_quotes=_clean_mapping_list(row.get("notable_quotes")),
                topic_tags=_clean_tag_list(row.get("topic_tags")),
                decision_domains=_clean_tag_list(row.get("decision_domains")),
                content_type=str(row.get("content_type") or "company_blog"),
                publisher_type=str(row.get("publisher_type") or "independent"),
                source_class=str(row.get("source_class") or "external_commentary"),
                document_signal_score=float(row.get("document_signal_score") or 0.0),
                novelty_score=float(row.get("novelty_score") or 0.0),
                evidence_density_score=float(row.get("evidence_density_score") or 0.0),
            )
        )
    return candidates


def build_dedupe_key(candidate: CandidateDocument) -> str:
    title_key = re.sub(r"[^a-z0-9]+", " ", candidate.title.lower()).strip()
    title_key = " ".join(title_key.split()[:8])
    return f"{candidate.source_domain}:{title_key}"


def score_candidate(candidate: CandidateDocument) -> float:
    score = candidate.document_signal_score * 4.0
    score += candidate.novelty_score * 1.5
    score += candidate.evidence_density_score * 1.25
    score += min(len(candidate.metrics), 3) * 0.35
    score += min(len(candidate.notable_quotes), 2) * 0.2
    if candidate.why_it_matters.strip():
        score += 0.45
    if candidate.summary_short.strip():
        score += 0.25
    score += PRIMARY_SOURCE_BOOST.get(candidate.source_class, 0.0)
    score += CONTENT_TYPE_BOOST.get(candidate.content_type, 0.0)
    lowered_title = candidate.title.lower()
    if any(keyword in lowered_title for keyword in ANNOUNCEMENT_PATTERNS):
        score -= 0.6
    return round(score, 4)


def attach_support_snippets(engine: Engine, candidates: Iterable[CandidateDocument]) -> None:
    for candidate in candidates:
        query_parts = [candidate.title]
        query_parts.extend(candidate.topic_tags[:3])
        query = " ".join(part for part in query_parts if part).strip()
        rows = search_research_document_chunks(engine, document_id=candidate.document_id, query=query or candidate.title, limit=3)
        candidate.support_snippets = [str(row.get("snippet") or "").strip() for row in rows if str(row.get("snippet") or "").strip()]


def select_distinct_candidates(
    candidates: Sequence[CandidateDocument],
    *,
    max_items: int,
    source_limit_per_digest: int,
) -> List[CandidateDocument]:
    scored: List[CandidateDocument] = []
    for candidate in candidates:
        candidate.candidate_score = score_candidate(candidate)
        scored.append(candidate)
    scored.sort(key=lambda item: (item.candidate_score, item.published_at), reverse=True)

    selected: List[CandidateDocument] = []
    selected_keys: set[str] = set()
    source_counts: Dict[str, int] = {}
    for candidate in scored:
        dedupe_key = build_dedupe_key(candidate)
        if dedupe_key in selected_keys:
            continue
        current_source_count = source_counts.get(candidate.source_name, 0)
        if current_source_count >= source_limit_per_digest:
            continue
        selected.append(candidate)
        selected_keys.add(dedupe_key)
        source_counts[candidate.source_name] = current_source_count + 1
        if len(selected) >= max_items:
            break
    return selected


def choose_metric(candidate: CandidateDocument) -> Optional[OutputDigestMetric]:
    if not candidate.metrics:
        return None
    top = candidate.metrics[0]
    return OutputDigestMetric(
        name=str(top.get("name") or "metric"),
        value=str(top.get("value") or ""),
        unit=str(top.get("unit") or ""),
        qualifier=str(top.get("qualifier") or ""),
    )


def choose_quote(candidate: CandidateDocument) -> Optional[OutputDigestQuote]:
    if not candidate.notable_quotes:
        return None
    top = candidate.notable_quotes[0]
    return OutputDigestQuote(
        speaker=str(top.get("speaker") or ""),
        text=str(top.get("text") or ""),
    )


def _openai_chat_completion(
    *,
    model: str,
    api_key: str,
    system_prompt: str,
    user_prompt: str,
) -> Dict[str, Any]:
    response = httpx.post(
        os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1/chat/completions"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise DigestGenerationError("Model response content was not a string")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise DigestGenerationError("Model response was not valid JSON") from exc


def write_editorial_draft(
    *,
    settings: DigestGeneratorSettings,
    target_date: date,
    backfill: bool,
    window_start: datetime,
    window_end: datetime,
    candidates: Sequence[CandidateDocument],
) -> DraftDigestContent:
    payload = {
        "date": target_date.isoformat(),
        "backfill": backfill,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "items": [
            {
                "document_id": candidate.document_id,
                "title": candidate.title,
                "source_name": candidate.source_name,
                "source_url": candidate.canonical_url,
                "published_at": candidate.published_at.isoformat(),
                "summary_short": candidate.summary_short,
                "why_it_matters": candidate.why_it_matters,
                "topic_tags": candidate.topic_tags,
                "decision_domains": candidate.decision_domains,
                "metrics": candidate.metrics[:2],
                "quotes": candidate.notable_quotes[:1],
                "support_snippets": candidate.support_snippets[:3],
            }
            for candidate in candidates
        ],
    }
    system_prompt = (
        "You are the Lambic Labs research editor. Return strict JSON only. "
        "Write a concise structured digest for the website. "
        "Do not invent facts, links, metrics, or source names. "
        "Top-level fields: title, intro, summary, items[]. "
        "Each item must contain document_id, headline, summary, why_it_matters. "
        "Use the supplied document_id values exactly once each. "
        "The digest should feel editorially sharp, technical, and grounded."
    )
    user_prompt = json.dumps(payload, ensure_ascii=True)
    try:
        raw = _openai_chat_completion(
            model=settings.model,
            api_key=settings.openai_api_key,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        draft = DraftDigestContent.model_validate(raw)
    except (httpx.HTTPError, ValidationError, DigestGenerationError) as exc:
        raise DigestGenerationError(f"Digest writing failed: {exc}") from exc

    expected_ids = {candidate.document_id for candidate in candidates}
    returned_ids = {item.document_id for item in draft.items}
    if returned_ids != expected_ids:
        raise DigestGenerationError("Model draft did not return the expected document set")
    return draft


def build_output_digest(
    *,
    settings: DigestGeneratorSettings,
    target_date: date,
    backfill: bool,
    window_start: datetime,
    window_end: datetime,
    draft: DraftDigestContent,
    candidates: Sequence[CandidateDocument],
) -> OutputDigest:
    by_id = {candidate.document_id: candidate for candidate in candidates}
    items: List[OutputDigestItem] = []
    for draft_item in draft.items:
        candidate = by_id[draft_item.document_id]
        tags = candidate.topic_tags[:4] or candidate.decision_domains[:4]
        items.append(
            OutputDigestItem(
                documentId=candidate.document_id,
                headline=draft_item.headline,
                summary=draft_item.summary,
                sourceName=candidate.source_name,
                sourceUrl=candidate.canonical_url,
                publishedAt=candidate.published_at.isoformat(),
                tags=tags,
                whyItMatters=draft_item.why_it_matters,
                metric=choose_metric(candidate),
                quote=choose_quote(candidate),
            )
        )
    return OutputDigest(
        date=target_date.isoformat(),
        windowStart=window_start.isoformat(),
        windowEnd=window_end.isoformat(),
        title=draft.title,
        intro=draft.intro,
        summary=draft.summary,
        generatedAt=datetime.now(timezone.utc).isoformat(),
        generatorModel=settings.model,
        backfill=backfill,
        items=items,
    )


def quality_gate_digest(digest: OutputDigest, *, min_items: int) -> Optional[str]:
    if len(digest.items) < min_items:
        return f"only {len(digest.items)} items selected"
    source_names = {item.sourceName for item in digest.items}
    if len(source_names) < min(3, len(digest.items)):
        return "insufficient source diversity"
    source_urls = [item.sourceUrl for item in digest.items]
    if len(set(source_urls)) != len(source_urls):
        return "duplicate source URLs"
    if not digest.title.strip() or not digest.intro.strip() or not digest.summary.strip():
        return "digest copy was incomplete"
    for item in digest.items:
        if not item.headline.strip() or not item.summary.strip() or not item.whyItMatters.strip():
            return f"incomplete item copy for {item.documentId}"
    return None


def ensure_digest_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def render_digest_json(digest: OutputDigest) -> str:
    return json.dumps(digest.model_dump(mode="json", exclude_none=True), indent=2, ensure_ascii=True) + "\n"


def write_digest_file(digest_dir: Path, digest: OutputDigest) -> Path:
    ensure_digest_dir(digest_dir)
    filepath = digest_dir / f"{digest.date}.json"
    filepath.write_text(render_digest_json(digest), encoding="utf-8")
    return filepath


def run_git_command(repo: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def ensure_publishable_worktree(repo: Path) -> None:
    status = run_git_command(repo, ["status", "--porcelain"])
    if status.returncode != 0:
        raise DigestGenerationError(status.stderr.strip() or "Unable to inspect website repo status")
    if status.stdout.strip():
        raise DigestGenerationError("Website repo has uncommitted changes; refusing to auto-commit generated digests")


def validate_website_build(settings: DigestGeneratorSettings) -> None:
    if not settings.validate_build:
        return
    workdir = settings.output_repo / "apps" / "web"
    npm_executable = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm_executable:
        raise DigestGenerationError("Unable to find npm or npm.cmd required for website build validation")
    result = subprocess.run(
        [npm_executable, "run", "build"],
        cwd=workdir,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise DigestGenerationError(result.stdout + "\n" + result.stderr)


def commit_and_push_generated_digests(
    *,
    settings: DigestGeneratorSettings,
    filepaths: Sequence[Path],
    message: str,
) -> None:
    repo = settings.output_repo
    for path in filepaths:
        relative_path = str(path.relative_to(repo))
        add_result = run_git_command(repo, ["add", relative_path])
        if add_result.returncode != 0:
            raise DigestGenerationError(add_result.stderr.strip() or f"Unable to add {path}")
    commit_result = run_git_command(repo, ["commit", "-m", message])
    if commit_result.returncode != 0:
        raise DigestGenerationError(commit_result.stderr.strip() or commit_result.stdout.strip() or "git commit failed")
    push_result = run_git_command(repo, ["push", settings.git_remote, settings.git_branch])
    if push_result.returncode != 0:
        raise DigestGenerationError(push_result.stderr.strip() or push_result.stdout.strip() or "git push failed")


def generate_digest_for_day(
    *,
    engine: Engine,
    settings: DigestGeneratorSettings,
    target_date: date,
    existing_dates: set[date],
    request: GeneratorRequest,
) -> DayRunResult:
    if not request.force and target_date in existing_dates:
        return DayRunResult(date=target_date, status="skipped-existing", reason="digest already exists")

    window_start, window_end = date_to_window(target_date)
    candidates = load_candidates_for_window(engine, topic_key=settings.topic_key, window_start=window_start, window_end=window_end)
    selected = select_distinct_candidates(
        candidates,
        max_items=settings.max_items,
        source_limit_per_digest=settings.source_limit_per_digest,
    )
    attach_support_snippets(engine, selected)
    if len(selected) < settings.min_items:
        return DayRunResult(date=target_date, status="skipped-weak", reason=f"only {len(selected)} strong items found")

    draft = write_editorial_draft(
        settings=settings,
        target_date=target_date,
        backfill=request.mode != "daily",
        window_start=window_start,
        window_end=window_end,
        candidates=selected,
    )
    digest = build_output_digest(
        settings=settings,
        target_date=target_date,
        backfill=request.mode != "daily",
        window_start=window_start,
        window_end=window_end,
        draft=draft,
        candidates=selected,
    )
    gate_error = quality_gate_digest(digest, min_items=settings.min_items)
    if gate_error:
        return DayRunResult(date=target_date, status="skipped-weak", reason=gate_error)
    if request.dry_run:
        return DayRunResult(date=target_date, status="dry-run", reason="validated without writing")
    filepath = write_digest_file(settings.digest_dir, digest)
    return DayRunResult(date=target_date, status="generated", filepath=filepath)


def build_commit_message(mode: RunMode, generated_dates: Sequence[date]) -> str:
    if not generated_dates:
        return "Update research digests"
    if mode == "daily" and len(generated_dates) == 1:
        return f"Add research digest for {generated_dates[0].isoformat()}"
    return f"Backfill research digests {generated_dates[0].isoformat()} to {generated_dates[-1].isoformat()}"


def execute_generation(
    *,
    settings: DigestGeneratorSettings,
    request: GeneratorRequest,
    engine: Optional[Engine] = None,
) -> Dict[str, Any]:
    effective_engine = engine or create_generator_engine(settings)
    existing_dates = get_existing_digest_dates(settings.digest_dir)
    earliest_date = get_earliest_digestable_date(effective_engine, settings.topic_key)
    target_dates = compute_target_dates(
        settings=settings,
        request=request,
        earliest_date=earliest_date,
        existing_dates=existing_dates,
    )
    results: List[DayRunResult] = []

    if not request.dry_run:
        ensure_publishable_worktree(settings.output_repo)

    for target in target_dates:
        try:
            results.append(
                generate_digest_for_day(
                    engine=effective_engine,
                    settings=settings,
                    target_date=target,
                    existing_dates=existing_dates,
                    request=request,
                )
            )
        except Exception as exc:  # noqa: BLE001
            results.append(DayRunResult(date=target, status="failed", reason=str(exc)))

    generated = [result for result in results if result.status == "generated" and result.filepath]
    if generated and not request.dry_run:
        validate_website_build(settings)
        commit_and_push_generated_digests(
            settings=settings,
            filepaths=[result.filepath for result in generated if result.filepath is not None],
            message=build_commit_message(request.mode, [result.date for result in generated]),
        )

    report = {
        "mode": request.mode,
        "topic_key": settings.topic_key,
        "model": settings.model,
        "earliest_digestable_date": earliest_date.isoformat() if earliest_date else None,
        "target_dates": [target.isoformat() for target in target_dates],
        "results": [
            {
                "date": result.date.isoformat(),
                "status": result.status,
                "reason": result.reason,
                "filepath": str(result.filepath) if result.filepath else None,
            }
            for result in results
        ],
    }

    if request.mode == "daily":
        daily_result = results[0] if results else None
        if daily_result and daily_result.status in {"failed", "skipped-weak"}:
            raise DigestGenerationError(daily_result.reason or daily_result.status)
    elif any(result.status == "failed" for result in results):
        raise DigestGenerationError("One or more backfill dates failed")

    return report
