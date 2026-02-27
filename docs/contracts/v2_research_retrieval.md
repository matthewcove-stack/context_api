# /v2 research retrieval — Contract stub (Phase 4+ target)

Status: draft retrieval contract for upcoming phases.

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
  - `score_breakdown` (bounded explainability payload)
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
