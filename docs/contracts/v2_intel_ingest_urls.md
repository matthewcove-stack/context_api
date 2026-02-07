# /v2 Intel URL ingestion + enrichment — Contract (MVP)

## Endpoint: POST /v2/intel/ingest_urls
Queues URL ingestion jobs (fetch/extract/sectionise/enrich). Does not return full content.

Request JSON:
- urls: string[] (required, 1..N)
- topics?: string[] (optional)
- tags?: string[] (optional)
- force_refetch?: boolean (default false)
- enrich?: boolean (default true; MVP expects true)

Response JSON:
- results: [
    {
      url: string,
      status: "queued" | "deduped" | "failed",
      article_id?: string,
      job_id?: string,
      reason?: string
    }
  ]

Notes:
- URL canonicalisation is deterministic; article_id is derived from canonical URL.
- If already ingested and not force_refetch, status=deduped.

## Endpoint: GET /v2/intel/articles/{article_id}
Returns ingestion/enrichment status and compact outputs (signals/summary) when available.

Response JSON:
- article_id
- url
- title (nullable until extracted)
- status: "queued" | "extracted" | "enriched" | "failed" | "partial"
- topics: string[]
- summary: string (present when enriched/partial)
- signals: array (present when enriched/partial)
- outline: array (present when extracted or enriched)
- meta:
  - fetch: { http_status, content_type, fetched_at, warnings[] }
  - extraction: { method, confidence, warnings[] }
  - enrichment: { model, prompt_version, confidence, token_usage, warnings[] }
- last_error?: string

## Worker
Entry: `python -m app.intel.worker`
- Polls intel_ingest_jobs
- Uses bounded fetch and extraction
- Runs LLM enrichment with strict JSON schema
- Updates intel_articles and intel_article_sections

## Enrichment rules
- No signal without cite pointer to section_id
- Each cite pointer includes supporting_snippet (<= 200 chars) that appears in the referenced section content
- Outputs are bounded:
  - summary <= 900 chars
  - signals <= 8 (MVP default), each field bounded
