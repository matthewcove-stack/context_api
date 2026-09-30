# Intent: Context API

## Overview

Provide a research service backed by Postgres: collect sources, retrieve cited
evidence for project questions, and produce concise reviewed Brief reports.

## Responsibilities

- Fetch and extract selected public research sources with provenance.
- Return bounded context packs with source citations and limitations.
- Review Brief drafts for factual grounding, structure and natural writing.
- Report collection, embedding and publication failures separately.
- Maintain existing Notion Projects/Tasks sync and search without expanding it.

## Constraints

- Docker-only for services and scripts.
- No host-installed dependencies for the canonical workflow.
- Use Docker service names (not localhost) for container-to-container calls.

## Legacy API (v1, maintained)

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
