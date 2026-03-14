# Lambic AI Brief Generator

This pipeline generates daily Lambic AI Brief issues from the `ai_research` corpus and writes them into the website repo as static JSON artifacts.

## Entrypoint

```powershell
python scripts/generate_daily_research_digest.py --mode daily
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

## Required runtime

- `DATABASE_URL`
- `OPENAI_API_KEY`
- `CONTEXT_API_TOKEN`
- `DAILY_DIGEST_OUTPUT_REPO`

Recommended defaults are defined in `.env.example`.

## Auto-publish behavior

- The generator writes one JSON file per day into `apps/web/content/research-digests/` in the website repo.
- Daily generation expands its window to cover any unpublished gap, so skipped low-signal days roll into the next published issue instead of creating blind spots.
- It validates the website build before committing.
- It commits and pushes directly to the configured website branch when generation succeeds.
- It refuses to auto-commit if the website repo already has uncommitted changes.

## Backfill notes

- Backfill is bounded by the earliest digestable date in the research corpus.
- Existing digest files are treated as authoritative for `backfill-missing`.
- Weak historical days are skipped instead of padded with low-signal content.

## Suggested Windows Task Scheduler command

```powershell
cd C:\Users\Matth\Documents\workspace\brain_os_project\context_api
python scripts/generate_daily_research_digest.py --mode daily
```
