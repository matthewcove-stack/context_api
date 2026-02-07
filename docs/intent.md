# context_api — Intent

## Product intent
This service is BrainOS's Context API: a small, authenticated, docker-reproducible API that serves
compact context hints for LLM workflows.

We are prioritising an MVP extension:

### Intel Digest + Context Pack (Option B)
Ship an "Intel connector" that stores engineering-intel artifacts (articles/papers/transcripts) and
serves compact Context Packs for reasoning. For MVP, packs are intel-only (do not merge Projects/Tasks).

## Primary workflows (MVP)

1) Ingest (fixtures first; URLs later)
- Store raw snapshot losslessly
- Store derived representations:
  - outline (section headings)
  - section texts (for targeted expansion)
  - summary (short)
  - signals (structured claims with provenance)
  - outbound links

2) Retrieve Context Pack
- Caller provides query + optional tags + optional recency bias + token budget
- API returns:
  - signals + short summary + citations/pointers
  - retrieval_confidence (high/med/low)
  - next_action (proceed | refine_query | expand_sections)

3) Progressive disclosure
- Caller can fetch outline and then specific sections/chunks
- Default behaviour never returns full raw text in /context/pack

## Constraints
- Do not change /v1 endpoints or their contracts in this MVP.
- Deterministic fixture ingestion (same inputs -> same stored outputs).
- Bounded outputs on all endpoints.
- Provenance for every extracted signal via cite pointers.
- Docker-compose reproducibility for run and tests.

## MVP success criteria
- `POST /v2/intel/ingest` can ingest a deterministic fixture bundle.
- `POST /v2/context/pack` returns a bounded pack with citations from the fixture corpus.
- Expansion endpoints return stable, bounded outputs for outline + selected sections/chunks.
- Tests cover ingest + pack + expansion.
