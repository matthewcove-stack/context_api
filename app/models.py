from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic import AliasChoices


class ProjectUpsert(BaseModel):
    project_id: str = Field(validation_alias=AliasChoices("project_id", "id"))
    name: str
    status: Optional[str] = None
    updated_at: Optional[datetime] = None
    raw: Optional[Dict[str, Any]] = None


class TaskUpsert(BaseModel):
    task_id: str = Field(validation_alias=AliasChoices("task_id", "id"))
    title: str
    status: Optional[str] = None
    priority: Optional[str] = None
    due: Optional[str] = None
    project_id: Optional[str] = None
    updated_at: Optional[datetime] = None
    raw: Optional[Dict[str, Any]] = None


class SyncProjectsRequest(BaseModel):
    source: Optional[str] = None
    items: List[ProjectUpsert]


class SyncTasksRequest(BaseModel):
    source: Optional[str] = None
    items: List[TaskUpsert]


class SearchRequest(BaseModel):
    query: str
    limit: int = 5


class TaskSearchRequest(BaseModel):
    query: str
    limit: int = 5
    project_id: Optional[str] = None
    status: Optional[str] = None


class SearchResult(BaseModel):
    id: str
    label: str
    score: float
    status: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class SearchResponse(BaseModel):
    results: List[SearchResult]


class ProjectResponse(BaseModel):
    project_id: str
    name: str
    status: Optional[str] = None
    updated_at: Optional[datetime] = None
    source: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None


class TaskResponse(BaseModel):
    task_id: str
    title: str
    status: Optional[str] = None
    priority: Optional[str] = None
    due: Optional[str] = None
    project_id: Optional[str] = None
    updated_at: Optional[datetime] = None
    source: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None
