# context_api — Phases

## Phase 0 (done)
- Basic mirrored data model for projects/tasks
- Search endpoints and dockerised tests
- Optional sync script scaffolding

## Phase 1 (supporting BrainOS)
- Ensure search endpoints cover the fields needed by intent_normaliser for task/project resolution.
- Ensure sync script can run deterministically and safely (no partial writes).

## Phase 2 (MVP priority) — Intel connector + Context Packs (Option B)
Goal: ship intel-only Context Pack retrieval and progressive disclosure under /v2 without altering /v1.

Deliverables:
- Alembic migration(s) adding intel tables:
  - intel_articles
  - intel_article_sections
  - (optional) intel_article_chunks
- Deterministic fixture ingestion:
  - checked-in fixtures under tests/fixtures/intel/
  - scripts/ingest_intel_fixtures.py (or equivalent)
  - `POST /v2/intel/ingest` to ingest fixtures into Postgres
- Retrieval:
  - `POST /v2/context/pack` returns bounded pack with citations, confidence, next_action, and trace
- Expansion:
  - outline + sections + chunks:search endpoints
- Tests:
  - ingest fixture -> /context/pack -> expansion endpoints assertions

Exit criteria:
- `docker compose run --rm api pytest` passes
- `docker compose up --build` serves /v1 as before AND /v2 intel endpoints
- `docs/current_state.md` and README updated

## Phase 3 (later) — Merge packs across domains (Option A)
- Extend /v2/context/pack to merge projects/tasks + intel with routing and namespaces
- Consider promoting /v2 schemas to notion_assistant_contracts

## Phase 4 (later) — Sophistication
- hierarchical summaries (RAPTOR-like)
- corrective retrieval / query rewriting loops
- MCP adapter around the HTTP endpoints
