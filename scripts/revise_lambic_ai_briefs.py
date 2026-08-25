from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.research.digest_generator import (  # noqa: E402
    CandidateDocument,
    DraftDigestContent,
    DraftDigestEditorial,
    DraftDigestItem,
    DigestGenerationError,
    OutputDigest,
    OutputDigestEditorial,
    OutputDigestEditorialReview,
    _clean_headline,
    _clean_sentence,
    _clean_top_things,
    render_digest_json,
    review_and_rewrite_editorial_draft,
)
from app.research.editorial_review import (  # noqa: E402
    EDITORIAL_WORKFLOW_VERSION,
    load_recent_digest_payloads,
    review_digest_payload,
)


def parse_request(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Lambic structural and anti-AI editorial workflow over existing Brief issues."
    )
    parser.add_argument("--website-repo", type=Path, required=True)
    parser.add_argument("--last", type=int, default=10)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def _digest_dir(website_repo: Path) -> Path:
    return website_repo.resolve() / "apps" / "web" / "content" / "research-digests"


def _select_paths(
    digest_dir: Path,
    *,
    last: int,
    start_date: str | None,
    end_date: str | None,
) -> list[Path]:
    paths = sorted(digest_dir.glob("*.json"))
    if start_date:
        paths = [path for path in paths if path.stem >= start_date]
    if end_date:
        paths = [path for path in paths if path.stem <= end_date]
    if not start_date and not end_date:
        paths = paths[-max(last, 1) :]
    if not paths:
        raise DigestGenerationError("No matching Brief issues were found")
    return paths


def _draft_from_digest(digest: OutputDigest) -> DraftDigestContent:
    editorial = digest.editorial or OutputDigestEditorial(
        editorialFrame=digest.issueSummary,
        builderImplication=digest.topThings[0] if digest.topThings else digest.issueSummary,
        watchSignal=digest.topThings[1] if len(digest.topThings) > 1 else digest.issueSummary,
    )
    return DraftDigestContent(
        title=digest.title,
        intro=digest.intro,
        summary=digest.summary,
        issue_summary=digest.issueSummary,
        top_things=digest.topThings,
        editorial=DraftDigestEditorial(
            editorial_frame=editorial.editorialFrame,
            builder_implication=editorial.builderImplication,
            watch_signal=editorial.watchSignal,
        ),
        items=[
            DraftDigestItem(
                document_id=item.documentId,
                headline=item.headline,
                contextual_background=item.contextualBackground or "",
                what_happened=item.whatHappened,
                why_it_matters=item.whyItMatters,
                engineering_takeaway=item.engineeringTakeaway,
            )
            for item in digest.items
        ],
    )


def _candidates_from_digest(digest: OutputDigest) -> list[CandidateDocument]:
    candidates: list[CandidateDocument] = []
    for item in digest.items:
        metrics = [item.metric.model_dump(mode="json")] if item.metric else []
        quotes = [item.quote.model_dump(mode="json")] if item.quote else []
        candidates.append(
            CandidateDocument(
                document_id=item.documentId,
                source_id=item.documentId,
                source_name=item.sourceName,
                title=item.sourceTitle or item.headline,
                canonical_url=item.sourceUrl,
                published_at=datetime.fromisoformat(item.publishedAt.replace("Z", "+00:00")),
                summary_short=item.whatHappened,
                why_it_matters=item.whyItMatters,
                metrics=metrics,
                notable_quotes=quotes,
                topic_tags=item.tags,
                decision_domains=[],
                content_type="article",
                publisher_type="publisher",
                source_class="external_primary",
                document_signal_score=0.0,
                novelty_score=0.0,
                evidence_density_score=0.0,
                support_snippets=[
                    value
                    for value in (item.contextualBackground, item.whatHappened, item.whyItMatters)
                    if value
                ],
            )
        )
    return candidates


def _apply_revised_copy(
    original: OutputDigest,
    draft: DraftDigestContent,
    *,
    revision_count: int,
    checked_fields: int,
    review_notes: Any,
) -> OutputDigest:
    revised = original.model_copy(deep=True)
    revised.title = _clean_headline(draft.title, original.title)
    revised.intro = _clean_sentence(draft.intro, minimum_words=10, maximum_length=420) or original.intro
    revised.summary = _clean_sentence(draft.summary, minimum_words=12, maximum_length=620) or original.summary
    revised.issueSummary = (
        _clean_sentence(draft.issue_summary, minimum_words=8, maximum_length=260) or original.issueSummary
    )
    revised.topThings = _clean_top_things(draft.top_things) or original.topThings
    revised.editorial = OutputDigestEditorial(
        editorialFrame=_clean_sentence(
            draft.editorial.editorial_frame,
            minimum_words=8,
            maximum_length=360,
        )
        or original.issueSummary,
        builderImplication=_clean_sentence(
            draft.editorial.builder_implication,
            minimum_words=8,
            maximum_length=360,
        )
        or original.issueSummary,
        watchSignal=_clean_sentence(
            draft.editorial.watch_signal,
            minimum_words=8,
            maximum_length=360,
        )
        or original.issueSummary,
    )

    original_items = {item.documentId: item for item in revised.items}
    for draft_item in draft.items:
        item = original_items[draft_item.document_id]
        item.headline = _clean_headline(draft_item.headline, item.headline)
        item.contextualBackground = (
            _clean_sentence(draft_item.contextual_background, minimum_words=5, maximum_length=340) or None
        )
        item.whatHappened = (
            _clean_sentence(draft_item.what_happened, minimum_words=8, maximum_length=680) or item.whatHappened
        )
        item.whyItMatters = (
            _clean_sentence(draft_item.why_it_matters, minimum_words=8, maximum_length=680) or item.whyItMatters
        )
        item.engineeringTakeaway = (
            _clean_sentence(draft_item.engineering_takeaway, minimum_words=6, maximum_length=380)
            or item.engineeringTakeaway
        )

    if revised.share:
        revised.share.title = revised.title
        revised.share.description = revised.issueSummary
    revised.editorialReview = OutputDigestEditorialReview(
        workflowVersion=EDITORIAL_WORKFLOW_VERSION,
        status="passed",
        revisionCount=revision_count,
        checkedFields=checked_fields,
        reviewedAt=datetime.now(timezone.utc).isoformat(),
        structuralFindings=list(review_notes.structural_findings),
        antiAiFindings=list(review_notes.anti_ai_findings),
        materialEdits=list(review_notes.material_edits),
    )
    return revised


def revise_digest(
    *,
    digest: OutputDigest,
    model: str,
    api_key: str,
    recent_payloads: Sequence[Dict[str, Any]],
) -> OutputDigest:
    settings = SimpleNamespace(model=model, openai_api_key=api_key)
    working_digest = digest.model_copy(deep=True)
    removed_items = [
        item
        for item in working_digest.items
        if item.whatHappened.strip()[-1:] not in {".", "!", "?", "\u2019", "\u201d"}
    ]
    if removed_items:
        removed_ids = {item.documentId for item in removed_items}
        working_digest.items = [item for item in working_digest.items if item.documentId not in removed_ids]
    if len(working_digest.items) < 3:
        raise DigestGenerationError(f"{digest.date}: fewer than three complete source items remain after cleanup")

    candidates = _candidates_from_digest(working_digest)
    draft = _draft_from_digest(working_digest)
    review_notes: Any = SimpleNamespace(structural_findings=[], anti_ai_findings=[], material_edits=[])
    revised = working_digest
    final_review = review_digest_payload(
        digest.model_dump(mode="json", exclude_none=True),
        recent_payloads=recent_payloads,
    )
    review_error: str | None = None

    for attempt in range(1, 4):
        current_payload = revised.model_dump(mode="json", exclude_none=True)
        current_review = review_digest_payload(current_payload, recent_payloads=recent_payloads)
        try:
            reviewed = review_and_rewrite_editorial_draft(
                settings=settings,
                draft=draft,
                candidates=candidates,
                findings=current_review.findings,
                recent_payloads=recent_payloads,
            )
        except DigestGenerationError as exc:
            review_error = str(exc)
            continue
        draft = reviewed.digest
        review_notes = reviewed.review
        revised = _apply_revised_copy(
            working_digest,
            draft,
            revision_count=attempt,
            checked_fields=0,
            review_notes=review_notes,
        )
        final_review = review_digest_payload(
            revised.model_dump(mode="json", exclude_none=True),
            recent_payloads=recent_payloads,
        )
        if final_review.passed:
            revised.editorialReview = OutputDigestEditorialReview(
                workflowVersion=EDITORIAL_WORKFLOW_VERSION,
                status="passed",
                revisionCount=attempt,
                checkedFields=final_review.checked_fields,
                reviewedAt=datetime.now(timezone.utc).isoformat(),
                structuralFindings=list(review_notes.structural_findings),
                antiAiFindings=list(review_notes.anti_ai_findings),
                materialEdits=list(review_notes.material_edits)
                + [
                    f"Removed {item.documentId} because the stored what-happened text was truncated."
                    for item in removed_items
                ],
            )
            return revised

    detail = final_review.summary(limit=8)
    if review_error:
        detail = f"{detail}; last model error: {review_error}"
    raise DigestGenerationError(f"{digest.date}: {detail}")


def main(argv: Sequence[str] | None = None) -> None:
    request = parse_request(argv)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise DigestGenerationError("OPENAI_API_KEY is required")
    model = os.getenv("DAILY_DIGEST_MODEL", "gpt-5.2").strip() or "gpt-5.2"
    digest_dir = _digest_dir(request.website_repo)
    paths = _select_paths(
        digest_dir,
        last=request.last,
        start_date=request.start_date,
        end_date=request.end_date,
    )

    revised_payloads: list[dict[str, Any]] = []
    revised_by_path: dict[Path, OutputDigest] = {}
    reports: list[dict[str, Any]] = []
    for path in paths:
        original = OutputDigest.model_validate(json.loads(path.read_text(encoding="utf-8")))
        recent = list(reversed(revised_payloads[-10:]))
        known_dates = {str(payload.get("date")) for payload in recent}
        recent.extend(
            payload
            for payload in load_recent_digest_payloads(digest_dir, before_date=original.date, limit=10)
            if str(payload.get("date")) not in known_dates
        )
        revised = revise_digest(
            digest=original,
            model=model,
            api_key=api_key,
            recent_payloads=recent[:10],
        )
        revised_by_path[path] = revised
        revised_payload = revised.model_dump(mode="json", exclude_none=True)
        revised_payloads.append(revised_payload)
        reports.append(
            {
                "date": revised.date,
                "status": "validated" if request.dry_run else "revised",
                "revision_count": revised.editorialReview.revisionCount if revised.editorialReview else 0,
                "checked_fields": revised.editorialReview.checkedFields if revised.editorialReview else 0,
            }
        )

    if not request.dry_run:
        for path, revised in revised_by_path.items():
            path.write_text(render_digest_json(revised), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "validated" if request.dry_run else "revised",
                "workflow_version": EDITORIAL_WORKFLOW_VERSION,
                "model": model,
                "issues": reports,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except DigestGenerationError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
