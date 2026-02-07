# AGENTS.md

Codex guidance for this repo.

## What this repo is
FastAPI service that mirrors Projects and Tasks into Postgres and serves compact search results.

MVP priority: Intel Digest connector and compact Context Packs for LLM reasoning using stored Intel artifacts.
We ship Option B: Intel-only packs under /v2, without touching existing /v1 projects/tasks behaviour.

## Current phase focus
Phase 3: URL ingestion + fetch/extract + LLM enrichment (outline/summary/signals) feeding existing /v2 retrieval.

## Quick commands
- Setup: `cp .env.example .env`
- Run: `docker compose up --build`
- Tests: `docker compose run --rm api pytest`

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
