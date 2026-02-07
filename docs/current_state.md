# context_api — Current State (Authoritative for this repo)

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
### URL ingestion + LLM enrichment
- `POST /v2/intel/ingest_urls`:
  - accepts list of URLs; queues ingestion jobs; returns job_id/article_id per URL
- Worker:
  - fetch (bounded), extract, sectionise
  - LLM enrichment produces: outline + summary + signals (each signal citeable to section_id)
  - stores results into intel_articles + intel_article_sections
- Status:
  - `GET /v2/intel/articles/{article_id}` returns job/status and includes enrichment outputs when ready

## Storage (MVP)
Current intel tables:
- intel_articles (signals/summary/outline/topics)
- intel_article_sections (content + FTS index)

Phase 3 extends intel_articles and adds intel_ingest_jobs to support URL ingestion and enrichment metadata.

## Drift prevention
Whenever code changes meaningfully affect:
- API contracts
- schemas or migrations
- verification commands
update this file and mirror in README.
