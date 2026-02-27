# Codex Rules — context_api

## Core rules
- Do not break `/v1` contracts.
- Keep runtime changes scoped to the requested phase only.
- `docs/current_state.md` is authoritative; update it whenever behavior changes.
- Add DB changes via Alembic migrations only.

## Research ingestion guardrails
- Deterministic IDs are mandatory for sources, documents, chunks, and retrieval citations.
- Idempotency is mandatory for ingestion and reprocessing; duplicate canonical items must not duplicate records.
- Preserve provenance on every derived artifact:
  - source_id
  - canonical_url
  - fetch/extraction metadata
  - chunk/embedding model versions
- Do not discard raw payloads needed for audit/reprocessing unless retention policy explicitly says so.

## Governance and safety
- Use allowlisted sources only.
- Respect per-source crawl policy (rate, robots, fetch bounds, retries/backoff).
- Never place secrets in code, logs, fixtures, docs, or tests.
- Redaction must be applied before logging request/response payloads containing tokens or credentials.

## Retrieval constraints
- Keep retrieval outputs compact and bounded by explicit limits.
- Prefer citation-first responses over long text dumps.
- If hybrid retrieval is introduced, keep lexical fallback deterministic and documented.

## Testing expectations
- Unit tests must cover ID determinism and dedupe logic.
- Integration tests must avoid live internet dependencies.
- LLM-dependent stages must be mockable and schema-validated.

## Actions and external access
- Actions/OpenAPI exposure is read-only by default.
- Edge/Cloudflare exposure must follow existing repo runbooks and shared `edge` network standards.
