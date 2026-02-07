# context_api

## What works today
- FastAPI + Postgres + Alembic
- Authenticated v1 endpoints for searching mirrored Projects/Tasks
- Docker quickstart and tests exist

## MVP priority (now)
Implement Intel Digest + Context Pack serving (Option B: intel-only packs under /v2).

This MUST NOT break or alter existing /v1 projects/tasks behaviour.

## Planned /v2 API surface (MVP)

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

### Ingestion (internal/admin)
- `POST /v2/intel/ingest`
  - MVP supports deterministic fixture ingestion (checked into repo)
  - URL fetching can be added later

## Storage (MVP)
Add new intel tables (Postgres):
- intel_articles
  - metadata + derived (summary, outline, signals, outbound links)
- intel_article_sections
  - lossless section text (for expansion)
Optionally (if needed in MVP):
- intel_article_chunks (skip if section-level search is enough)

## Retrieval behaviour (MVP)
Default:
- Return only signals + short summary + citations (no raw full text).
- Use Postgres full-text search + a simple re-ranker.
- Enforce a token/size budget for the pack.

Confidence gate:
- Return retrieval_confidence and next_action.
- If confidence is low, suggest refine_query or expand_sections.

## Verification commands
Must run in docker compose:
- `docker compose up --build` (run)
- `docker compose run --rm api pytest` (tests)

## Drift prevention
Any change to /v2 endpoints, schemas, or storage format must update this file and be mirrored in README.
