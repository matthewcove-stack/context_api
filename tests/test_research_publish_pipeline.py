from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.research.brief_ops import BriefOpsError, resolve_website_repo_paths
from app.research.digest_generator import DigestGeneratorSettings, GeneratorRequest
from app.research.distribution_generator import DistributionGeneratorSettings
from app.research.publish_pipeline import BriefPublishError, execute_publish


def _website_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "website"
    (repo / ".git").mkdir(parents=True)
    web = repo / "apps" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text('{"name":"test-web"}', encoding="utf-8")
    return repo


def _digest_settings(repo: Path) -> DigestGeneratorSettings:
    return DigestGeneratorSettings(
        topic_key="ai_research",
        model="gpt-5.2",
        openai_api_key="key",
        context_api_token="token",
        database_url="postgresql://example",
        output_repo=repo,
        website_content_dir=Path("apps/web/content/research-digests"),
        author_name="Lambic AI Brief Editor",
        git_remote="origin",
        git_branch="main",
        backfill_start_date=None,
        backfill_end_date=None,
        max_items=7,
        min_items=4,
        lookback_hours=24,
        source_limit_per_digest=2,
        validate_build=True,
    )


def _distribution_settings(repo: Path) -> DistributionGeneratorSettings:
    return DistributionGeneratorSettings(
        output_repo=repo,
        digest_dir=repo / "apps" / "web" / "content" / "research-digests",
        assets_dir=repo / "apps" / "web" / "content" / "research-digest-assets",
        weekly_dir=repo / "apps" / "web" / "content" / "research-weekly",
    )


def test_resolve_website_repo_paths_requires_explicit_repo_outside_dev(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing_repo = tmp_path / "missing"
    monkeypatch.setenv("BRIEF_PUBLISH_ENV", "prod")
    monkeypatch.setenv("BRIEF_WEBSITE_REPO", str(missing_repo))

    with pytest.raises(BriefOpsError):
        resolve_website_repo_paths()


def test_publish_pipeline_dry_run_uses_workspace_copy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = _website_repo(tmp_path)
    digest_settings = _digest_settings(repo)
    distribution_settings = _distribution_settings(repo)

    def fake_create_engine(settings: DigestGeneratorSettings) -> object:
        return object()

    def fake_digest(*, settings: DigestGeneratorSettings, request: GeneratorRequest, engine: object) -> dict:
        settings.digest_dir.mkdir(parents=True, exist_ok=True)
        (settings.digest_dir / "2026-03-12.json").write_text("{}", encoding="utf-8")
        return {
            "mode": request.mode,
            "generated_dates": ["2026-03-12"],
            "results": [{"date": "2026-03-12", "status": "generated"}],
        }

    def fake_distribution(*, settings: DistributionGeneratorSettings, mode: str, dry_run: bool) -> dict:
        settings.assets_dir.mkdir(parents=True, exist_ok=True)
        settings.weekly_dir.mkdir(parents=True, exist_ok=True)
        (settings.assets_dir / "2026-03-12.json").write_text("{}", encoding="utf-8")
        (settings.weekly_dir / "2026-W11.json").write_text("{}", encoding="utf-8")
        return {
            "mode": mode,
            "daily_digest_count": 1,
            "generated_assets": ["2026-03-12"],
            "generated_weeklies": ["2026-W11"],
            "generated_asset_paths": [str(settings.assets_dir / "2026-03-12.json")],
            "generated_weekly_paths": [str(settings.weekly_dir / "2026-W11.json")],
            "removed_asset_paths": [],
            "removed_weekly_paths": [],
        }

    monkeypatch.setattr("app.research.publish_pipeline.create_generator_engine", fake_create_engine)
    monkeypatch.setattr("app.research.publish_pipeline.execute_digest_generation", fake_digest)
    monkeypatch.setattr("app.research.publish_pipeline.execute_distribution_generation", fake_distribution)
    monkeypatch.setattr("app.research.publish_pipeline.run_npm_script", lambda workdir, script: None)

    report = execute_publish(
        request=GeneratorRequest(
            mode="daily",
            target_date=None,
            start_date=None,
            end_date=None,
            force=False,
            dry_run=True,
        ),
        digest_settings=digest_settings,
        distribution_settings=distribution_settings,
    )

    assert report["dry_run"] is True
    assert report["pushed"] is False
    assert report["generated_dates"] == ["2026-03-12"]
    assert report["workspace_repo"] != str(repo)
    assert not (repo / "apps" / "web" / "content" / "research-digests" / "2026-03-12.json").exists()


def test_publish_pipeline_skips_publish_when_no_new_issue(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = _website_repo(tmp_path)
    digest_settings = _digest_settings(repo)
    distribution_settings = _distribution_settings(repo)

    monkeypatch.setattr("app.research.publish_pipeline.create_generator_engine", lambda settings: object())
    monkeypatch.setattr(
        "app.research.publish_pipeline.execute_digest_generation",
        lambda **kwargs: {"mode": "daily", "generated_dates": [], "results": [{"status": "skipped-weak"}]},
    )

    distribution_called = {"value": False}

    def fake_distribution(**kwargs: object) -> dict:
        distribution_called["value"] = True
        return {}

    monkeypatch.setattr("app.research.publish_pipeline.execute_distribution_generation", fake_distribution)

    report = execute_publish(
        request=GeneratorRequest(
            mode="daily",
            target_date=None,
            start_date=None,
            end_date=None,
            force=False,
            dry_run=True,
        ),
        digest_settings=digest_settings,
        distribution_settings=distribution_settings,
    )

    assert report["generated_dates"] == []
    assert distribution_called["value"] is False
    assert report["pushed"] is False


def test_publish_pipeline_writes_structured_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = _website_repo(tmp_path)
    digest_settings = _digest_settings(repo)
    distribution_settings = _distribution_settings(repo)
    report_dir = tmp_path / "reports"

    monkeypatch.setenv("BRIEF_PUBLISH_REPORT_DIR", str(report_dir))
    monkeypatch.setattr("app.research.publish_pipeline.create_generator_engine", lambda settings: object())
    monkeypatch.setattr(
        "app.research.publish_pipeline.execute_digest_generation",
        lambda **kwargs: {"mode": "daily", "generated_dates": [], "results": [{"date": "2026-03-12", "status": "skipped-weak", "reason": "weak"}]},
    )
    monkeypatch.setattr("app.research.publish_pipeline.execute_distribution_generation", lambda **kwargs: {})

    report = execute_publish(
        request=GeneratorRequest(
            mode="daily",
            target_date=None,
            start_date=None,
            end_date=None,
            force=False,
            dry_run=True,
        ),
        digest_settings=digest_settings,
        distribution_settings=distribution_settings,
    )

    assert report["report_path"]
    report_path = Path(report["report_path"])
    assert report_path.exists()
    assert report_path.parent == report_dir
    assert '"dry_run": true' in report_path.read_text(encoding="utf-8")


def test_publish_pipeline_blocks_daily_publish_when_candidate_preflight_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = _website_repo(tmp_path)
    digest_settings = _digest_settings(repo)
    distribution_settings = _distribution_settings(repo)

    monkeypatch.setattr("app.research.publish_pipeline.create_generator_engine", lambda settings: object())
    monkeypatch.setattr("app.research.publish_pipeline.ensure_clean_worktree", lambda repo_root: None)
    monkeypatch.setattr(
        "app.research.publish_pipeline._candidate_readiness",
        lambda **kwargs: {
            "evaluated": True,
            "minimum_required_items": 4,
            "enough_candidates": False,
            "error": "only 2 strong items found for 2026-03-12",
        },
    )

    with pytest.raises(BriefPublishError, match="only 2 strong items found"):
        execute_publish(
            request=GeneratorRequest(
                mode="daily",
                target_date=None,
                start_date=None,
                end_date=None,
                force=False,
                dry_run=False,
            ),
            digest_settings=digest_settings,
            distribution_settings=distribution_settings,
        )


def test_publish_pipeline_fails_before_mutation_when_repo_is_dirty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = _website_repo(tmp_path)
    digest_settings = _digest_settings(repo)
    distribution_settings = _distribution_settings(repo)

    monkeypatch.setattr(
        "app.research.publish_pipeline.ensure_clean_worktree",
        lambda repo_root: (_ for _ in ()).throw(BriefOpsError("dirty repo")),
    )
    monkeypatch.setattr("app.research.publish_pipeline.create_generator_engine", lambda settings: object())

    with pytest.raises(BriefOpsError):
        execute_publish(
            request=GeneratorRequest(
                mode="daily",
                target_date=None,
                start_date=None,
                end_date=None,
                force=False,
                dry_run=False,
            ),
            digest_settings=digest_settings,
            distribution_settings=distribution_settings,
        )
