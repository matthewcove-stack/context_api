from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_research_relevance_feedback"
down_revision = "0007_research_query_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_source_policies",
        sa.Column("source_weight", sa.Float(), nullable=False, server_default=sa.text("1.0")),
    )

    op.create_table(
        "research_relevance_scores",
        sa.Column("score_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column("topic_key", sa.Text(), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("score_total", sa.Float(), nullable=False),
        sa.Column("score_lexical", sa.Float(), nullable=False),
        sa.Column("score_embedding", sa.Float(), nullable=False),
        sa.Column("score_recency", sa.Float(), nullable=False),
        sa.Column("score_source_weight", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["document_id"], ["research_documents.document_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("score_id"),
    )
    op.create_index(
        "ix_research_relevance_scores_trace",
        "research_relevance_scores",
        ["trace_id", "created_at"],
    )

    op.create_table(
        "research_retrieval_feedback",
        sa.Column("feedback_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column("query_log_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["document_id"], ["research_documents.document_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["query_log_id"], ["research_query_logs.query_log_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("feedback_id"),
    )
    op.create_index(
        "ix_research_retrieval_feedback_trace",
        "research_retrieval_feedback",
        ["trace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_research_retrieval_feedback_trace", table_name="research_retrieval_feedback")
    op.drop_table("research_retrieval_feedback")

    op.drop_index("ix_research_relevance_scores_trace", table_name="research_relevance_scores")
    op.drop_table("research_relevance_scores")

    op.drop_column("research_source_policies", "source_weight")
