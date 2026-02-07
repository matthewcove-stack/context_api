from __future__ import annotations

import os

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def build_settings() -> Settings:
    # Reuse DATABASE_URL from env or fall back to local compose default.
    db_url = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@db:5432/postgres")
    return Settings(database_url=db_url, context_api_token="test-token")


def test_health_endpoint_no_auth() -> None:
    app = create_app(build_settings())
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_ready_endpoint_requires_db() -> None:
    app = create_app(build_settings())
    client = TestClient(app)
    # ready may be 200 if db is reachable in test environment; allow 503 if not.
    r = client.get("/ready", headers={"Authorization": "Bearer test-token"})
    assert r.status_code in (200, 503)
