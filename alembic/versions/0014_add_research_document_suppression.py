from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0014_doc_suppress"
down_revision = "0013_research_evidence_relations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_documents",
        sa.Column("suppressed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "research_documents",
        sa.Column("suppression_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "research_documents",
        sa.Column("suppressed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_research_documents_suppressed",
        "research_documents",
        ["suppressed"],
    )


def downgrade() -> None:
    op.drop_index("ix_research_documents_suppressed", table_name="research_documents")
    op.drop_column("research_documents", "suppressed_at")
    op.drop_column("research_documents", "suppression_reason")
    op.drop_column("research_documents", "suppressed")
