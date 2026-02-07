# Codex Rules — context_api

## Core rules
- Do not change /v1 endpoints or contracts. All new work is under /v2.
- Keep response payloads compact; this API serves context hints, not full documents.
- Prefer deterministic behaviour: tests must not depend on live internet.
- Add migrations via Alembic; do not hand-edit DB state.
- Bounded outputs:
  - /v2/context/pack respects token/size budgets.
  - expansion endpoints return limited payloads by section/chunk selection.
  - ingestion endpoints return small status payloads (no full documents).

## Intel ingestion rules
- URL canonicalisation must be deterministic (strip common tracking params, normalise host/scheme).
- Store lossless raw_html for traceability, but never return it by default.
- Extraction must be bounded (max bytes, timeouts, max chars stored per field as a guardrail).
- LLM enrichment must be schema-validated; reject/mark partial on invalid outputs.
- No claim/signal without a cite pointer to an existing section_id.

## Provenance
- Every extracted signal must include a cite pointer (article_id + section_id).
- For each cite pointer, store a bounded supporting_snippet that appears in the referenced section.

## Observability
- /v2/context/pack returns trace_id and list of retrieved_article_ids.
- Ingestion jobs record errors and attempts; worker logs are safe (no secrets).

## Testing
- Integration tests must:
  - use a local HTTP fixture server for URL fetch
  - mock the LLM client
  - ingest -> enrich -> /v2/context/pack -> expansion endpoint assertions
