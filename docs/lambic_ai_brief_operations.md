# Lambic AI Brief Operations

## Purpose

This runbook covers the production publish path for the Lambic AI Brief.

The Brief is a two-repo system:

- `context_api` owns research ingestion, document enrichment, daily issue generation, and publish orchestration.
- `lambic_labs_website` owns the public static routes, archive UX, feeds, subscription surfaces, analytics wiring, and production deploy.

## Preconditions

The Brief publish depends on the research corpus already being populated for the target UTC day.

Required runtime:

- `DATABASE_URL`
- `OPENAI_API_KEY`
- `CONTEXT_API_TOKEN`
- `BRIEF_WEBSITE_REPO`
- `DAILY_DIGEST_GIT_REMOTE`
- `DAILY_DIGEST_GIT_BRANCH`

Recommended runtime:

- `BRIEF_PUBLISH_ENV=prod`
- `DAILY_DIGEST_TOPIC_KEY=ai_research`
- `BRIEF_PUBLISH_REPORT_DIR=/path/to/report-output`

## Canonical publish command

```powershell
python scripts/publish_lambic_ai_brief.py --mode daily
```

Backfill examples:

```powershell
python scripts/publish_lambic_ai_brief.py --mode backfill-range --start-date 2026-03-01 --end-date 2026-03-07
python scripts/publish_lambic_ai_brief.py --mode backfill-missing --start-date 2026-03-01 --end-date 2026-03-07
```

Dry-run:

```powershell
python scripts/publish_lambic_ai_brief.py --mode daily --dry-run
```

Optional structured report output:

- set `BRIEF_PUBLISH_REPORT_DIR` to write one JSON publish report per run
- set `BRIEF_PUBLISH_REPORT_PATH` to force one exact output path

## What the publish command does

1. Validates the website repo path and required directories.
2. Verifies publish runtime configuration and database reachability.
3. For daily mode, checks that enough strong candidate documents exist before mutation.
4. For live publish, verifies the website repo worktree is clean.
5. Generates daily Brief issue artifacts into `apps/web/content/research-digests/`.
6. Regenerates derivative assets into `apps/web/content/research-digest-assets/`.
7. Regenerates weekly artifacts into `apps/web/content/research-weekly/`.
8. Validates website research artifacts.
9. Regenerates RSS feeds.
10. Runs the website build.
11. Commits all generated website outputs in one commit.
12. Pushes once to the configured website branch.

Dry-run performs the same generation and validation steps inside a temporary copy of the website repo, so the real worktree stays unchanged.
Each run can also emit a structured JSON report with preflight, per-date outcomes, generated files, and postflight checks.

## Scheduler contract

The supported scheduler contract is:

- trigger the canonical publish command after research ingestion has completed for the prior UTC day
- run on the production host or a self-hosted runner that has access to:
  - the research database
  - the `context_api` runtime env
  - the checked-out `lambic_labs_website` repo
  - git credentials for the website repo

Recommended timing:

- schedule research ingestion first
- schedule Brief publish after the ingestion window has finished

The repository also includes a sample scheduled GitHub Actions workflow for self-hosted runners.

## Expected outputs

Published website content lives in:

- `apps/web/content/research-digests/`
- `apps/web/content/research-digest-assets/`
- `apps/web/content/research-weekly/`
- `apps/web/public/brief/feed.xml`
- `apps/web/public/brief/weekly/feed.xml`

## Failure handling

### Dirty website repo

Cause:

- manual edits or incomplete prior publish left the website repo dirty

Action:

- inspect `git status` in the website repo
- either commit/reset the unrelated changes manually or move them out of the way
- rerun publish

### Daily issue skipped as weak

Cause:

- not enough strong source material passed candidate selection and quality gates

Action:

- confirm ingestion succeeded for the target day
- review the latest research documents and source quality
- rerun later if more material is expected

### Website validation/build failure

Cause:

- generated content failed schema validation
- feed generation or static build failed

Action:

- rerun with `--dry-run` to reproduce without mutating the website repo
- inspect the failing generated artifact in the temporary workspace or local website repo copy
- fix the generator or website validation expectation, then rerun

### Push failure

Cause:

- remote rejection, network failure, or missing credentials

Action:

- inspect the website repo worktree
- if the commit succeeded locally but push failed, resolve credentials/remote state and push manually or rerun after cleaning up

## Recovery checks

After a successful live publish:

- the website repo worktree should be clean
- the expected daily digest file should exist for the target date
- derivative asset and weekly files should be present when applicable
- the website repo branch should contain exactly one publish commit for the run
