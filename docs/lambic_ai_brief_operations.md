# Lambic AI Brief Operations

## Purpose

This runbook covers the production publish path for the Lambic AI Brief.
For a visual end-to-end map, see `docs/lambic_ai_brief_pipeline_diagrams.md`.

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
- `DAILY_DIGEST_OPENAI_TIMEOUT_S=180`
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
5. Generates a reported draft, runs structural and anti-AI review, and checks it against recent issues.
6. Fails closed if the revised issue still contains blocked house-style patterns, duplication, unfinished prose, or an unspecific editorial watch item.
7. Writes passing daily Brief artifacts and their `editorialReview` record into `apps/web/content/research-digests/`.
8. Regenerates derivative assets into `apps/web/content/research-digest-assets/`.
9. Regenerates weekly artifacts into `apps/web/content/research-weekly/`.
10. Validates website research artifacts.
11. Regenerates RSS feeds.
12. Runs the website build.
13. Commits all generated website outputs in one commit.
14. Pushes once to the configured website branch.

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

Production scheduling is owned by the `brain_os` repository's Lambic AI Brief workflow because that repository has the live Lambic Local 1 host runner. The scheduled run calls the host runner script so publishing happens beside the production research database and checked-out website repo.

This repository still contains the generator, publish scripts, and manual workflow dispatch support for dry-runs and one-off publishes. Use `backfill-missing` with explicit `start_date` and `end_date` to catch up missed publication windows.

For Lambic Local 1 host scheduling, use:

```bash
cd /srv/lambic/apps/brainos-workspace/context_api
./scripts/run_lambic_brief_publish_daily.sh
```

The host runner script:

- reads BrainOS runtime secrets from `/srv/lambic/apps/brainos-workspace/brain_os/.env`
- resolves `brainos_context_postgres` container IP for `DATABASE_URL`
- maps `CONTEXT_API_BEARER_TOKEN` to `CONTEXT_API_TOKEN`
- points publish output to `/srv/lambic/apps/lambic-labs-site`
- bootstraps a local `.venv_publish` and installs `requirements.txt` on first run
- reconciles the curated source list, disables replaced and private-address sources, and repairs up to 250 recent missing OpenAI embeddings before generation
- serializes publish attempts with `flock`, so GitHub Actions and the host fallback cannot mutate the website checkout concurrently
- writes structured success or blocked-preflight reports under `/srv/lambic/logs/brainos-reports` by default
- runs `daily --allow-skipped-weak`, covering the period since the last published issue
- withholds issues that fail the normal gates, recording the reason without lowering item/source requirements
- stops after a provider error; it does not retry each date or reinterpret quota exhaustion as a lack of news

### Credit or provider failure

Repair prints a redacted JSON record with `status: blocked-provider`, the provider
code, completed/remaining counts and an operator action. Exit 78 means account
credit, limit or permission failure; exit 75 means temporary rate/availability.
Long-running embedding workers cool down for 15 minutes on an account failure,
or 60–3600 seconds for transient failures, then allow a new attempt. Raw provider
prose, keys and request headers are not included in this diagnostic.

On 30 September 2026 the live provider returned `credit_balance_exhausted` and
the latest public issue was dated 18 September. Restore account credit first;
rotating an otherwise valid key does not solve exhausted credit. After that,
run bounded repair batches, inspect the remaining missing-model/chunk backlog,
and resume normal reviewed publishing. Do not change to hash embeddings in production.

The BrainOS Actions workflow independently checks the public feed after every
scheduled run and fails if the latest issue is older than seven days. This is a
diagnostic threshold, not an instruction to fill the archive with weak material.

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
