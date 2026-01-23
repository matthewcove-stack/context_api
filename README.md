# Context API

FastAPI service that mirrors Projects and Tasks into Postgres and serves compact search results for the normaliser.

## Quickstart (Docker)

```bash
cp .env.example .env
docker compose up --build
```

API runs at `http://localhost:8001` for host access. For container-to-container calls, use service names (for example `http://api:8001`) and avoid localhost.

## Configuration

Required:

- `DATABASE_URL`
- `CONTEXT_API_TOKEN`

Optional:

- `VERSION`
- `GIT_SHA`
- `GATEWAY_BASE_URL` (for sync script)
- `GATEWAY_API_TOKEN` (for sync script)
- `CONTEXT_API_BASE_URL` (for sync script, default http://api:8001)
- `SYNC_LIMIT` (for sync script)

## Endpoints (v1)

All endpoints require `Authorization: Bearer <CONTEXT_API_TOKEN>`.

### POST /v1/projects/sync

```json
{
  "source": "notion",
  "items": [
    { "project_id": "proj_1", "name": "Sagitta Loft", "status": "Active" }
  ]
}
```

### POST /v1/tasks/sync

```json
{
  "source": "notion",
  "items": [
    { "task_id": "task_1", "title": "Follow up", "project_id": "proj_1" }
  ]
}
```

### POST /v1/projects/search

```json
{ "query": "Sagitta", "limit": 5 }
```

### POST /v1/tasks/search

```json
{ "query": "Follow up", "limit": 5, "project_id": "proj_1" }
```

### GET /v1/projects/{project_id}
### GET /v1/tasks/{task_id}

## Tests

```bash
docker compose run --rm api pytest
```

## Manual sync from Notion Gateway

The gateway already exposes read endpoints. This script pulls Projects + Tasks and upserts them into the cache:

```bash
set GATEWAY_BASE_URL=http://n8n:5678/webhook
set GATEWAY_API_TOKEN=change-me
set CONTEXT_API_BASE_URL=http://api:8001
set CONTEXT_API_TOKEN=change-me
docker compose run --rm api python scripts/sync_from_gateway.py 100
```

Ensure the gateway container is reachable on a shared Docker network and reference it by service name (for example `n8n`).
