# Lambic AI Brief Generator

This pipeline generates daily Lambic AI Brief issues from the `ai_research` corpus and writes them into the website repo as static JSON artifacts.

The canonical production command is now the publish orchestrator, which also refreshes derivative distribution assets, weekly roundups, feeds, and website validation in one run.

## Entrypoint

```powershell
python scripts/publish_lambic_ai_brief.py --mode daily
```

## Modes

- `--mode daily`
  - Generates the digest for the previous UTC day by default.
- `--mode backfill-range --start-date YYYY-MM-DD --end-date YYYY-MM-DD`
  - Generates digests for every eligible date in the range.
- `--mode backfill-missing --start-date YYYY-MM-DD --end-date YYYY-MM-DD`
  - Generates only missing dates in the range.

Optional flags:

- `--date YYYY-MM-DD`
- `--force`
- `--dry-run`

Optional report env:

- `BRIEF_PUBLISH_REPORT_DIR`
- `BRIEF_PUBLISH_REPORT_PATH`

## Required runtime

- `DATABASE_URL`
- `OPENAI_API_KEY`
- `CONTEXT_API_TOKEN`
- `BRIEF_WEBSITE_REPO`

Recommended defaults are defined in `.env.example`.

## Publish behavior

- The publish command writes one JSON file per day into `apps/web/content/research-digests/` in the website repo.
- It then refreshes:
  - `apps/web/content/research-digest-assets/`
  - `apps/web/content/research-weekly/`
  - `apps/web/public/brief/feed.xml`
  - `apps/web/public/brief/weekly/feed.xml`
- Daily generation expands its window to cover any unpublished gap, so skipped low-signal days roll into the next published issue instead of creating blind spots.
- It validates website research artifacts, regenerates feeds, runs the website build, commits all generated website outputs in one commit, and pushes once.
- It refuses to publish if the website repo already has uncommitted changes.
- For daily mode it checks database reachability and candidate sufficiency before mutating the website repo.
- `--dry-run` executes the full generation and validation flow inside a temporary workspace copy, leaving the real repo untouched.
- A structured JSON report can be written for each run for scheduler or operator inspection.

## Backfill notes

- Backfill is bounded by the earliest digestable date in the research corpus.
- Existing digest files are treated as authoritative for `backfill-missing`.
- Weak historical days are skipped instead of padded with low-signal content.

## Supporting commands

```powershell
cd C:\Users\Matth\Documents\workspace\brain_os_project\context_api
python scripts/generate_daily_research_digest.py --mode daily
python scripts/generate_research_distribution_assets.py --mode all
```

## Suggested scheduler command

```powershell
cd C:\Users\Matth\Documents\workspace\brain_os_project\context_api
python scripts/publish_lambic_ai_brief.py --mode daily
```
