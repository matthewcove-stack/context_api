# AGENTS.md

Codex guidance for this repo.

## What this repo is
Research ingestion, cited context packs and reviewed Lambic Brief publishing.
Projects/Tasks mirroring is maintained legacy functionality. Preserve v1/v2 contracts.

## Current phase focus
Research reliability and measured usefulness, as recorded in `docs/current_state.md`.
Do not treat historical phase lists as instructions to grow the voice/Notion product.
Do not lower editorial/source thresholds to fill dates or claim new publication
until a reviewed issue is visible in the production feed.

## Quick commands
- Setup: `cp .env.example .env`
- Run: `docker compose up --build`
- Tests: `make test` (uses a disposable `context_test` Postgres instance)

Tests fail closed when `DATABASE_URL` names a non-test database. Do not run raw
`docker compose run --rm api pytest` against the persistent `context` database.

## Required env vars
- `DATABASE_URL`
- `CONTEXT_API_TOKEN`

## New env vars (Phase 3)
- `OPENAI_API_KEY` (or provider key)
- `OPENAI_MODEL` (e.g. "gpt-4.1-mini" or chosen model)
- Optional:
  - `INTEL_FETCH_MAX_BYTES` (default 2_000_000)
  - `INTEL_FETCH_TIMEOUT_S` (default 20)
  - `INTEL_HOST_THROTTLE_MS` (default 1200)

## Safe to edit
- `app/`
- `scripts/`
- `tests/`
- `docs/`
- `README.md`

## Avoid or be careful
- `docker-compose.yml` unless needed for behaviour changes
- Alembic: prefer generated migrations and keep them small and reviewable
- Do not modify /v1 endpoints or response shapes


## Phase 4 (ChatGPT Actions)
- Files under adapters/chatgpt_actions/ are used to configure a Custom GPT Action.
- docs/deployment/cloudflare_tunnel.md describes the recommended HTTPS exposure path.
