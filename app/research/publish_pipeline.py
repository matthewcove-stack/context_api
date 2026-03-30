from __future__ import annotations

import argparse
import json
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import text

from app.research.brief_ops import (
    WebsiteRepoPaths,
    commit_and_push,
    ensure_clean_worktree,
    list_worktree_changes,
    list_staged_changes,
    prepare_publish_workspace,
    resolve_website_repo_paths,
    run_npm_script,
    stage_publish_outputs,
    validate_website_repo_paths,
)
from app.research.digest_generator import (
    compute_target_dates,
    determine_digest_window,
    DigestGeneratorSettings,
    GeneratorRequest,
    create_generator_engine,
    execute_generation as execute_digest_generation,
    get_earliest_digestable_date,
    get_existing_digest_dates,
    load_candidates_for_window,
    load_settings as load_digest_settings,
    select_distinct_candidates,
)
from app.research.distribution_generator import (
    DistributionGeneratorSettings,
    execute_generation as execute_distribution_generation,
    load_settings as load_distribution_settings,
)


PUBLISH_OUTPUT_PATHS = (
    "apps/web/content/research-digests",
    "apps/web/content/research-digest-assets",
    "apps/web/content/research-weekly",
    "apps/web/public/brief/feed.xml",
    "apps/web/public/brief/weekly/feed.xml",
)


class BriefPublishError(RuntimeError):
    pass


def _database_reachable(engine: object) -> Dict[str, Any]:
    if not hasattr(engine, "begin"):
        return {"checked": False, "reachable": True}
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT 1"))
        return {"checked": True, "reachable": True}
    except Exception as exc:  # noqa: BLE001
        return {"checked": True, "reachable": False, "error": str(exc)}


def _runtime_status(settings: DigestGeneratorSettings, paths: WebsiteRepoPaths) -> Dict[str, Any]:
    values = {
        "DATABASE_URL": bool(settings.database_url.strip()),
        "OPENAI_API_KEY": bool(settings.openai_api_key.strip()),
        "CONTEXT_API_TOKEN": bool(settings.context_api_token.strip()),
        "BRIEF_WEBSITE_REPO": bool(str(paths.repo_root).strip()),
        "DAILY_DIGEST_GIT_REMOTE": bool(settings.git_remote.strip()),
        "DAILY_DIGEST_GIT_BRANCH": bool(settings.git_branch.strip()),
    }
    return {
        "configured": values,
        "all_configured": all(values.values()),
        "publish_env": os.getenv("BRIEF_PUBLISH_ENV", "prod").strip().lower() or "prod",
    }


def _candidate_readiness(
    *,
    engine: object,
    settings: DigestGeneratorSettings,
    request: GeneratorRequest,
    existing_dates: set,
    target_dates: Sequence,
) -> Dict[str, Any]:
    if request.mode != "daily" or not target_dates or not hasattr(engine, "begin"):
        return {
            "evaluated": False,
            "minimum_required_items": settings.min_items,
            "enough_candidates": None,
        }

    target_date = target_dates[0]
    window_start, window_end = determine_digest_window(
        target_date=target_date,
        existing_dates=existing_dates,
        request=request,
    )
    candidates = load_candidates_for_window(
        engine,
        topic_key=settings.topic_key,
        window_start=window_start,
        window_end=window_end,
    )
    selected = select_distinct_candidates(
        candidates,
        max_items=settings.max_items,
        source_limit_per_digest=settings.source_limit_per_digest,
    )
    readiness = {
        "evaluated": True,
        "target_date": target_date.isoformat(),
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "minimum_required_items": settings.min_items,
        "enough_candidates": len(selected) >= settings.min_items,
    }
    if not readiness["enough_candidates"]:
        readiness["error"] = f"only {len(selected)} strong items found for {target_date.isoformat()}"
    return readiness


def _maybe_write_publish_report(report: Dict[str, Any]) -> Optional[str]:
    explicit_path = os.getenv("BRIEF_PUBLISH_REPORT_PATH", "").strip()
    report_dir = os.getenv("BRIEF_PUBLISH_REPORT_DIR", "").strip()

    target_path: Optional[Path] = None
    if explicit_path:
        target_path = Path(explicit_path).expanduser()
    elif report_dir:
        safe_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target_path = Path(report_dir).expanduser() / f"lambic-ai-brief-publish-{safe_timestamp}.json"

    if target_path is None:
        return None

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return str(target_path)


def _coerce_settings_for_workspace(
    digest_settings: DigestGeneratorSettings,
    distribution_settings: DistributionGeneratorSettings,
    workspace: WebsiteRepoPaths,
) -> tuple[DigestGeneratorSettings, DistributionGeneratorSettings]:
    return (
        replace(
            digest_settings,
            output_repo=workspace.repo_root,
            website_content_dir=workspace.digest_dir.relative_to(workspace.repo_root),
        ),
        replace(
            distribution_settings,
            output_repo=workspace.repo_root,
            digest_dir=workspace.digest_dir,
            assets_dir=workspace.assets_dir,
            weekly_dir=workspace.weekly_dir,
        ),
    )


def _build_publish_commit_message(request: GeneratorRequest, generated_dates: Sequence[str]) -> str:
    if not generated_dates:
        return "Publish Lambic AI Brief updates"
    if request.mode == "daily" and len(generated_dates) == 1:
        return f"Publish Lambic AI Brief for {generated_dates[0]}"
    return f"Publish Lambic AI Brief updates {generated_dates[0]} to {generated_dates[-1]}"


def _extract_generated_dates(report: Dict[str, Any]) -> List[str]:
    values = report.get("generated_dates") or []
    return [str(value) for value in values if str(value).strip()]


def _validate_post_publish_outputs(workspace: WebsiteRepoPaths, generated_dates: Sequence[str]) -> None:
    for value in generated_dates:
        expected = workspace.digest_dir / f"{value}.json"
        if not expected.exists():
            raise BriefPublishError(f"Expected generated digest is missing: {expected}")
    if generated_dates and not workspace.assets_dir.exists():
        raise BriefPublishError(f"Distribution assets directory is missing after publish: {workspace.assets_dir}")
    if generated_dates and not workspace.weekly_dir.exists():
        raise BriefPublishError(f"Weekly digest directory is missing after publish: {workspace.weekly_dir}")


def parse_request(argv: Optional[Sequence[str]] = None) -> GeneratorRequest:
    parser = argparse.ArgumentParser(description="Publish Lambic AI Brief outputs.")
    parser.add_argument("--mode", choices=["daily", "backfill-range", "backfill-missing"], default="daily")
    parser.add_argument("--date", dest="target_date")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    from app.research.digest_generator import parse_date

    return GeneratorRequest(
        mode=args.mode,
        target_date=parse_date(args.target_date) if args.target_date else None,
        start_date=parse_date(args.start_date) if args.start_date else None,
        end_date=parse_date(args.end_date) if args.end_date else None,
        force=bool(args.force),
        dry_run=bool(args.dry_run),
    )


def execute_publish(
    *,
    request: GeneratorRequest,
    digest_settings: Optional[DigestGeneratorSettings] = None,
    distribution_settings: Optional[DistributionGeneratorSettings] = None,
) -> Dict[str, Any]:
    effective_digest_settings = digest_settings or load_digest_settings()
    effective_distribution_settings = distribution_settings or load_distribution_settings()
    if digest_settings is not None and distribution_settings is not None:
        paths = WebsiteRepoPaths(
            repo_root=effective_digest_settings.output_repo,
            web_app_dir=effective_digest_settings.output_repo / "apps" / "web",
            digest_dir=effective_digest_settings.output_repo / effective_digest_settings.website_content_dir,
            assets_dir=effective_distribution_settings.assets_dir,
            weekly_dir=effective_distribution_settings.weekly_dir,
            daily_feed_path=effective_digest_settings.output_repo / "apps" / "web" / "public" / "brief" / "feed.xml",
            weekly_feed_path=effective_digest_settings.output_repo / "apps" / "web" / "public" / "brief" / "weekly" / "feed.xml",
        )
        validate_website_repo_paths(paths)
    else:
        paths = resolve_website_repo_paths(
            digest_dir=str(effective_digest_settings.website_content_dir),
            assets_dir=str(effective_distribution_settings.assets_dir.relative_to(effective_distribution_settings.output_repo)),
            weekly_dir=str(effective_distribution_settings.weekly_dir.relative_to(effective_distribution_settings.output_repo)),
        )
    started_at = datetime.now(timezone.utc)
    engine = create_generator_engine(effective_digest_settings)
    db_status = _database_reachable(engine)
    if not db_status["reachable"]:
        raise BriefPublishError(db_status.get("error") or "Unable to reach research database")

    existing_dates = get_existing_digest_dates(paths.digest_dir)
    earliest_date = get_earliest_digestable_date(engine, effective_digest_settings.topic_key) if hasattr(engine, "begin") else None
    target_dates = (
        compute_target_dates(
            settings=effective_digest_settings,
            request=request,
            earliest_date=earliest_date,
            existing_dates=existing_dates,
        )
        if hasattr(engine, "begin")
        else []
    )
    runtime_status = _runtime_status(effective_digest_settings, paths)
    candidate_readiness = _candidate_readiness(
        engine=engine,
        settings=effective_digest_settings,
        request=request,
        existing_dates=existing_dates,
        target_dates=target_dates,
    )
    preflight: Dict[str, Any] = {
        "website_repo": str(paths.repo_root),
        "topic_key": effective_digest_settings.topic_key,
        "workspace_mode": "dry-run-copy" if request.dry_run else "in-place",
        "database": db_status,
        "runtime": runtime_status,
        "earliest_digestable_date": earliest_date.isoformat() if earliest_date else None,
        "target_dates": [target.isoformat() for target in target_dates],
        "candidate_readiness": candidate_readiness,
        "worktree_clean": request.dry_run,
    }

    if not request.dry_run:
        ensure_clean_worktree(paths.repo_root)
        preflight["worktree_clean"] = True
    if (
        not request.dry_run
        and candidate_readiness.get("evaluated")
        and candidate_readiness.get("enough_candidates") is False
    ):
        raise BriefPublishError(candidate_readiness.get("error") or "Not enough strong candidates for publish")

    with prepare_publish_workspace(paths, dry_run=request.dry_run) as workspace:
        workspace_digest_settings, workspace_distribution_settings = _coerce_settings_for_workspace(
            effective_digest_settings,
            effective_distribution_settings,
            workspace,
        )
        workspace_request = replace(request, dry_run=False) if request.dry_run else request
        digest_report = execute_digest_generation(
            settings=workspace_digest_settings,
            request=workspace_request,
            engine=engine,
            allow_skipped_weak=request.dry_run,
        )
        generated_dates = _extract_generated_dates(digest_report)

        distribution_report: Dict[str, Any] = {
            "mode": "all",
            "daily_digest_count": 0,
            "generated_assets": [],
            "generated_weeklies": [],
            "generated_asset_paths": [],
            "generated_weekly_paths": [],
            "removed_asset_paths": [],
            "removed_weekly_paths": [],
        }

        changed_files_before_stage: List[str] = []
        commit_message: Optional[str] = None
        pushed = False
        validation_steps: List[str] = []

        if generated_dates:
            distribution_report = execute_distribution_generation(
                settings=workspace_distribution_settings,
                mode="all",
                dry_run=False,
            )
            run_npm_script(workspace.web_app_dir, "research:validate")
            validation_steps.append("research:validate")
            run_npm_script(workspace.web_app_dir, "research:feeds")
            validation_steps.append("research:feeds")
            run_npm_script(workspace.web_app_dir, "build")
            validation_steps.append("build")
            _validate_post_publish_outputs(workspace, generated_dates)

            if not request.dry_run:
                changed_files_before_stage = list_worktree_changes(workspace.repo_root)
                stage_publish_outputs(workspace.repo_root, PUBLISH_OUTPUT_PATHS)
                if list_staged_changes(workspace.repo_root):
                    commit_message = _build_publish_commit_message(request, generated_dates)
                    commit_and_push(
                        workspace.repo_root,
                        remote=workspace_digest_settings.git_remote,
                        branch=workspace_digest_settings.git_branch,
                        message=commit_message,
                    )
                    pushed = True
                    if list_worktree_changes(workspace.repo_root):
                        raise BriefPublishError("Website repo is not clean after publish")

        daily_paths = [str(item.get("filepath")) for item in digest_report.get("results", []) if item.get("filepath")]
        asset_paths = [str(value) for value in distribution_report.get("generated_asset_paths", [])]
        weekly_paths = [str(value) for value in distribution_report.get("generated_weekly_paths", [])]
        skipped_dates = [
            {"date": str(item.get("date")), "reason": str(item.get("reason") or "")}
            for item in digest_report.get("results", [])
            if str(item.get("status")) in {"skipped-existing", "skipped-weak"}
        ]
        failed_dates = [
            {"date": str(item.get("date")), "reason": str(item.get("reason") or "")}
            for item in digest_report.get("results", [])
            if str(item.get("status")) == "failed"
        ]
        postflight = {
            "daily_digest_paths": daily_paths,
            "distribution_asset_paths": asset_paths,
            "weekly_digest_paths": weekly_paths,
            "daily_feed_path": str(workspace.daily_feed_path) if workspace.daily_feed_path.exists() else None,
            "weekly_feed_path": str(workspace.weekly_feed_path) if workspace.weekly_feed_path.exists() else None,
            "validation_steps": validation_steps,
            "website_repo_clean": True if request.dry_run else not list_worktree_changes(workspace.repo_root),
        }
        report = {
            "mode": request.mode,
            "dry_run": request.dry_run,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "preflight": preflight,
            "daily_report": digest_report,
            "distribution_report": distribution_report,
            "generated_dates": generated_dates,
            "skipped_dates": skipped_dates,
            "failed_dates": failed_dates,
            "changed_files_before_stage": changed_files_before_stage,
            "commit_message": commit_message,
            "pushed": pushed,
            "postflight": postflight,
            "workspace_repo": str(workspace.repo_root),
        }
        report_path = _maybe_write_publish_report(report)
        if report_path:
            report["report_path"] = report_path

    return report
