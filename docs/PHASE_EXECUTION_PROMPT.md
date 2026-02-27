# Phase Execution Prompt — Research Phase 1

You are implementing ONLY Phase 1 from `docs/phases.md`:

`Phase 1 — Source catalogue + scheduler + dedupe + raw storage`

Truth hierarchy:
1. `docs/current_state.md`
2. `docs/intent.md`
3. `docs/phases.md`
4. `README.md`
5. code

## Scope (must do)
- Add source catalogue and source policy persistence.
- Add ingestion run tracking and deterministic dedupe at item level.
- Add raw fetch storage metadata for newly discovered items.
- Add minimal `/v2/research/*` ingestion endpoints required by Phase 1 contracts.
- Add worker logic for discovery + fetch + persistence with safe retries.

## Scope (must NOT do)
- Do not implement chunk embeddings/vector retrieval yet.
- Do not change `/v1` endpoints/contracts.
- Do not bypass existing compose/edge/env patterns.
- Do not introduce new infra stacks (Redis/Kafka/etc.) unless explicitly required by approved phase scope.

## Implementation constraints
- Use deterministic IDs and idempotency keys.
- Keep jobs rerunnable and safe on crash/restart.
- Enforce per-source rate limits and bounded fetch.
- Persist provenance metadata for every fetched item.
- Keep tests deterministic (local fixtures; mocked external calls where required).

## Mandatory verification
- `docker compose run --rm api pytest`
- `docker compose run --rm api python -m app.research.worker --once`
- `docker compose up --build`
- `bash scripts/edge_validate.sh`

## Documentation updates required
- `docs/current_state.md`
- `docs/contracts/v2_research_sources_and_ingest.md`
- `README.md` (only if setup/run steps changed)

## Output format required
1. Files changed.
2. Migrations added and why.
3. Commands run with pass/fail summary.
4. Rollback notes.
5. Assumptions (only if unavoidable).
