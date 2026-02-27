# context_api — Intent

## Product intent
`context_api` is BrainOS's retrieval substrate: a small authenticated service that ingests trusted external knowledge, preserves provenance, and serves bounded context payloads for agents.

The next initiative extends the current intel MVP into a durable research ingestion pipeline:

1) Curated source catalogue
- Maintain allowlisted research sources by topic/domain.
- Enforce per-source crawl policies and operator controls.

2) Continuous ingestion
- Discover and fetch newly published items on a schedule/event trigger.
- Preserve deterministic identities and idempotent re-runs.

3) Relevance and enrichment
- Score candidate items with explainable signals.
- Extract, chunk, embed, and index for retrieval.

4) Retrieval for agents
- Keep compact, citation-first `/v2` responses.
- Preserve progressive disclosure for deeper expansion.

## Constraints
- `docs/current_state.md` is authoritative for what is currently implemented.
- Do not break or reshape existing `/v1` contracts.
- Extend existing compose/network/env patterns; do not introduce parallel infrastructure stacks.
- Keep outputs bounded and provenance-rich.
- Treat idempotency and deterministic IDs as first-order requirements.
- Never embed secrets in code/docs; use env vars only.

## Success criteria (program-level)
- Research source ingestion runs continuously and safely with replay support.
- Duplicate fetches for the same canonical item do not create duplicate records.
- Retrieval remains bounded and cites stable provenance pointers.
- Operators can answer: what changed, why it was ingested, and where each claim came from.
