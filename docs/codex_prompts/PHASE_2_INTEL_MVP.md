# Codex Prompt — Phase 2 (Intel connector + Context Packs, Option B)

You are working in `context_api/`.

Follow:
- AGENTS.md
- docs/codex_rules.md
- Truth hierarchy: docs/current_state.md is authoritative
- Implement ONLY Phase 2 as defined in docs/phases.md

## Goal
Ship intel-only Context Pack retrieval + progressive disclosure under /v2 without altering /v1 behaviour.

## Step-by-step tasks

### A) Add DB schema via Alembic
1. Create new Alembic revision that adds:
   - table `intel_articles`
     - article_id TEXT PRIMARY KEY
     - url TEXT NOT NULL
     - title TEXT NOT NULL
     - publisher TEXT NULL
     - author TEXT NULL
     - published_at TIMESTAMPTZ NULL
     - ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
     - topics JSONB NOT NULL DEFAULT '[]'
     - summary TEXT NOT NULL DEFAULT ''
     - signals JSONB NOT NULL DEFAULT '[]'
     - outline JSONB NOT NULL DEFAULT '[]'
     - outbound_links JSONB NOT NULL DEFAULT '[]'
   - table `intel_article_sections`
     - article_id TEXT NOT NULL (FK to intel_articles.article_id, on delete cascade)
     - section_id TEXT NOT NULL
     - heading TEXT NOT NULL DEFAULT ''
     - content TEXT NOT NULL
     - rank INTEGER NOT NULL DEFAULT 0
     - PRIMARY KEY (article_id, section_id)
2. Add reasonable indexes:
   - intel_articles: index on ingested_at, published_at
   - Full-text search:
     - add tsvector generated column OR a functional index combining title+summary (choose simplest that works in Postgres)
     - and/or index content in intel_article_sections for section search

### B) Define Pydantic models
Add models for /v2:
- ContextPackRequest: { query, topics?, token_budget?, recency_days?, max_items? }
- ContextPackResponse: { pack: { items: [...] }, retrieval_confidence, next_action, trace }
- OutlineResponse: { article_id, outline: [...] }
- SectionsRequest: { section_ids: [...] }
- SectionsResponse: { article_id, sections: [...] }
- ChunkSearchRequest: { query, max_chars?, max_chunks? }
- ChunkSearchResponse: { article_id, chunks: [...] }
- IntelIngestRequest: { fixture_bundle: string }  (MVP: only fixtures)
- IntelIngestResponse: { ingested_article_ids: [...] }

### C) Add deterministic fixtures and ingestion
1. Create `tests/fixtures/intel/` with at least 2 fixtures (JSON) that include:
   - metadata: article_id, url, title, publisher, published_at, topics
   - raw_text (optional)
   - outline: list of {section_id, heading, blurb}
   - sections: list of {section_id, heading, content, rank}
   - summary
   - signals: list of { claim, why, tradeoff?, cite: { section_id } }
   - outbound_links: list of urls
2. Implement `scripts/ingest_intel_fixtures.py` that:
   - loads fixtures from tests/fixtures/intel/
   - upserts intel_articles
   - replaces sections for each article deterministically (delete then insert in rank order)
3. Add `/v2/intel/ingest` endpoint (auth-protected) that triggers fixture ingestion:
   - Input: fixture_bundle (e.g. "default")
   - It ingests the built-in fixtures and returns ingested_article_ids

### D) Implement /v2 retrieval + expansion endpoints
1. Add router under `/v2`:
   - POST /v2/context/pack:
     - query DB using full-text search over title+summary and/or signals text
     - apply optional topic filter and recency_days
     - assemble bounded Context Pack:
       - include signals (top N) + short summary + citations
       - output retrieval_confidence + next_action
       - include trace_id (uuid4) + retrieved_article_ids
   - GET /v2/intel/articles/{id}/outline:
     - returns outline from intel_articles
   - POST /v2/intel/articles/{id}/sections:
     - returns requested sections from intel_article_sections (bounded)
   - POST /v2/intel/articles/{id}/chunks:search:
     - MVP: search within sections using Postgres full-text and return top matching snippets (bounded by max_chars)

2. Confidence + next_action heuristic (simple and deterministic):
   - high: top score above threshold AND >=2 signals with citations
   - med: some results but sparse signals or lower score
   - low: no results or very low score
   - next_action:
     - if low -> refine_query
     - if med and query mentions implementation/detail keywords -> expand_sections
     - else proceed

### E) Tests
Add pytest integration tests that:
- calls /v2/intel/ingest (fixtures)
- calls /v2/context/pack with query matching fixtures
- asserts:
  - 200 OK
  - pack has >=1 item
  - each item has citations / cite pointers
  - response size bounded (e.g., signals limited)
- calls outline + sections + chunks:search endpoints and asserts stable structure.

### F) Docs updates
Update docs/current_state.md and README.md to reflect what is now true, including the /v2 endpoints.

## Do not do
- Do not add embeddings unless absolutely necessary.
- Do not change /v1 schemas or existing tests.
- Do not add new services.
