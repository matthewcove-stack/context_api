# context_api — Phases

## Phase 0 (done)
- Basic mirrored data model for projects/tasks
- Search endpoints and dockerised tests
- Optional sync script scaffolding

## Phase 1 (supporting BrainOS)
- Ensure search endpoints cover the fields needed by intent_normaliser for task/project resolution.
- Ensure sync script can run deterministically and safely (no partial writes).

## Phase 2 (MVP priority) — Intel connector + Context Packs (Option B) (done)
Goal: ship intel-only Context Pack retrieval and progressive disclosure under /v2 without altering /v1.

Deliverables:
- Alembic migration(s) adding intel tables:
  - intel_articles
  - intel_article_sections
- Deterministic fixture ingestion:
  - checked-in fixtures under tests/fixtures/intel/
  - util ingestion helper + `POST /v2/intel/ingest`
- Retrieval:
  - `POST /v2/context/pack` returns bounded pack with citations, confidence, next_action, and trace
- Expansion:
  - outline + sections + chunks:search endpoints
- Tests:
  - ingest fixture -> /context/pack -> expansion endpoints assertions

Exit criteria:
- `docker compose run --rm api pytest` passes
- /v1 behaviour unchanged

## Phase 3 (MVP priority) — URL ingestion + fetch/extract + LLM enrichment
Goal: accept a list of URLs, fetch and extract readable text, sectionise, run LLM enrichment
(outline + summary + signals with cite pointers), store results, and make them available via existing /v2 retrieval.

Deliverables:
- Alembic migration(s):
  - add intel_ingest_jobs table (Postgres-backed queue)
  - extend intel_articles for URL ingestion:
    - url_original, raw_html, extracted_text
    - fetch metadata (http_status, content_type, etag, last_modified)
    - extraction_meta (jsonb), enrichment_meta (jsonb)
    - status fields (queued/extracted/enriched/failed)
- New /v2 endpoints (must not touch /v1):
  - `POST /v2/intel/ingest_urls` (queues jobs, returns job_id/article_id per URL)
  - `GET /v2/intel/articles/{article_id}` (status + metadata; include summary/signals when ready)
  - (optional) `GET /v2/intel/ingest_jobs/{job_id}` (poll)
- Worker entrypoint (same repo):
  - `python -m app.intel.worker` (or equivalent)
  - polls jobs table; performs:
    1) URL canonicalisation + dedupe
    2) fetch (bounded, throttled)
    3) extract (trafilatura/readability fallback)
    4) sectionise (headings or paragraph buckets)
    5) LLM enrichment (strict JSON schema; no claims without cite pointer)
    6) store + update job status
- LLM integration:
  - provider via env vars (e.g. OPENAI_API_KEY, OPENAI_MODEL)
  - prompt versioning and schema validation (Pydantic)
  - bounded output enforcement (limits on counts/lengths)
- Tests:
  - unit tests: URL canonicalisation, bounds, schema validation
  - integration test: local HTTP fixture server (no live internet), mocked LLM client, end-to-end ingest -> pack retrieval
- Make targets (or equivalent documented commands):
  - `docker compose run --rm api pytest`
  - `docker compose run --rm api python -m app.intel.worker --once` (or documented worker run)
  - `docker compose up --build` (API)

Exit criteria:
- Fixture URL ingestion works end-to-end (via local test server)
- LLM enrichment output is stored and used by /v2/context/pack
- /v1 behaviour unchanged


## Phase 4 — ChatGPT Actions integration (deployment + OpenAPI assets)
Goal: make the knowledge base usable from ChatGPT UI (Plus plan) via a Custom GPT with Actions.

Deliverables:
- OpenAPI schema limited to read-only endpoints for /v2 context pack + expansion.
- Custom GPT instruction block that enforces 'pack first' behavior.
- Deployment guidance for public HTTPS via Cloudflare Tunnel.
- docker-compose override for cloudflared.

Exit criteria:
- Public URL reachable over HTTPS.
- Custom GPT can successfully call getContextPack and expansion endpoints using bearer auth.
