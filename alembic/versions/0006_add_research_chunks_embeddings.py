from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_research_chunks_embeddings"
down_revision = "0005_research_extraction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_chunks",
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["document_id"], ["research_documents.document_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("document_id", "chunk_id"),
    )
    op.create_index("ix_research_chunks_document_id", "research_chunks", ["document_id"])
    op.create_index("ix_research_chunks_ordinal", "research_chunks", ["ordinal"])
    op.execute(
        """
        CREATE INDEX ix_research_chunks_search
        ON research_chunks
        USING GIN (
            to_tsvector('english', coalesce(content, ''))
        )
        """
    )

    op.create_table(
        "research_embeddings",
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("embedding_model_id", sa.Text(), nullable=False),
        sa.Column("vector", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["document_id", "chunk_id"],
            ["research_chunks.document_id", "research_chunks.chunk_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("document_id", "chunk_id", "embedding_model_id"),
    )
    op.create_index("ix_research_embeddings_document_model", "research_embeddings", ["document_id", "embedding_model_id"])

    op.add_column("research_documents", sa.Column("embedding_model_id", sa.Text(), nullable=True))
    op.add_column("research_documents", sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("research_documents", "embedded_at")
    op.drop_column("research_documents", "embedding_model_id")

    op.drop_index("ix_research_embeddings_document_model", table_name="research_embeddings")
    op.drop_table("research_embeddings")

    op.execute("DROP INDEX IF EXISTS ix_research_chunks_search")
    op.drop_index("ix_research_chunks_ordinal", table_name="research_chunks")
    op.drop_index("ix_research_chunks_document_id", table_name="research_chunks")
    op.drop_table("research_chunks")
