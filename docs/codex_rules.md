# Codex Rules — context_api

## Core rules
- Do not change /v1 endpoints or contracts for the Intel MVP (Option B).
- Keep response payloads compact; this API serves context hints, not full documents.
- Prefer deterministic behaviour: fixture ingestion must be repeatable.
- Add migrations via Alembic; do not hand-edit DB state.
- Bounded outputs:
  - /v2/context/pack respects token/size budgets.
  - expansion endpoints return limited payloads by section/chunk selection.

## Provenance
- Every extracted signal must include a cite pointer (article_id + section_id/chunk offsets).

## Observability
- /v2/context/pack should return a trace_id and list retrieved_article_ids.
- Log retrieval decisions (safe, no secrets).

## Testing
- Add an integration test that:
  - ingests fixtures
  - calls /v2/context/pack
  - validates: citations present, bounded output, stable schema
