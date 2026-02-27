from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_research_extraction"
down_revision = "0004_research_phase1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_documents", sa.Column("extracted_text", sa.Text(), nullable=True))
    op.add_column("research_documents", sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("research_documents", "extracted_at")
    op.drop_column("research_documents", "extracted_text")
