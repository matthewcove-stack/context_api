# context_api — Phases

Truth: `docs/current_state.md` is authoritative for implemented behavior.

## Legacy phases (already shipped)
- Phase 0: `/v1` projects/tasks sync + search.
- Phase 2: intel fixtures + `/v2/context/pack` + expansion endpoints.
- Phase 3: URL ingestion worker (fetch/extract/sectionise/enrich) backed by Postgres jobs.
- Phase 4: ChatGPT Actions read-only adapter docs/assets.

## Research ingestion program phases

### Phase 0 — Contracts, guardrails, and wiring (docs + stubs)
Scope:
- Define the research ingestion architecture and contracts without changing runtime behavior.
- Add deterministic ID helpers and typed scaffolding for Phase 1.

Edit map:
- `docs/intent.md`
- `docs/current_state.md`
- `docs/phases.md`
- `docs/codex_rules.md`
- `docs/PHASE_EXECUTION_PROMPT.md`
- `docs/contracts/v2_research_*.md`
- `app/research/*` (stubs only)
- `tests/test_research_*.py` (unit-only)

Data migrations:
- None.

Local run:
- `docker compose up --build`

Verification:
- `docker compose run --rm api pytest`
- `bash scripts/edge_validate.sh`

Rollback:
- Revert docs/stub files only. No DB/API runtime rollback needed.

Definition of done:
- Authoritative docs describe the next phases and guardrails.
- Stub contracts and deterministic ID helpers exist and are tested.

### Phase 1 — Source catalogue + scheduler + dedupe + raw storage (implemented)
Scope:
- Introduce curated source registry, crawl policy, ingestion runs, and discovered items.
- Fetch newly discovered items with deterministic dedupe and raw payload persistence.

Edit map (planned):
- `alembic/versions/0004_*_research_catalog.py`
- `app/storage/schema.py`, `app/storage/db.py`
- `app/research/catalog.py`, `app/research/discovery.py`, `app/research/worker.py`
- `app/main.py` (`/v2/research/sources*`, `/v2/research/ingest*`)
- `tests/test_research_catalog*.py`, `tests/test_research_ingest*.py`

Data migrations (planned):
- `research_sources`
- `research_source_policies`
- `research_ingestion_runs`
- `research_documents` (seed/raw metadata only)

Local run:
- `docker compose up --build`
- `docker compose run --rm api python -m app.research.worker --once`

Verification:
- `docker compose run --rm api pytest`
- `docker compose run --rm api python -m app.research.worker --once`
- `bash scripts/edge_validate.sh`

Rollback:
- Feature-flag new endpoints off.
- Stop worker, downgrade migration to pre-phase revision if needed.

Definition of done:
- Source allowlist CRUD works.
- New item discovery is idempotent per canonical URL/external id.
- Raw fetch payload and run audit records are persisted.

### Phase 2 — Extraction and normalization (implemented)
Scope:
- Convert raw content into normalized extracted text and structured metadata.

Edit map (planned):
- `app/research/extract.py`
- `app/storage/db.py`, `app/storage/schema.py`
- `app/research/worker.py`
- extraction-focused tests

Data migrations (planned):
- Add extraction fields/state transitions to `research_documents`.

Local run:
- Same as Phase 1.

Verification:
- Deterministic extraction tests with local fixtures only.

Rollback:
- Keep raw payloads; reset document state to `fetched` and re-run.

Definition of done:
- Extracted text is persisted with provenance (`extraction_method`, timestamps, warnings).

### Phase 3 — Chunking + embedding + vector storage (implemented)
Scope:
- Add deterministic chunk generation and embeddings for retrievable units.

Edit map (planned):
- `alembic/versions/0006_*_research_chunks_embeddings.py`
- `app/research/chunking.py`, `app/research/embeddings.py`
- `app/storage/schema.py`, `app/storage/db.py`
- `app/research/worker.py`
- retrieval preparation tests

Data migrations (planned):
- `research_chunks`
- `research_embeddings` (vector and model metadata)

Local run:
- Existing compose stack; no new infra component unless required by approved migration plan.

Verification:
- Chunk ID determinism tests.
- Embedding write/read tests.

Rollback:
- Disable embed stage and keep extraction outputs.
- Recompute embeddings from chunk table when re-enabled.

Definition of done:
- Chunk IDs are stable across re-runs.
- Embeddings stored with `embedding_model_id` and provenance.

### Phase 4 — Context API retrieval endpoints + query logging (implemented)
Scope:
- Expose `/v2/research/*` retrieval endpoints and query audit logs.
- Keep `/v2/context/pack` compatibility while enabling research-backed retrieval.

Edit map (planned):
- `app/main.py`
- `app/models.py`
- `app/storage/db.py`
- `docs/contracts/v2_research_retrieval.md`
- `adapters/chatgpt_actions/openapi.yaml` (read-only additions if approved)

Data migrations (planned):
- `research_query_logs`
- optional `research_retrieval_feedback`

Verification:
- End-to-end retrieval tests with deterministic fixtures and mocked embeddings.

Rollback:
- Route retrieval back to intel-only selectors.

Definition of done:
- Retrieval returns bounded results with stable provenance pointers and trace IDs.

### Phase 5 — Relevance scoring + feedback loop + observability (implemented)
Scope:
- Baseline explainable scoring and operator feedback capture.
- Improve operational metrics for ingestion and retrieval quality.

Planned scoring baseline:
- lexical match + embedding similarity + recency decay + source weight + policy gates.

Definition of done:
- Score breakdown is stored and inspectable per document/query.
- Dashboards/queries can show ingestion failures, lag, and top sources.

### Phase 6 — Production hardening (implemented)
Scope:
- Rate controls, retry/backoff policy, backpressure, disaster recovery drills.

Definition of done:
- SLO/error-budget policy documented and exercised.
- Recovery runbooks validated in staging-like environment.

