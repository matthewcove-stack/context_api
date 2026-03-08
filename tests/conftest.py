from __future__ import annotations

import os

import pytest
import sqlalchemy as sa


@pytest.fixture(autouse=True)
def configure_research_embedding_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_EMBEDDING_MODEL", os.environ.get("RESEARCH_EMBEDDING_MODEL", "hash-64"))
    monkeypatch.setenv("RESEARCH_ALLOW_HASH_EMBEDDINGS", os.environ.get("RESEARCH_ALLOW_HASH_EMBEDDINGS", "true"))


@pytest.fixture(autouse=True)
def reset_database() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return
    allow_reset = os.environ.get("CONTEXT_API_TEST_ALLOW_DB_RESET", "").strip().lower() in {"1", "true", "yes"}
    lowered_url = database_url.lower()
    if not allow_reset and all(token not in lowered_url for token in ("_test", "test_", "/test", "localhost:5543")):
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
