from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_add_intel_tables"
down_revision = "0001_create_projects_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intel_articles",
        sa.Column("article_id", sa.Text(), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("publisher", sa.Text(), nullable=True),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "topics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("summary", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "signals",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "outline",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "outbound_links",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_index("ix_intel_articles_ingested_at", "intel_articles", ["ingested_at"])
    op.create_index("ix_intel_articles_published_at", "intel_articles", ["published_at"])
    op.execute(
        """
        CREATE INDEX ix_intel_articles_search
        ON intel_articles
        USING GIN (
            to_tsvector(
                'english',
                coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(signals::text, '')
            )
        )
        """
    )

    op.create_table(
        "intel_article_sections",
        sa.Column("article_id", sa.Text(), nullable=False),
        sa.Column("section_id", sa.Text(), nullable=False),
        sa.Column("heading", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["article_id"], ["intel_articles.article_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("article_id", "section_id"),
    )
    op.execute(
        """
        CREATE INDEX ix_intel_article_sections_search
        ON intel_article_sections
        USING GIN (
            to_tsvector('english', coalesce(content, ''))
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_intel_article_sections_search")
    op.drop_table("intel_article_sections")
    op.execute("DROP INDEX IF EXISTS ix_intel_articles_search")
    op.drop_index("ix_intel_articles_published_at", table_name="intel_articles")
    op.drop_index("ix_intel_articles_ingested_at", table_name="intel_articles")
    op.drop_table("intel_articles")
