from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Sequence


LEGACY_DEV_WEBSITE_REPO = Path(r"C:\Users\Matth\Documents\workspace\lambic_labs_website")
_NPM_INSTALL_CACHE: set[Path] = set()


class BriefOpsError(RuntimeError):
    pass


@dataclass(frozen=True)
class WebsiteRepoPaths:
    repo_root: Path
    web_app_dir: Path
    digest_dir: Path
    assets_dir: Path
    weekly_dir: Path
    daily_feed_path: Path
    weekly_feed_path: Path


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y"}


def resolve_website_repo_paths(
    *,
    digest_dir: str = "apps/web/content/research-digests",
    assets_dir: str = "apps/web/content/research-digest-assets",
    weekly_dir: str = "apps/web/content/research-weekly",
) -> WebsiteRepoPaths:
    repo_value = os.getenv("BRIEF_WEBSITE_REPO", "").strip()
    publish_env = os.getenv("BRIEF_PUBLISH_ENV", "prod").strip().lower() or "prod"
    if repo_value:
        repo_root = Path(repo_value).expanduser()
    elif publish_env == "dev":
        repo_root = LEGACY_DEV_WEBSITE_REPO
    else:
        raise BriefOpsError("BRIEF_WEBSITE_REPO is required when BRIEF_PUBLISH_ENV is not set to dev")

    web_app_dir = repo_root / "apps" / "web"
    resolved = WebsiteRepoPaths(
        repo_root=repo_root,
        web_app_dir=web_app_dir,
        digest_dir=repo_root / Path(digest_dir),
        assets_dir=repo_root / Path(assets_dir),
        weekly_dir=repo_root / Path(weekly_dir),
        daily_feed_path=web_app_dir / "public" / "brief" / "feed.xml",
        weekly_feed_path=web_app_dir / "public" / "brief" / "weekly" / "feed.xml",
    )
    validate_website_repo_paths(resolved)
    return resolved


def validate_website_repo_paths(paths: WebsiteRepoPaths) -> None:
    if not paths.repo_root.exists():
        raise BriefOpsError(f"Website repo does not exist: {paths.repo_root}")
    if not (paths.repo_root / ".git").exists():
        raise BriefOpsError(f"Website repo is missing .git metadata: {paths.repo_root}")
    if not paths.web_app_dir.exists():
        raise BriefOpsError(f"Website app directory is missing: {paths.web_app_dir}")
    package_json = paths.web_app_dir / "package.json"
    if not package_json.exists():
        raise BriefOpsError(f"Website app package.json is missing: {package_json}")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def run_git_command(repo: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def list_worktree_changes(repo: Path) -> List[str]:
    result = run_git_command(repo, ["status", "--short"])
    if result.returncode != 0:
        raise BriefOpsError(result.stderr.strip() or "Unable to inspect website repo status")
    return [line for line in result.stdout.splitlines() if line.strip()]


def ensure_clean_worktree(repo: Path) -> None:
    changes = list_worktree_changes(repo)
    if changes:
        raise BriefOpsError("Website repo has uncommitted changes; refusing to publish")


def stage_publish_outputs(repo: Path, relative_paths: Sequence[str]) -> None:
    if not relative_paths:
        return
    result = run_git_command(repo, ["add", "-A", *relative_paths])
    if result.returncode != 0:
        raise BriefOpsError(result.stderr.strip() or "Unable to stage generated website outputs")


def list_staged_changes(repo: Path) -> List[str]:
    result = run_git_command(repo, ["diff", "--cached", "--name-only"])
    if result.returncode != 0:
        raise BriefOpsError(result.stderr.strip() or "Unable to inspect staged website outputs")
    return [line for line in result.stdout.splitlines() if line.strip()]


def commit_and_push(repo: Path, *, remote: str, branch: str, message: str) -> None:
    commit_result = run_git_command(repo, ["commit", "-m", message])
    if commit_result.returncode != 0:
        raise BriefOpsError(commit_result.stderr.strip() or commit_result.stdout.strip() or "git commit failed")
    push_result = run_git_command(repo, ["push", remote, branch])
    if push_result.returncode != 0:
        raise BriefOpsError(push_result.stderr.strip() or push_result.stdout.strip() or "git push failed")


def _ensure_npm_dependencies(workdir: Path, npm_executable: str) -> None:
    resolved = workdir.resolve()
    if resolved in _NPM_INSTALL_CACHE:
        return
    if (workdir / "node_modules" / ".bin").exists():
        _NPM_INSTALL_CACHE.add(resolved)
        return

    install_result = subprocess.run(
        [npm_executable, "ci"],
        cwd=workdir,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if install_result.returncode != 0:
        fallback_result = subprocess.run(
            [npm_executable, "install"],
            cwd=workdir,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if fallback_result.returncode != 0:
            raise BriefOpsError(fallback_result.stdout + "\n" + fallback_result.stderr)

    _NPM_INSTALL_CACHE.add(resolved)


def run_npm_script(workdir: Path, script: str) -> subprocess.CompletedProcess[str]:
    npm_executable = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm_executable:
        raise BriefOpsError("Unable to find npm or npm.cmd required for website validation")
    _ensure_npm_dependencies(workdir, npm_executable)
    result = subprocess.run(
        [npm_executable, "run", script],
        cwd=workdir,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise BriefOpsError(result.stdout + "\n" + result.stderr)
    return result


@contextmanager
def prepare_publish_workspace(paths: WebsiteRepoPaths, *, dry_run: bool) -> Iterator[WebsiteRepoPaths]:
    if not dry_run:
        yield paths
        return

    temp_root = Path(tempfile.mkdtemp(prefix="lambic-brief-publish-"))
    workspace_root = temp_root / paths.repo_root.name
    try:
        shutil.copytree(
            paths.repo_root,
            workspace_root,
            ignore=shutil.ignore_patterns(".git", "node_modules", ".next", "out"),
        )
        yield WebsiteRepoPaths(
            repo_root=workspace_root,
            web_app_dir=workspace_root / "apps" / "web",
            digest_dir=workspace_root / paths.digest_dir.relative_to(paths.repo_root),
            assets_dir=workspace_root / paths.assets_dir.relative_to(paths.repo_root),
            weekly_dir=workspace_root / paths.weekly_dir.relative_to(paths.repo_root),
            daily_feed_path=workspace_root / paths.daily_feed_path.relative_to(paths.repo_root),
            weekly_feed_path=workspace_root / paths.weekly_feed_path.relative_to(paths.repo_root),
        )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
