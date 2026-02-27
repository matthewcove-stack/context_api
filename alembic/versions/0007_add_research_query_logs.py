from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_research_query_logs"
down_revision = "0006_research_chunks_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_query_logs",
        sa.Column("query_log_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column("topic_key", sa.Text(), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("source_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("token_budget", sa.Integer(), nullable=True),
        sa.Column("max_items", sa.Integer(), nullable=True),
        sa.Column("recency_days", sa.Integer(), nullable=True),
        sa.Column("min_relevance_score", sa.Float(), nullable=True),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "returned_document_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "returned_chunk_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("timing_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'ok'")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("query_log_id"),
    )
    op.create_index("ix_research_query_logs_topic_created_at", "research_query_logs", ["topic_key", "created_at"])
    op.create_index("ix_research_query_logs_trace_id", "research_query_logs", ["trace_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_research_query_logs_trace_id", table_name="research_query_logs")
    op.drop_index("ix_research_query_logs_topic_created_at", table_name="research_query_logs")
    op.drop_table("research_query_logs")
