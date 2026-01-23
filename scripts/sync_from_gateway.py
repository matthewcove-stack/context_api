#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import uuid
from typing import Any, Dict, List, Optional, Tuple
from urllib import request, error


def env(name: str, default: Optional[str] = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Missing {name}")
    return value


def post_json(url: str, token: str, payload: Dict[str, Any]) -> Tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode("utf-8")
    except error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def parse_json(body: str) -> Dict[str, Any]:
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON response: {exc}") from exc


def build_gateway_payload(database_key: str, limit: int) -> Dict[str, Any]:
    return {
        "request_id": str(uuid.uuid4()),
        "actor": "context_sync",
        "payload": {"database_key": database_key, "limit": limit},
    }


def fetch_gateway_rows(base_url: str, token: str, database_key: str, limit: int) -> List[Dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/v1/notion/db/sample"
    status, body = post_json(url, token, build_gateway_payload(database_key, limit))
    if status != 200:
        raise RuntimeError(f"Gateway {database_key} fetch failed: HTTP {status} {body}")
    data = parse_json(body)
    if data.get("status") != "ok":
        raise RuntimeError(f"Gateway {database_key} returned error: {body}")
    results = (data.get("data") or {}).get("results") or []
    if not isinstance(results, list):
        raise RuntimeError(f"Gateway {database_key} results invalid: {body}")
    return results


def normalize_project_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in rows:
        properties = row.get("properties") or {}
        name = properties.get("Name")
        if not isinstance(name, str) or not name.strip():
            continue
        items.append(
            {
                "project_id": row.get("id"),
                "name": name,
                "status": properties.get("Status"),
                "raw": row,
            }
        )
    return items


def build_project_name_index(items: List[Dict[str, Any]]) -> Dict[str, str]:
    index: Dict[str, str] = {}
    for item in items:
        name = item.get("name")
        project_id = item.get("project_id")
        if isinstance(name, str) and isinstance(project_id, str):
            index[name.strip().lower()] = project_id
    return index


def normalize_task_rows(rows: List[Dict[str, Any]], project_index: Dict[str, str]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in rows:
        properties = row.get("properties") or {}
        title = properties.get("Title")
        if not isinstance(title, str) or not title.strip():
            continue
        project_name = properties.get("Project")
        project_id = None
        if isinstance(project_name, str):
            project_id = project_index.get(project_name.strip().lower())
        items.append(
            {
                "task_id": row.get("id"),
                "title": title,
                "status": properties.get("Status"),
                "priority": properties.get("Priority"),
                "due": properties.get("Due"),
                "project_id": project_id,
                "raw": row,
            }
        )
    return items


def sync_context_api(
    base_url: str,
    token: str,
    path: str,
    items: List[Dict[str, Any]],
    source: str,
) -> None:
    url = f"{base_url.rstrip('/')}{path}"
    status, body = post_json(url, token, {"source": source, "items": items})
    if status != 200:
        raise RuntimeError(f"Context API sync failed: HTTP {status} {body}")


def main() -> None:
    limit = int(os.environ.get("SYNC_LIMIT", "100"))
    if len(sys.argv) > 1:
        limit = int(sys.argv[1])

    gateway_base_url = env("GATEWAY_BASE_URL", "http://n8n:5678/webhook")
    gateway_token = env("GATEWAY_API_TOKEN")
    context_base_url = env("CONTEXT_API_BASE_URL", "http://api:8001")
    context_token = env("CONTEXT_API_TOKEN")
    projects_key = env("PROJECTS_DB_KEY", "projects")
    tasks_key = env("TASKS_DB_KEY", "tasks")

    project_rows = fetch_gateway_rows(gateway_base_url, gateway_token, projects_key, limit)
    project_items = normalize_project_rows(project_rows)
    project_index = build_project_name_index(project_items)
    sync_context_api(context_base_url, context_token, "/v1/projects/sync", project_items, "notion_gateway")
    print(f"projects synced={len(project_items)}")

    task_rows = fetch_gateway_rows(gateway_base_url, gateway_token, tasks_key, limit)
    task_items = normalize_task_rows(task_rows, project_index)
    sync_context_api(context_base_url, context_token, "/v1/tasks/sync", task_items, "notion_gateway")
    print(f"tasks synced={len(task_items)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc))
        sys.exit(1)
