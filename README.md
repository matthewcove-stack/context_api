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

## Research Phase 1 ingestion
- `POST /v2/research/sources/upsert`
- `POST /v2/research/sources/bootstrap`
- `GET /v2/research/sources?topic_key=<topic>`
- `POST /v2/research/ingest/run`
- `GET /v2/research/ingest/runs/{run_id}`
- `GET /v2/research/bootstrap/status?topic_key=<topic>`

## Research Phase 4 retrieval
- `POST /v2/research/context/pack`
- `POST /v2/research/documents/{document_id}/chunks:search`
- `GET /v2/research/topics`
- `GET /v2/research/topics/search?query=<text>`
- `GET /v2/research/topics/{topic_key}`
- `GET /v2/research/topics/{topic_key}/documents`
- `POST /v2/research/topics/{topic_key}/summarize`

## Research Phase 5 scoring + ops
- `POST /v2/research/retrieval/feedback`
- `GET /v2/research/ops/summary?topic_key=<topic>`
- `GET /v2/research/ops/sources?topic_key=<topic>&limit=<n>`
- `GET /v2/research/ops/documents?topic_key=<topic>`
- `GET /v2/research/ops/storage?topic_key=<topic>`
- `GET /v2/research/ops/progress?topic_key=<topic>&run_limit=<n>`
- `GET /v2/research/ops/dashboard` (browser UI; bearer token + default topic are bootstrapped from server config)
- `POST /v2/research/sources/{source_id}/disable`
- `POST /v2/research/sources/{source_id}/enable`
- `POST /v2/research/documents/{document_id}/suppress`
- `POST /v2/research/documents/{document_id}/unsuppress`
- `POST /v2/research/governance/redact`
- `GET /v2/research/review/queue?topic_key=<topic>&limit=<n>`

## Research Phase 6 hardening controls
- `RESEARCH_SOURCE_FAILURE_THRESHOLD` (default `3`)
- `RESEARCH_SOURCE_COOLDOWN_MINUTES` (default `60`)
- `RESEARCH_RUN_MAX_NEW_ITEMS` (default `0` = unbounded)
- `RESEARCH_SCORE_WEIGHT_LEXICAL` (default `0.45`)
- `RESEARCH_SCORE_WEIGHT_EMBEDDING` (default `0.35`)
- `RESEARCH_SCORE_WEIGHT_RECENCY` (default `0.15`)
- `RESEARCH_SCORE_WEIGHT_SOURCE` (default `0.05`)
- Runbook: `docs/research_operations.md`
- Retention utility: `python -m app.research.retention --topic-key <topic> --older-than-days 30`

## Worker
- `docker compose run --rm api python -m app.intel.worker --once`
- `docker compose run --rm api python -m app.research.worker --once`
- Production retrieval quality requires `OPENAI_API_KEY` and `RESEARCH_EMBEDDING_MODEL` (default `text-embedding-3-small`).
- Hash embeddings remain available only when `RESEARCH_ALLOW_HASH_EMBEDDINGS=true` is set explicitly for dev/test.

## Research digest generator
- Daily digest script: `python scripts/generate_daily_research_digest.py --mode daily`
- Backfill missing days: `python scripts/generate_daily_research_digest.py --mode backfill-missing --start-date YYYY-MM-DD --end-date YYYY-MM-DD`
- Runbook: `docs/research_digest_generator.md`

## ChatGPT Actions
- Setup guide: `docs/chatgpt_actions_setup.md`

## Codex MCP bridge (starter)
- Spec: `docs/contracts/mcp_bridge_v1.md`
- Server entrypoint: `scripts/run_mcp_bridge.py`
- Runtime:
  - `CONTEXT_API_BASE_URL` (default `http://localhost:8001`)
  - `CONTEXT_API_TOKEN` (required)
  - `MCP_BRIDGE_TIMEOUT_S` (default `20`)
  - `MCP_BRIDGE_TRANSPORT` (`stdio` or `sse`, default `stdio`)
- Local run:
  - `python scripts/run_mcp_bridge.py --transport stdio`
- Codex CLI wiring example:
  - `codex mcp add context-api-research -- python C:\path\to\context_api\scripts\run_mcp_bridge.py --transport stdio`

## Codex MCP ops bridge (write-lite)
- Spec: `docs/contracts/mcp_ops_bridge_v1.md`
- Server entrypoint: `scripts/run_mcp_ops_bridge.py`
- Runtime:
  - `MCP_OPS_ENABLED=true` (required)
  - `CONTEXT_API_BASE_URL` (default `http://localhost:8001`)
  - `CONTEXT_API_TOKEN` (required)
  - `MCP_BRIDGE_TIMEOUT_S` (default `20`)
  - `MCP_BRIDGE_TRANSPORT` (`stdio` or `sse`, default `stdio`)
- Local run:
  - `python scripts/run_mcp_ops_bridge.py --transport stdio`
- Codex CLI wiring example:
  - `codex mcp add context-api-research-ops -- python C:\path\to\context_api\scripts\run_mcp_ops_bridge.py --transport stdio`

## Quick commands
- Setup: `python scripts/sync_runtime_env.py` or `cp .env.example .env`
- Run: `make up` (now always includes the edge overlay so `http://context-api.localhost` stays routed through Traefik)
- Tests: `docker compose run --rm api pytest`
- Smoke loop (PowerShell): `powershell -ExecutionPolicy Bypass -File scripts/bootstrap_smoke.ps1 -BaseUrl http://localhost:8001 -Token change-me -TopicKey smoke_topic -FeedUrl https://example.com/feed`
- Warning: if you start the API with plain `docker compose -f docker-compose.yml up`, the app now logs an explicit warning that edge routing is disabled and `context-api.localhost` will not work until it is started with `compose.edge.yml`


## ChatGPT integration (Custom GPT + Actions)
- See docs/chatgpt_actions_setup.md
- OpenAPI schema: adapters/chatgpt_actions/openapi.yaml


## Health endpoints
- `GET /health` liveness probe (no auth)
- `GET /ready` readiness probe (checks DB)

## Edge Dev
- `make dev`
- `make up`
- `http://context-api.localhost`
- `docs/current_state.md` (authoritative)
- `docs/edge_integration.md`

## Runtime alignment
- `scripts/sync_runtime_env.py` copies the Brain OS bearer token, OpenAI key, embedding config, and persistent Postgres path from `../brain_os/.env` into `context_api/.env`.
- `make dev` and `make up` run that sync step first, then launch Docker with `--env-file .env`.
- The API refuses to start when `CONTEXT_API_EXPECT_PERSISTENT_CORPUS=true` and the connected corpus is unexpectedly small. This prevents silently booting against a fresh empty local Postgres volume.

