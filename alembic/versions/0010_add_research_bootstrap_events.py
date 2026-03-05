from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_research_bootstrap_events"
down_revision = "0009_research_source_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_bootstrap_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic_key", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("received", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("valid", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("invalid", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("skipped_duplicate", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["run_id"], ["research_ingestion_runs.run_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_research_bootstrap_events_topic_created_at",
        "research_bootstrap_events",
        ["topic_key", "created_at"],
    )
    op.create_index(
        "ix_research_bootstrap_events_idempotency_key",
        "research_bootstrap_events",
        ["idempotency_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_research_bootstrap_events_idempotency_key", table_name="research_bootstrap_events")
    op.drop_index("ix_research_bootstrap_events_topic_created_at", table_name="research_bootstrap_events")
    op.drop_table("research_bootstrap_events")
