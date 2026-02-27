from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009_research_source_hardening"
down_revision = "0008_research_relevance_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_source_policies",
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "research_source_policies",
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "research_source_policies",
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_research_source_policies_cooldown_until",
        "research_source_policies",
        ["cooldown_until"],
    )


def downgrade() -> None:
    op.drop_index("ix_research_source_policies_cooldown_until", table_name="research_source_policies")
    op.drop_column("research_source_policies", "last_error")
    op.drop_column("research_source_policies", "cooldown_until")
    op.drop_column("research_source_policies", "consecutive_failures")
