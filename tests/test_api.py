from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def build_settings() -> Settings:
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        context_api_token=os.environ.get("CONTEXT_API_TOKEN", "change-me"),
        version="0.0.0",
        git_sha="test",
    )


def test_sync_and_search_projects() -> None:
    settings = build_settings()
    app = create_app(settings)
    client = TestClient(app)

    headers = {"Authorization": f"Bearer {settings.context_api_token}"}
    payload = {
        "items": [
            {"project_id": "proj_1", "name": "Sagitta Loft", "status": "Active"},
            {"project_id": "proj_2", "name": "Sagitta Flooring", "status": "Active"},
        ]
    }
    response = client.post("/v1/projects/sync", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["count"] == 2

    search = client.post("/v1/projects/search", json={"query": "Sagitta", "limit": 5}, headers=headers)
    assert search.status_code == 200
    results = search.json()["results"]
    assert results
    assert results[0]["id"].startswith("proj_")


def test_sync_and_search_tasks() -> None:
    settings = build_settings()
    app = create_app(settings)
    client = TestClient(app)

    headers = {"Authorization": f"Bearer {settings.context_api_token}"}
    payload = {
        "items": [
            {
                "task_id": "task_1",
                "title": "Follow up with John",
                "status": "Todo",
                "priority": "High",
                "project_id": "proj_1",
            }
        ]
    }
    response = client.post("/v1/tasks/sync", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["count"] == 1

    search = client.post("/v1/tasks/search", json={"query": "Follow up", "limit": 5}, headers=headers)
    assert search.status_code == 200
    results = search.json()["results"]
    assert results
    assert results[0]["id"] == "task_1"
