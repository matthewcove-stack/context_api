# context_api

## What works today
- FastAPI + Postgres + Alembic
- Authenticated v1 endpoints for searching mirrored Projects/Tasks
- Intel fixture ingestion + /v2 Context Pack retrieval with progressive disclosure endpoints
- Docker quickstart and tests exist

## MVP priority (now)
Add URL ingestion with fetch/extract and LLM enrichment, feeding the existing intel-only /v2 Context Pack.

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

## Next to implement (Phase 3)
- `POST /v2/intel/ingest_urls` to queue URL ingestion jobs.
- Worker process to fetch/extract/sectionise and run LLM enrichment.
- `GET /v2/intel/articles/{article_id}` to read status and outputs.

## Quick commands
- Setup: `cp .env.example .env`
- Run: `docker compose up --build`
- Tests: `docker compose run --rm api pytest`
