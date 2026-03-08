# /v2 research retrieval — Contract

Status: implemented in Phase 5 (hybrid scoring + feedback + ops summary).

## Endpoint: `POST /v2/research/context/pack`

Request:
- `query` (string, required)
- `topic_key` (string, required)
- `source_ids` (string[], optional)
- `token_budget` (int, optional)
- `recency_days` (int, optional)
- `max_items` (int, optional)
- `min_relevance_score` (float, optional)

Response:
- `pack.items[]`:
  - `document_id`
  - `source_id`
  - `title`
  - `canonical_url`
  - `published_at`
  - `summary`
  - `signals[]`
  - `citations[]` (`document_id`, `chunk_id`, `section_id`)
  - `score_breakdown` (`total`, `lexical`, `embedding`, `recency`, `source_weight`)
- `retrieval_confidence` (`high` | `med` | `low`)
- `next_action` (`proceed` | `refine_query` | `expand_sections`)
- `trace`:
  - `trace_id`
  - `retrieved_document_ids[]`
  - `timing_ms`

## Endpoint: `POST /v2/research/documents/{document_id}/chunks:search`

Request:
- `query` (string)
- `max_chunks` (int, optional)
- `max_chars` (int, optional)

Response:
- `document_id`
- `chunks[]`:
  - `chunk_id`
  - `section_id`
  - `snippet`
  - `score`

## Logging expectations
- Every retrieval writes a query log row with:
  - `trace_id`
  - normalized request fields
  - candidate set size
  - returned item IDs
  - latency + error status

Implemented table:
- `research_query_logs`

## Endpoint: `POST /v2/research/retrieval/feedback`

Request:
- `trace_id` (string, required)
- `query_log_id` (string, optional)
- `document_id` (string, required)
- `chunk_id` (string, required)
- `verdict` (`useful` | `not_useful`, required)
- `notes` (string, optional)

Response:
- `feedback_id`
- `status` (`recorded`)

## Endpoint: `GET /v2/research/ops/summary?topic_key=...`

Response includes:
- source counts
- source cooldown counts
- document status counts
- open/failed run counters
- 24h run failure rate
- retrieval query/error counters (24h)

## Endpoint: `GET /v2/research/ops/sources?topic_key=...&limit=...`

Response:
- `topic_key`
- `items[]`:
  - `source_id`
  - `name`
  - `enabled`
  - `last_polled_at`
  - `consecutive_failures`
  - `cooldown_until`
  - `last_error`
  - `documents_total`
  - `documents_embedded`
  - `documents_failed`
  - `retrieval_queries_24h`

## Endpoint: `GET /v2/research/ops/documents?topic_key=...`

Response:
- `topic_key`
- `items[]`:
  - `status`
  - `count`

## Endpoint: `GET /v2/research/ops/storage?topic_key=...`

Response:
- `topic_key`
- `documents_count`
- `chunks_count`
- `embeddings_count`
- `raw_payload_bytes`
- `extracted_text_bytes`
- `chunks_bytes`
- `embeddings_bytes`
- `total_bytes`

## Endpoint: `GET /v2/research/ops/progress?topic_key=...&run_limit=...`

Response:
- `topic_key`
- `queued_runs`
- `running_runs`
- `stages` (discovered/fetched/extracted/embedded/failed)
- `chunks_count`
- `embeddings_count`
- `embedding_coverage_pct`
- `db_size_bytes`
- `disk_total_bytes`
- `disk_used_bytes`
- `disk_free_bytes`
- `disk_used_pct`
- `ai_external_calls_estimate`
- `ai_estimated_tokens_total`
- `ai_estimated_tokens_24h`
- `ai_models[]` with model-level document/chunk/token estimates
- `runs[]` with run status, elapsed seconds, and item counters

## Endpoint: `GET /v2/research/ops/dashboard`

Response:
- HTML dashboard shell that calls ops/review endpoints with bearer auth from page input.

## Endpoint: `POST /v2/research/sources/{source_id}/disable`
## Endpoint: `POST /v2/research/sources/{source_id}/enable`

Response:
- `source_id`
- `enabled`
- `status` (`updated`)

## Endpoint: `POST /v2/research/governance/redact`

Request:
- `topic_key`
- `older_than_days`

Response:
- `topic_key`
- `older_than_days`
- `redacted_documents`

## Endpoint: `GET /v2/research/review/queue?topic_key=...&limit=...`

Response:
- `topic_key`
- `items[]` with retrieval trace, candidate/returned IDs, status/error, and feedback counters
