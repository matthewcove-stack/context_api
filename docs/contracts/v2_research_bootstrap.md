# /v2 research source bootstrap — Contract

## Endpoint: `POST /v2/research/sources/bootstrap`

Bootstraps source suggestions for a topic, dedupes/canonicalizes/upserts them, and optionally triggers one ingestion run.

### Request
- `topic_key` (string, required)
- `suggestions` (array, required, `1..200` by default limit)
  - item:
    - `kind` (`rss` | `atom` | `site_map` | `html_listing` | `api`)
    - `name` (string)
    - `base_url` (string)
    - `tags` (string[], optional)
    - `poll_interval_minutes` (int, optional)
    - `rate_limit_per_hour` (int, optional)
    - `source_weight` (float, optional)
    - `robots_mode` (`strict` | `ignore`, optional)
- `trigger_ingest` (bool, optional, default `true`)
- `trigger` (`manual` | `event`, optional, default `event`)
- `idempotency_key` (string, optional)
- `dry_run` (bool, optional, default `false`)

### Response
- `topic_key`
- `summary`:
  - `received`
  - `valid`
  - `invalid`
  - `created`
  - `updated`
  - `skipped_duplicate`
- `results[]`:
  - `index`
  - `status` (`created` | `updated` | `invalid` | `skipped_duplicate`)
  - `reason` (optional)
  - `source_id` (optional)
- `ingest`:
  - `triggered` (bool)
  - `run_id` (optional)
  - `status` (optional)

### Behavior
- Canonical URL + deterministic `source_id` derivation.
- Duplicate handling:
  - invalid URLs => `invalid`
  - duplicate in request => `skipped_duplicate`
- Upsert uses existing source catalog policy model.
- When `trigger_ingest=true`, one ingest run is created for all valid unique sources.
- `idempotency_key` replays previous response for same payload.
- `dry_run=true` performs validation/dedupe only and writes nothing.
