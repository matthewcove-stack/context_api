from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url


@pytest.fixture(autouse=True)
def configure_research_embedding_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_EMBEDDING_MODEL", os.environ.get("RESEARCH_EMBEDDING_MODEL", "hash-64"))
    monkeypatch.setenv("RESEARCH_ALLOW_HASH_EMBEDDINGS", os.environ.get("RESEARCH_ALLOW_HASH_EMBEDDINGS", "true"))
    monkeypatch.setenv("RESEARCH_ALLOW_PRIVATE_SOURCE_URLS", "true")


def pytest_sessionstart(session: pytest.Session) -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return
    try:
        database_name = (make_url(database_url).database or "").lower()
    except Exception as exc:
        raise pytest.UsageError(f"Unable to validate DATABASE_URL for tests: {exc}") from exc
    if "test" not in database_name:
        raise pytest.UsageError(
            "Refusing to run tests against a non-test database. "
            "Use `make test` or `python scripts/run_pytest_isolated.py`."
        )


@pytest.fixture(autouse=True)
def reset_database() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return
    engine = sa.create_engine(database_url, future=True)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                TRUNCATE
                    research_digest_feedback,
                    research_decision_feedback,
                    research_document_insights,
                    research_retrieval_feedback,
                    research_bootstrap_events,
                    research_relevance_scores,
                    research_query_logs,
                    research_embeddings,
                    research_chunks,
                    research_documents,
                    research_ingestion_runs,
                    research_source_policies,
                    research_sources,
                    intel_ingest_jobs,
                    intel_article_sections,
                    intel_articles,
                    tasks,
                    projects
                RESTART IDENTITY CASCADE
                """
            )
        )
