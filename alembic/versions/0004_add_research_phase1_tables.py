from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_research_phase1"
down_revision = "0003_intel_ingest_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_sources",
        sa.Column("source_id", sa.Text(), primary_key=True),
        sa.Column("topic_key", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("base_url_original", sa.Text(), nullable=False),
        sa.Column("base_url_canonical", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_research_sources_topic_key", "research_sources", ["topic_key"])
    op.create_index("ix_research_sources_enabled", "research_sources", ["enabled"])
    op.create_index(
        "uq_research_sources_topic_kind_canonical",
        "research_sources",
        ["topic_key", "kind", "base_url_canonical"],
        unique=True,
    )

    op.create_table(
        "research_source_policies",
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("poll_interval_minutes", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("rate_limit_per_hour", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("robots_mode", sa.Text(), nullable=False, server_default=sa.text("'strict'")),
        sa.Column("max_items_per_run", sa.Integer(), nullable=False, server_default=sa.text("50")),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["source_id"], ["research_sources.source_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("source_id"),
    )

    op.create_table(
        "research_ingestion_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("topic_key", sa.Text(), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column(
            "requested_source_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "selected_source_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("items_seen", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_new", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_deduped", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("items_failed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "errors",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_research_runs_status_created_at", "research_ingestion_runs", ["status", "created_at"])
    op.create_index("ix_research_runs_topic_key", "research_ingestion_runs", ["topic_key"])
    op.create_index("ix_research_runs_idempotency_key", "research_ingestion_runs", ["idempotency_key"])

    op.create_table(
        "research_documents",
        sa.Column("document_id", sa.Text(), primary_key=True),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("url_original", sa.Text(), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'discovered'")),
        sa.Column("raw_payload", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.Text(), nullable=True),
        sa.Column(
            "fetch_meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "extraction_meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "enrichment_meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["source_id"], ["research_sources.source_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["research_ingestion_runs.run_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_research_documents_source_id", "research_documents", ["source_id"])
    op.create_index("ix_research_documents_status", "research_documents", ["status"])
    op.create_index("ix_research_documents_canonical_url", "research_documents", ["canonical_url"])


def downgrade() -> None:
    op.drop_index("ix_research_documents_canonical_url", table_name="research_documents")
    op.drop_index("ix_research_documents_status", table_name="research_documents")
    op.drop_index("ix_research_documents_source_id", table_name="research_documents")
    op.drop_table("research_documents")

    op.drop_index("ix_research_runs_idempotency_key", table_name="research_ingestion_runs")
    op.drop_index("ix_research_runs_topic_key", table_name="research_ingestion_runs")
    op.drop_index("ix_research_runs_status_created_at", table_name="research_ingestion_runs")
    op.drop_table("research_ingestion_runs")

    op.drop_table("research_source_policies")

    op.drop_index("uq_research_sources_topic_kind_canonical", table_name="research_sources")
    op.drop_index("ix_research_sources_enabled", table_name="research_sources")
    op.drop_index("ix_research_sources_topic_key", table_name="research_sources")
    op.drop_table("research_sources")
