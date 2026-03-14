# context_api — Current State (Authoritative for this repo)

## What works today
- FastAPI + Postgres + Alembic.
- Authenticated `/v1` endpoints for mirrored Projects/Tasks sync + search.
- Authenticated `/v1` dashboard endpoints for Brain OS shell reads:
  - today dashboard
  - upcoming tasks
  - project workspace
  - inbox
  - daily and weekly reviews
- Intel fixture ingestion and intel URL ingestion.
- Worker-based fetch/extract/sectionise/enrich pipeline for intel articles.
- `/v2/context/pack` and progressive disclosure endpoints over intel content.
- Phase 1 research ingestion:
  - Source catalogue upsert/list under `/v2/research/sources*`.
  - Ingestion run queue/status under `/v2/research/ingest/*`.
  - Worker-driven source fetch/discovery with deterministic dedupe and raw payload storage.
- Phase 2 research extraction:
  - Worker extracts normalized text from fetched payloads.
  - Extraction provenance is persisted in `research_documents.extraction_meta`.
- Phase 3 chunking + embeddings:
  - Worker generates deterministic chunks from extracted text.
  - Chunk embeddings are persisted with model provenance.
- Phase 4 research retrieval:
  - `POST /v2/research/context/pack` returns bounded, citation-first retrieval packs.
  - `POST /v2/research/documents/{document_id}/chunks:search` supports progressive disclosure.
  - Retrieval queries are audited in `research_query_logs`.
- Phase 5 relevance + feedback + observability:
  - Retrieval uses hybrid scoring (`lexical`, `embedding`, `recency`, `source_weight`).
  - Feedback capture endpoint persists operator judgments.
  - Ops summary endpoint exposes ingestion/retrieval counters.
  - Source metrics endpoint exposes per-source failure/throughput status.
  - Governance controls:
    - source moderation endpoints (`enable`/`disable`)
    - document suppression endpoints (`suppress`/`unsuppress`)
    - redaction endpoint for raw payload retention hygiene
    - review queue endpoint for operator triage
  - Ingest-time junk suppression:
    - obvious login/pricing/sitemap/press-kit pages are suppressed before enrichment/embedding
    - suppressed documents are excluded from retrieval, digests, and topic views
- Phase 6 production hardening:
  - Source failure counters and automatic cooldown (`consecutive_failures`, `cooldown_until`).
  - Schedule enqueue honors cooldown to prevent hot-loop retries.
  - Run-level backpressure budget (`RESEARCH_RUN_MAX_NEW_ITEMS`) stops runaway ingestion growth.
  - PDF-aware extraction path for research documents (`application/pdf`).
  - Env-driven scoring weight knobs for relevance tuning.
- Bootstrap loop closure:
  - `POST /v2/research/sources/bootstrap` for source suggestion ingestion + optional run trigger.
  - `GET /v2/research/bootstrap/status` for latest onboarding/run rollup per topic.
  - `research_bootstrap_events` audit table for bootstrap requests/results.
- Dockerized test workflow (`docker compose run --rm api pytest`).

## Implemented in this phase
- New tables:
  - `research_sources`
  - `research_source_policies`
  - `research_ingestion_runs`
  - `research_documents`
- New worker behavior in `app.research.worker`:
  - claims queued runs
  - discovers candidate URLs from feeds/sitemaps/html listings
  - applies deterministic document identity + dedupe
  - fetches and stores raw payload + fetch metadata
  - extracts readable text with bounded extractor metadata
  - records run counters and bounded errors
- Added readiness endpoint:
  - `GET /ready`

## Implemented API surface (runtime)
### Existing `/v2` intel retrieval
- `POST /v2/context/pack`
- `GET /v2/intel/articles/{article_id}/outline`
- `POST /v2/intel/articles/{article_id}/sections`
- `POST /v2/intel/articles/{article_id}/chunks:search`

### Existing `/v2` intel ingestion
- `POST /v2/intel/ingest`
- `POST /v2/intel/ingest_urls`
- `GET /v2/intel/articles/{article_id}`

### New `/v2` research phase 1 ingestion
- `POST /v2/research/sources/upsert`
- `POST /v2/research/sources/bootstrap`
- `GET /v2/research/sources?topic_key=...`
- `POST /v2/research/ingest/run`
- `GET /v2/research/ingest/runs/{run_id}`
- `GET /v2/research/bootstrap/status?topic_key=...`

### New `/v2` research phase 4 retrieval
- `POST /v2/research/context/pack`
- `POST /v2/research/documents/{document_id}/chunks:search`

### New `/v2` research phase 5 governance/ops
- `POST /v2/research/retrieval/feedback`
- `GET /v2/research/ops/summary?topic_key=...`
- `GET /v2/research/ops/sources?topic_key=...&limit=...`
- `POST /v2/research/sources/{source_id}/disable`
- `POST /v2/research/sources/{source_id}/enable`
- `POST /v2/research/documents/{document_id}/suppress`
- `POST /v2/research/documents/{document_id}/unsuppress`
- `POST /v2/research/governance/redact`
- `GET /v2/research/review/queue?topic_key=...&limit=...`

### Existing `/v1` sync/search
- `POST /v1/projects/sync`
- `POST /v1/tasks/sync`
- `POST /v1/projects/search`
- `POST /v1/tasks/search`
- `GET /v1/dashboard/today`
- `GET /v1/dashboard/upcoming`
- `GET /v1/projects/{project_id}/workspace`
- `GET /v1/inbox`
- `GET /v1/reviews/daily`
- `GET /v1/reviews/weekly`

## Current storage
- `projects`
- `tasks`
- `intel_articles`
- `intel_article_sections`
- `intel_ingest_jobs`
- `research_sources`
- `research_source_policies`
- `research_ingestion_runs`
- `research_documents`
  - includes `extracted_text` and `extracted_at` (Phase 2)
- `research_chunks`
- `research_embeddings`
- `research_query_logs`
- `research_relevance_scores`
- `research_retrieval_feedback`
- `research_bootstrap_events`

## Current worker model
- Intel worker command:
  - `docker compose run --rm api python -m app.intel.worker --once`
- Research worker command:
  - `docker compose run --rm api python -m app.research.worker --once`

## Gaps against the research ingestion target
- Governance controls are baseline only:
  - allowlist and per-source rate controls exist
  - robots strict mode exists
  - source cooldown + run backpressure controls are implemented
  - DR runbook is documented in `docs/research_operations.md`

## Actions integration status
- ChatGPT Actions assets expose intel/research retrieval endpoints and optional onboarding endpoints (`/v2/research/sources/bootstrap`, `/v2/research/bootstrap/status`) for setup workflows:
  - `adapters/chatgpt_actions/openapi.yaml`
  - `adapters/chatgpt_actions/gpt_instructions.md`
- Codex MCP bridge starter exposes read-only retrieval tools (`search`, `fetch`):
  - `app/mcp_bridge/server.py`
  - `scripts/run_mcp_bridge.py`
  - Contract: `docs/contracts/mcp_bridge_v1.md`
- Separate Codex MCP ops bridge exposes write-lite onboarding tools:
  - `app/mcp_bridge_ops/server.py`
  - `scripts/run_mcp_ops_bridge.py`
  - Contract: `docs/contracts/mcp_ops_bridge_v1.md`
- HTTPS exposure guidance:
  - `docs/chatgpt_actions_setup.md`
  - `docs/deployment/cloudflare_tunnel.md`

## Health endpoints
- `GET /health` (liveness/readiness against DB)
- `GET /ready` (readiness against DB)
- `GET /version`

## Edge integration
- Entry service: `api` on `8001`
- Dev route: `http://context-api.localhost`
- Run with `make dev` using shared `edge` network and `compose.edge.yml`.

## Drift prevention
If changes affect API contracts, migrations, verification commands, or phase status:
- update this file first,
- then update `README.md` and supporting contract docs.
