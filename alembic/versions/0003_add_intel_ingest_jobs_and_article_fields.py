from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_intel_ingest_jobs"
down_revision = "0002_add_intel_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intel_ingest_jobs",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("url_original", sa.Text(), nullable=False),
        sa.Column("url_canonical", sa.Text(), nullable=False),
        sa.Column("article_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_intel_ingest_jobs_status_created_at", "intel_ingest_jobs", ["status", "created_at"])
    op.create_index("ix_intel_ingest_jobs_article_id", "intel_ingest_jobs", ["article_id"])

    op.add_column("intel_articles", sa.Column("url_original", sa.Text(), nullable=True))
    op.add_column("intel_articles", sa.Column("raw_html", sa.Text(), nullable=True))
    op.add_column("intel_articles", sa.Column("extracted_text", sa.Text(), nullable=True))
    op.add_column("intel_articles", sa.Column("http_status", sa.Integer(), nullable=True))
    op.add_column("intel_articles", sa.Column("content_type", sa.Text(), nullable=True))
    op.add_column("intel_articles", sa.Column("etag", sa.Text(), nullable=True))
    op.add_column("intel_articles", sa.Column("last_modified", sa.Text(), nullable=True))
    op.add_column(
        "intel_articles",
        sa.Column("fetch_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "intel_articles",
        sa.Column("extraction_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "intel_articles",
        sa.Column("enrichment_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "intel_articles",
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
    )
    op.add_column(
        "intel_articles",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column(
        "intel_articles",
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("intel_articles", "tags")
    op.drop_column("intel_articles", "updated_at")
    op.drop_column("intel_articles", "status")
    op.drop_column("intel_articles", "enrichment_meta")
    op.drop_column("intel_articles", "extraction_meta")
    op.drop_column("intel_articles", "fetch_meta")
    op.drop_column("intel_articles", "last_modified")
    op.drop_column("intel_articles", "etag")
    op.drop_column("intel_articles", "content_type")
    op.drop_column("intel_articles", "http_status")
    op.drop_column("intel_articles", "extracted_text")
    op.drop_column("intel_articles", "raw_html")
    op.drop_column("intel_articles", "url_original")

    op.drop_index("ix_intel_ingest_jobs_article_id", table_name="intel_ingest_jobs")
    op.drop_index("ix_intel_ingest_jobs_status_created_at", table_name="intel_ingest_jobs")
    op.drop_table("intel_ingest_jobs")
