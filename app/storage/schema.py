from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, MetaData, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

metadata = MetaData()

projects = Table(
    "projects",
    metadata,
    Column("project_id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("status", Text, nullable=True),
    Column("source", Text, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("raw", JSONB, nullable=True),
    Index("ix_projects_name", "name"),
    Index("ix_projects_status", "status"),
)

tasks = Table(
    "tasks",
    metadata,
    Column("task_id", Text, primary_key=True),
    Column("title", Text, nullable=False),
    Column("status", Text, nullable=True),
    Column("priority", Text, nullable=True),
    Column("due", Text, nullable=True),
    Column("project_id", Text, nullable=True),
    Column("source", Text, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("raw", JSONB, nullable=True),
    Index("ix_tasks_title", "title"),
    Index("ix_tasks_status", "status"),
    Index("ix_tasks_project_id", "project_id"),
)

intel_articles = Table(
    "intel_articles",
    metadata,
    Column("article_id", Text, primary_key=True),
    Column("url", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("publisher", Text, nullable=True),
    Column("author", Text, nullable=True),
    Column("published_at", DateTime(timezone=True), nullable=True),
    Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("topics", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("summary", Text, nullable=False, server_default=text("''")),
    Column("signals", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("outline", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("outbound_links", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Index("ix_intel_articles_ingested_at", "ingested_at"),
    Index("ix_intel_articles_published_at", "published_at"),
)

intel_article_sections = Table(
    "intel_article_sections",
    metadata,
    Column(
        "article_id",
        Text,
        ForeignKey("intel_articles.article_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("section_id", Text, primary_key=True),
    Column("heading", Text, nullable=False, server_default=text("''")),
    Column("content", Text, nullable=False),
    Column("rank", Integer, nullable=False, server_default=text("0")),
)
