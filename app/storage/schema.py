from __future__ import annotations

from sqlalchemy import Column, DateTime, Index, MetaData, Table, Text
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
