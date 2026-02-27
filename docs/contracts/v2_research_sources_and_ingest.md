# /v2 research sources + ingestion — Contract stub (Phase 1)

Status: implemented in Phase 1 (baseline shape).

## Endpoints

### `POST /v2/research/sources/upsert`
Upserts an allowlisted source definition.

Request:
- `topic_key` (string, required)
- `kind` (`rss` | `atom` | `site_map` | `html_listing` | `api`, required)
- `name` (string, required)
- `base_url` (string, required)
- `poll_interval_minutes` (int, optional, default 60)
- `rate_limit_per_hour` (int, optional, default 30)
- `robots_mode` (`strict` | `ignore`, optional, default `strict`)
- `enabled` (bool, optional, default true)
- `tags` (string[], optional)

Response:
- `source_id` (stable deterministic ID)
- `status` (`created` | `updated`)

### `POST /v2/research/ingest/run`
Queues or executes one ingestion run for selected sources.

Request:
- `topic_key` (string, required)
- `source_ids` (string[], optional; default all enabled in topic)
- `trigger` (`manual` | `schedule` | `event`, required)
- `idempotency_key` (string, optional)
- `max_items_per_source` (int, optional)

Response:
- `run_id`
- `status` (`queued` | `running` | `completed` | `failed`)
- `sources_selected` (int)

### `GET /v2/research/ingest/runs/{run_id}`
Returns run status and change summary.

Response:
- `run_id`
- `status`
- `started_at`
- `finished_at`
- `counters`:
  - `items_seen`
  - `items_new`
  - `items_deduped`
  - `items_failed`
- `errors[]` (bounded)

## Storage expectations (Phase 1)
- `research_sources`
- `research_source_policies`
- `research_ingestion_runs`
- `research_documents` (seed + raw metadata only)

## Deterministic ID expectations
- `source_id = sha256(topic_key + canonical_base_url + kind)`
- `document_id = sha256(source_id + canonical_url_or_external_id)`
- reruns with same canonical item update existing row; no duplicates.
