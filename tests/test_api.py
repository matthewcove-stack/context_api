from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

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


def test_dashboard_and_workspace_views() -> None:
    settings = build_settings()
    app = create_app(settings)
    client = TestClient(app)

    headers = {"Authorization": f"Bearer {settings.context_api_token}"}
    project_payload = {
        "items": [
            {"project_id": "proj_1", "name": "Brain OS Console", "status": "Active"},
            {"project_id": "proj_2", "name": "Home Admin", "status": "Active"},
        ]
    }
    now = datetime.now(timezone.utc)
    task_payload = {
        "items": [
            {
                "task_id": "task_overdue",
                "title": "Fix shell layout",
                "status": "Todo",
                "priority": "High",
                "project_id": "proj_1",
                "due": (now - timedelta(days=1)).isoformat(),
                "updated_at": now.isoformat(),
            },
            {
                "task_id": "task_today",
                "title": "Review today plan",
                "status": "In Progress",
                "priority": "Medium",
                "project_id": "proj_1",
                "due": now.isoformat(),
                "updated_at": now.isoformat(),
            },
            {
                "task_id": "task_waiting",
                "title": "Waiting on gateway answer",
                "status": "Waiting",
                "priority": "Low",
                "project_id": "proj_2",
                "updated_at": now.isoformat(),
            },
            {
                "task_id": "task_inbox",
                "title": "Loose capture from phone",
                "status": "Todo",
                "priority": "Low",
                "updated_at": now.isoformat(),
            },
            {
                "task_id": "task_done",
                "title": "Completed yesterday",
                "status": "Done",
                "priority": "Low",
                "project_id": "proj_2",
                "updated_at": now.isoformat(),
            },
        ]
    }

    assert client.post("/v1/projects/sync", json=project_payload, headers=headers).status_code == 200
    assert client.post("/v1/tasks/sync", json=task_payload, headers=headers).status_code == 200

    dashboard = client.get("/v1/dashboard/today", headers=headers)
    assert dashboard.status_code == 200
    dashboard_json = dashboard.json()
    assert dashboard_json["summary"]["overdue_count"] == 1
    assert any(item["task_id"] == "task_today" for item in dashboard_json["today"])
    assert any(item["task_id"] == "task_waiting" for item in dashboard_json["waiting"])

    workspace = client.get("/v1/projects/proj_1/workspace", headers=headers)
    assert workspace.status_code == 200
    workspace_json = workspace.json()
    assert workspace_json["project"]["project_id"] == "proj_1"
    assert len(workspace_json["tasks"]) == 2
    assert workspace_json["summary"]["open_task_count"] == 2

    inbox = client.get("/v1/inbox", headers=headers)
    assert inbox.status_code == 200
    assert inbox.json()["items"][0]["task_id"] == "task_inbox"

    daily_review = client.get("/v1/reviews/daily", headers=headers)
    assert daily_review.status_code == 200
    review_json = daily_review.json()
    assert review_json["mode"] == "daily"
    assert any(item["task_id"] == "task_overdue" for item in review_json["focus_items"])
