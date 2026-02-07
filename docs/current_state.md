# context_api — Current State (Authoritative for this repo)

## What works today
- FastAPI + Postgres + Alembic
- Authenticated v1 endpoints for searching mirrored Projects/Tasks
- Intel fixture ingestion + /v2 Context Pack retrieval with progressive disclosure endpoints
- URL ingestion + worker-based fetch/extract/enrich pipeline for intel articles
- Docker quickstart and tests exist

## MVP priority (now)
URL ingestion with fetch/extract and LLM enrichment is implemented and feeds the existing intel-only /v2 Context Pack.

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

### URL ingestion + LLM enrichment
- `POST /v2/intel/ingest_urls`:
  - accepts list of URLs; queues ingestion jobs; returns job_id/article_id per URL
- Status:
  - `GET /v2/intel/articles/{article_id}` returns job/status and includes enrichment outputs when ready

## Storage (MVP)
Current intel tables:
- intel_articles (signals/summary/outline/topics + fetch/extraction/enrichment metadata + status)
- intel_article_sections (content + FTS index)
- intel_ingest_jobs (queue for URL ingestion)

## Worker (Phase 3)
Run locally:
- `docker compose run --rm api python -m app.intel.worker --once`

## Actions integration (Phase 4)
ChatGPT Actions assets and docs are available:
- OpenAPI schema: adapters/chatgpt_actions/openapi.yaml (read-only endpoints)
- GPT instructions: adapters/chatgpt_actions/gpt_instructions.md
- Setup guide: docs/chatgpt_actions_setup.md
- Cloudflare Tunnel guide: docs/deployment/cloudflare_tunnel.md

## Drift prevention
Whenever code changes meaningfully affect:
- API contracts
- schemas or migrations
- verification commands
update this file and mirror in README.


## ChatGPT Actions integration (Plus plan)
- This service can be used as an external knowledge base for ChatGPT via a Custom GPT with Actions.
- See: docs/chatgpt_actions_setup.md and adapters/chatgpt_actions/
- Expose the API over HTTPS (recommended: Cloudflare Tunnel). See: docs/deployment/cloudflare_tunnel.md


## Health endpoints
- `GET /health` liveness probe (no auth)
- `GET /ready` readiness probe (checks DB)
