# context_api

## What works today
- FastAPI + Postgres + Alembic
- Authenticated v1 endpoints for searching mirrored Projects/Tasks
- Intel fixture ingestion + /v2 Context Pack retrieval with progressive disclosure endpoints
- URL ingestion + worker-based fetch/extract/enrich pipeline for intel articles
- Docker quickstart and tests exist

## MVP priority (now)
URL ingestion with fetch/extract and LLM enrichment feeds the existing intel-only /v2 Context Pack.

This MUST NOT break or alter existing /v1 projects/tasks behaviour.

## Implemented /v2 API surface (stable)

### Context Pack
- `POST /v2/context/pack`
  - Input:
    - query: string
    - topics?: string[]
    - token_budget?: int
    - recency_days?: int
    - max_items?: int
  - Output:
    - pack:
      - items[]: { article_id, title, url, signals[], summary, citations[] }
    - retrieval_confidence: "high" | "med" | "low"
    - next_action: "proceed" | "refine_query" | "expand_sections"
    - trace: { trace_id, retrieved_article_ids[], timing_ms }

### Progressive disclosure
- `GET /v2/intel/articles/{article_id}/outline`
- `POST /v2/intel/articles/{article_id}/sections`
- `POST /v2/intel/articles/{article_id}/chunks:search`

### Ingestion (fixtures)
- `POST /v2/intel/ingest` ingests checked-in fixtures into Postgres (deterministic).

## URL ingestion + status
- `POST /v2/intel/ingest_urls` queues URL ingestion jobs (fetch/extract/enrich).
- `GET /v2/intel/articles/{article_id}` returns status + compact outputs.

## Worker
- `docker compose run --rm api python -m app.intel.worker --once`

## ChatGPT Actions
- Setup guide: `docs/chatgpt_actions_setup.md`

## Quick commands
- Setup: `cp .env.example .env`
- Run: `docker compose up --build`
- Tests: `docker compose run --rm api pytest`


## ChatGPT integration (Custom GPT + Actions)
- See docs/chatgpt_actions_setup.md
- OpenAPI schema: adapters/chatgpt_actions/openapi.yaml


## Health endpoints
- `GET /health` liveness probe (no auth)
- `GET /ready` readiness probe (checks DB)
