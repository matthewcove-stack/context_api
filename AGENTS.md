# AGENTS.md

Codex guidance for this repo.

## What this repo is

FastAPI service that mirrors Projects and Tasks into Postgres and serves compact search results.

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
- `README.md`

## Avoid or be careful

- `migrations/` (if present; prefer generated tooling)
- `docker-compose.yml` unless needed for behavior changes

## Contracts

- JSON schemas live in `..\notion_assistant_contracts\schemas\v1\`.
- Examples live in `..\notion_assistant_contracts\examples\`.
