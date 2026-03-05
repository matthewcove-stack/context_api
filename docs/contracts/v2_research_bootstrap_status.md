# /v2 research bootstrap status — Contract

## Endpoint: `GET /v2/research/bootstrap/status?topic_key=...`

Returns the latest bootstrap event and associated run status for a topic.

### Response
- `topic_key`
- `latest_bootstrap` (nullable):
  - `event_id`
  - `request_hash`
  - `idempotency_key` (nullable)
  - `summary`:
    - `received`
    - `valid`
    - `invalid`
    - `created`
    - `updated`
    - `skipped_duplicate`
  - `run_id` (nullable)
  - `run_status` (`queued` | `running` | `completed` | `failed`, nullable)
  - `created_at`
