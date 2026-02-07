# Phase 3 — Implement URL ingestion + fetch/extract + LLM enrichment (Option B)

You are implementing ONLY Phase 3 from docs/phases.md.
Obey docs/codex_rules.md. Truth hierarchy: docs/current_state.md is authoritative.
Do NOT change /v1 endpoints. Keep /v2/context/pack stable.

## Goal
Add URL ingestion and LLM enrichment so that a list of article URLs can be fetched, extracted, enriched,
stored in Postgres, and then used by /v2/context/pack and the existing expansion endpoints.

## Required deliverables
1) Database migrations (Alembic)
- Add intel_ingest_jobs table with fields:
  - job_id (uuid pk), url_original, url_canonical, article_id, status, attempts, last_error, created_at, updated_at
- Extend intel_articles with fields (nullable where appropriate):
  - url_original (text)
  - raw_html (text)  (store bounded; enforce max bytes)
  - extracted_text (text) (store bounded; enforce max chars)
  - http_status (int), content_type (text), etag (text), last_modified (text)
  - fetch_meta (jsonb), extraction_meta (jsonb), enrichment_meta (jsonb)
  - status (text) default 'queued'
  - updated_at timestamp
  - tags jsonb default []
- Keep existing columns (signals/summary/outline/topics) intact.

2) New models in app/models.py
- IntelIngestUrlsRequest { urls: list[str], topics?: list[str], tags?: list[str], force_refetch?: bool, enrich?: bool }
- IntelIngestUrlsResult { url, status, article_id?, job_id?, reason? }
- IntelIngestUrlsResponse { results: list[IntelIngestUrlsResult] }
- IntelArticleStatusResponse matching docs/contracts/v2_intel_ingest_urls.md (bounded outputs).

3) Storage functions (app/storage/db.py + app/storage/schema.py)
- Upsert/select for intel_articles, sections, jobs
- Add helpers:
  - canonicalize_url(url) -> canonical_url
  - compute_article_id(canonical_url) -> str
- Add query functions for job claiming:
  - claim_next_job(engine) -> job row (SELECT ... FOR UPDATE SKIP LOCKED)
  - update_job_status(engine, job_id, status, last_error, attempts)
- Add article status update functions:
  - mark_article_extracted(...)
  - mark_article_enriched(...)
  - mark_article_failed(...)

4) Intel pipeline modules (new package app/intel/)
- fetch.py:
  - fetch_url(url) -> { final_url, status_code, headers, html } with timeouts, max bytes, redirects cap, user-agent
  - per-host throttling (simple in-memory map; ok for single worker)
- extract.py:
  - extract_readable_text(html, url) -> { title, author?, published_at?, text, method, confidence, warnings[] }
  - Use trafilatura if added; fallback to readability-lxml or bs4 stripping.
  - Enforce bounds on extracted text length.
- sectionise.py:
  - sectionise(text or html) -> sections[{section_id, heading, content, rank}] + outline[{section_id, heading, blurb}]
  - Deterministic section ids (s01, s02...)
- enrich.py:
  - LLM client wrapper (use httpx; provider via env vars OPENAI_API_KEY/OPENAI_MODEL)
  - Two-step enrichment:
    1) outline blurbs (optional if sectionise already creates outline)
    2) signals + summary + topics + freshness_half_life_days
  - Strict JSON schema via Pydantic models (internal), validate before storing.
  - Hard rule: no signal without cite.section_id referencing an existing section.
  - supporting_snippet must appear in the referenced section content (substring match).
- worker.py:
  - loop: claim job -> fetch -> extract -> sectionise -> enrich -> store -> mark done
  - CLI args: --once (process one job and exit), --sleep-seconds
  - Safe logging (no secrets)

5) API endpoints in app/main.py (under /v2)
- POST /v2/intel/ingest_urls
  - canonicalize + dedupe against intel_articles by article_id
  - if force_refetch: queue new job and reprocess
  - else if exists and status enriched: return deduped
  - else: queue
- GET /v2/intel/articles/{article_id}
  - return status + compact summary/signals/outline/topics + meta + last_error
  - do NOT return raw_html or full extracted_text by default
- Ensure existing expansion endpoints read from intel_article_sections and outline as before.

6) Requirements and env example updates
- Add required libs for extraction if used (prefer trafilatura; fallback readability-lxml).
- Update .env.example with OPENAI_API_KEY/OPENAI_MODEL and optional fetch bounds.

7) Tests
- Unit tests:
  - canonicalize_url strips utm params and fragments
  - article_id stable
  - enrichment schema validation rejects missing cite pointers
- Integration test (no live internet):
  - Spin up a tiny local httpx mock transport OR FastAPI test route serving a sample HTML article.
  - Mock LLM client to return deterministic JSON.
  - Call POST /v2/intel/ingest_urls -> run worker --once -> GET article status -> POST /v2/context/pack
  - Assert: signals present, citations include section ids, pack bounded, /v1 untouched.

## Verification
- `docker compose run --rm api pytest` must pass.
- Document how to run worker locally in README or docs/current_state.md.
- Update docs/current_state.md and README to reflect what is now true (drift prevention).

## Output required
1) List files changed/added.
2) Commands run + results.
3) Any necessary assumptions (only if they impact behaviour/security/cost).
