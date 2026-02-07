# AGENTS.md

Codex guidance for this repo.

## What this repo is

FastAPI service that mirrors Projects and Tasks into Postgres and serves compact search results.

NEW (MVP priority): add an Intel Digest connector and serve compact Context Packs for LLM reasoning
using stored Intel artifacts. For MVP we will ship Option B: Intel-only packs under /v2, without
touching the existing /v1 projects/tasks behavior.

## Quick commands

- Setup: `cp .env.example .env`
- Run: `docker compose up --build`
- Tests: `docker compose run --rm api pytest`

## Required env vars

- `DATABASE_URL`
- `CONTEXT_API_TOKEN`

## Safe to edit

- `app/`
- `scripts/`
- `tests/`
- `docs/`
- `README.md`

## Avoid or be careful

- `docker-compose.yml` unless needed for behavior changes
- Alembic: prefer generated migrations and keep them deterministic

## Contracts

- JSON schemas live in `..\notion_assistant_contracts\schemas\v1\` (v1 only).
- For MVP /v2 (Intel), contracts live in this repo under `docs/contracts/` until we decide to promote
  them to notion_assistant_contracts.

## MVP endpoints (Option B)

- `POST /v2/context/pack` (intel-only)
- `GET  /v2/intel/articles/{id}/outline`
- `POST /v2/intel/articles/{id}/sections`
- `POST /v2/intel/articles/{id}/chunks:search`
- `POST /v2/intel/ingest` (internal/admin; fixtures first)

## Phase discipline

Implement ONLY the requested phase in `docs/phases.md`. Update `docs/current_state.md`
(authoritative) and mirror changes into `README.md`.
