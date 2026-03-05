from __future__ import annotations

import os

import pytest
import sqlalchemy as sa


@pytest.fixture(autouse=True)
def reset_database() -> None:
    engine = sa.create_engine(os.environ["DATABASE_URL"], future=True)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                TRUNCATE
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
