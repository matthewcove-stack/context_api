# context_api — Current State (Authoritative for this repo)

## What works today
- FastAPI + Postgres + Alembic
- Authenticated v1 endpoints for searching mirrored Projects/Tasks
- Docker quickstart and tests exist

## What is incomplete / Phase 1 expectations
For Phase 1, context_api may be used opportunistically, but it is not a hard dependency for the vertical slice.
If enabled:
- Searches must be fast and return compact, predictable shapes.
- Sync script should be runnable manually to refresh context from notion_gateway.

## Phase 1 scope (exact)

Goal: a single end-to-end vertical slice that reliably turns a natural-language intent into a Notion Task create/update, with an audit trail.

In scope:
- Submit intent (via action_relay client or curl) to intent_normaliser `POST /v1/intents`.
- intent_normaliser normalises into a deterministic plan (`notion.tasks.create` or `notion.tasks.update`).
- If `EXECUTE_ACTIONS=true` and confidence >= threshold, intent_normaliser executes the plan by calling notion_gateway:
  - `POST /v1/notion/tasks/create` or `POST /v1/notion/tasks/update`
- Write artifacts for: received → normalised → executed (or failed) with stable IDs.
- Idempotency: duplicate submissions with the same `request_id` (or generated deterministic key) must not create duplicate Notion tasks.
- Error handling: gateway errors are surfaced in the response and recorded as artifacts.
- Minimal context lookups:
  - Optional: query context_api for project/task hints when provided, but Phase 1 must still work without context_api being “perfect”.

Out of scope (Phase 2+):
- UI for clarifications (API-only is fine).
- Calendar events / reminders.
- Full automated background sync from Notion.
- Multi-user, permissions, or “agents” beyond single operator.


## Verification commands
- Tests (Docker):
  - `docker compose run --rm api pytest`
