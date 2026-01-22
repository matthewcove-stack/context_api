# Intent: Context API

## Overview

Provide a read-optimized context API backed by Postgres for fast, deterministic context packs.

## Responsibilities

- Mirror key Notion databases (start with Projects + Tasks).
- Expose compact context endpoints (project/task snapshots, search snippets).
- Support manual sync endpoints first; background sync later.
  - Manual sync uses the Notion gateway db sample endpoint.

## Implemented API (v1)

- `POST /v1/projects/sync`
- `POST /v1/tasks/sync`
- `POST /v1/projects/search`
- `POST /v1/tasks/search`
- `GET /v1/projects/{project_id}`
- `GET /v1/tasks/{task_id}`
- `GET /health`
- `GET /version`

## Non-Goals

- Not a reasoning engine or orchestration layer.
- Not a live Notion search proxy per chat turn.
