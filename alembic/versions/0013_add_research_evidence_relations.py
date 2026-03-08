from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013_research_evidence_relations"
down_revision = "0012_research_decision_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column_name, server_default in [
        ("topic_tags", "'[]'::jsonb"),
        ("entity_tags", "'[]'::jsonb"),
        ("problem_tags", "'[]'::jsonb"),
        ("intervention_tags", "'[]'::jsonb"),
        ("tradeoff_dimensions", "'[]'::jsonb"),
        ("decision_domains", "'[]'::jsonb"),
        ("applicability_conditions", "'[]'::jsonb"),
    ]:
        op.add_column(
            "research_document_insights",
            sa.Column(column_name, postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text(server_default)),
        )
    for column_name, server_default in [
        ("source_class", "'external_commentary'"),
        ("publisher_type", "'independent'"),
    ]:
        op.add_column(
            "research_document_insights",
            sa.Column(column_name, sa.Text(), nullable=False, server_default=sa.text(server_default)),
        )
    for column_name in [
        "evidence_strength",
        "freshness_score",
        "source_trust_tier",
        "coverage_score",
        "internal_coverage_score",
        "external_coverage_score",
        "evidence_quality",
    ]:
        op.add_column(
            "research_document_insights",
            sa.Column(column_name, sa.Float(), nullable=False, server_default=sa.text("0.0")),
        )
    for column_name in ["corroboration_count", "contradiction_count"]:
        op.add_column(
            "research_document_insights",
            sa.Column(column_name, sa.Integer(), nullable=False, server_default=sa.text("0")),
        )
    for column_name in ["staleness_flag", "superseded_flag"]:
        op.add_column(
            "research_document_insights",
            sa.Column(column_name, sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
    op.add_column("research_document_insights", sa.Column("superseded_by_insight_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.create_index(
        "ix_research_document_insights_problem_tags",
        "research_document_insights",
        ["problem_tags"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_research_document_insights_intervention_tags",
        "research_document_insights",
        ["intervention_tags"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_research_document_insights_topic_tags",
        "research_document_insights",
        ["topic_tags"],
        postgresql_using="gin",
    )

    op.create_table(
        "research_evidence_relations",
        sa.Column("relation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("from_insight_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_document_insights.insight_id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_insight_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_document_insights.insight_id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_research_evidence_relations_from", "research_evidence_relations", ["from_insight_id", "relation_type"])
    op.create_index("ix_research_evidence_relations_to", "research_evidence_relations", ["to_insight_id", "relation_type"])


def downgrade() -> None:
    op.drop_index("ix_research_evidence_relations_to", table_name="research_evidence_relations")
    op.drop_index("ix_research_evidence_relations_from", table_name="research_evidence_relations")
    op.drop_table("research_evidence_relations")

    op.drop_index("ix_research_document_insights_topic_tags", table_name="research_document_insights")
    op.drop_index("ix_research_document_insights_intervention_tags", table_name="research_document_insights")
    op.drop_index("ix_research_document_insights_problem_tags", table_name="research_document_insights")

    for column_name in [
        "superseded_by_insight_id",
        "superseded_flag",
        "staleness_flag",
        "evidence_quality",
        "external_coverage_score",
        "internal_coverage_score",
        "coverage_score",
        "contradiction_count",
        "corroboration_count",
        "source_trust_tier",
        "applicability_conditions",
        "freshness_score",
        "evidence_strength",
        "publisher_type",
        "source_class",
        "decision_domains",
        "tradeoff_dimensions",
        "intervention_tags",
        "problem_tags",
        "entity_tags",
        "topic_tags",
    ]:
        op.drop_column("research_document_insights", column_name)
