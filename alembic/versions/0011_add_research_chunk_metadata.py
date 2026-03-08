from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_research_chunk_metadata"
down_revision = "0010_research_bootstrap_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_chunks",
        sa.Column(
            "chunk_meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("research_chunks", "chunk_meta")
