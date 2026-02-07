# Phase execution prompt (copy/paste into Codex)

You are implementing ONLY the requested phase from docs/phases.md.
Obey docs/codex_rules.md and the truth hierarchy: docs/current_state.md is authoritative.

## Requested phase
Phase 2 (MVP priority) — Intel connector + Context Packs (Option B)

## Requirements
- Do NOT modify /v1 behaviour or response schemas.
- Add /v2 intel ingestion + retrieval + expansion endpoints.
- Add Alembic migrations for new intel tables.
- Add deterministic fixtures under tests/fixtures/intel/ and an ingestion script.
- Add tests covering ingest + pack + expansion.
- Ensure everything runs in docker compose:
  - `docker compose up --build`
  - `docker compose run --rm api pytest`

## Output format
1) List files changed/added.
2) Commands run + results.
3) Any assumptions (only if necessary).
4) Update docs/current_state.md and mirror README.
