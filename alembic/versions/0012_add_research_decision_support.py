from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012_research_decision_support"
down_revision = "0011_research_chunk_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_sources", sa.Column("publisher_type", sa.Text(), nullable=False, server_default=sa.text("'independent'")))
    op.add_column("research_sources", sa.Column("source_class", sa.Text(), nullable=False, server_default=sa.text("'external_commentary'")))
    op.add_column(
        "research_sources",
        sa.Column("default_decision_domains", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )

    op.add_column("research_documents", sa.Column("published_at_confidence", sa.Float(), nullable=False, server_default=sa.text("0.0")))
    op.add_column("research_documents", sa.Column("content_type", sa.Text(), nullable=False, server_default=sa.text("'company_blog'")))
    op.add_column("research_documents", sa.Column("publisher_type", sa.Text(), nullable=False, server_default=sa.text("'independent'")))
    op.add_column("research_documents", sa.Column("source_class", sa.Text(), nullable=False, server_default=sa.text("'external_commentary'")))
    op.add_column("research_documents", sa.Column("summary_short", sa.Text(), nullable=False, server_default=sa.text("''")))
    op.add_column("research_documents", sa.Column("why_it_matters", sa.Text(), nullable=False, server_default=sa.text("''")))
    op.add_column("research_documents", sa.Column("topic_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("research_documents", sa.Column("entity_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("research_documents", sa.Column("use_case_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("research_documents", sa.Column("decision_domains", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("research_documents", sa.Column("quality_signals", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("research_documents", sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("research_documents", sa.Column("notable_quotes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("research_documents", sa.Column("key_claims", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("research_documents", sa.Column("tradeoffs", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("research_documents", sa.Column("recommendations", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("research_documents", sa.Column("novelty_score", sa.Float(), nullable=False, server_default=sa.text("0.0")))
    op.add_column("research_documents", sa.Column("evidence_density_score", sa.Float(), nullable=False, server_default=sa.text("0.0")))
    op.add_column("research_documents", sa.Column("document_signal_score", sa.Float(), nullable=False, server_default=sa.text("0.0")))
    op.add_column("research_documents", sa.Column("embedding_ready", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    op.create_table(
        "research_document_insights",
        sa.Column("insight_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", sa.Text(), sa.ForeignKey("research_documents.document_id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("insight_type", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_research_document_insights_document_type", "research_document_insights", ["document_id", "insight_type"])
    op.create_index("ix_research_document_insights_type", "research_document_insights", ["insight_type"])

    op.create_table(
        "research_decision_feedback",
        sa.Column("feedback_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trace_id", sa.Text(), nullable=False),
        sa.Column("topic_key", sa.Text(), nullable=False),
        sa.Column("decision_domain", sa.Text(), nullable=True),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("followed_recommendation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("evidence_sufficient", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_research_decision_feedback_topic_created_at", "research_decision_feedback", ["topic_key", "created_at"])

    op.create_table(
        "research_digest_feedback",
        sa.Column("feedback_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("topic_key", sa.Text(), nullable=False),
        sa.Column("cluster_key", sa.Text(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("selected_for_publication", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("quotes_usable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("metrics_usable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_research_digest_feedback_topic_created_at", "research_digest_feedback", ["topic_key", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_research_digest_feedback_topic_created_at", table_name="research_digest_feedback")
    op.drop_table("research_digest_feedback")
    op.drop_index("ix_research_decision_feedback_topic_created_at", table_name="research_decision_feedback")
    op.drop_table("research_decision_feedback")
    op.drop_index("ix_research_document_insights_type", table_name="research_document_insights")
    op.drop_index("ix_research_document_insights_document_type", table_name="research_document_insights")
    op.drop_table("research_document_insights")

    for column_name in [
        "embedding_ready",
        "document_signal_score",
        "evidence_density_score",
        "novelty_score",
        "recommendations",
        "tradeoffs",
        "key_claims",
        "notable_quotes",
        "metrics",
        "quality_signals",
        "decision_domains",
        "use_case_tags",
        "entity_tags",
        "topic_tags",
        "why_it_matters",
        "summary_short",
        "source_class",
        "publisher_type",
        "content_type",
        "published_at_confidence",
    ]:
        op.drop_column("research_documents", column_name)

    for column_name in ["default_decision_domains", "source_class", "publisher_type"]:
        op.drop_column("research_sources", column_name)
