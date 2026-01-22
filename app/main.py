from __future__ import annotations

from typing import Any, Dict, List

from fastapi import Depends, FastAPI, Header, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings, settings as default_settings
from app.models import (
    ProjectResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SyncProjectsRequest,
    SyncTasksRequest,
    TaskResponse,
    TaskSearchRequest,
)
from app.storage.db import (
    check_db,
    create_db_engine,
    get_project,
    get_task,
    search_projects,
    search_tasks,
    upsert_projects,
    upsert_tasks,
)
from app.util.scoring import score_match


def create_app(app_settings: Settings | None = None) -> FastAPI:
    app_settings = app_settings or default_settings
    app = FastAPI()

    app.state.settings = app_settings
    app.state.engine = create_db_engine(app_settings.database_url)

    def get_settings() -> Settings:
        return app.state.settings

    def require_bearer(
        authorization: str | None = Header(default=None),
        settings: Settings = Depends(get_settings),
    ) -> None:
        if not authorization:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
        try:
            scheme, token = authorization.split(" ", 1)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")
        if scheme.lower() != "bearer" or token != settings.context_api_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")

    @app.get("/health")
    def health() -> Dict[str, str]:
        try:
            check_db(app.state.engine)
        except Exception:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")
        return {"status": "ok"}

    @app.get("/version")
    def version(settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
        return {"version": settings.version, "git_sha": settings.git_sha}

    @app.post("/v1/projects/sync")
    def sync_projects(
        payload: SyncProjectsRequest,
        _: None = Depends(require_bearer),
    ) -> Dict[str, Any]:
        try:
            count = upsert_projects(
                app.state.engine,
                items=[item.model_dump() for item in payload.items],
                source=payload.source,
            )
        except SQLAlchemyError:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")
        return {"count": count}

    @app.post("/v1/tasks/sync")
    def sync_tasks(
        payload: SyncTasksRequest,
        _: None = Depends(require_bearer),
    ) -> Dict[str, Any]:
        try:
            count = upsert_tasks(
                app.state.engine,
                items=[item.model_dump() for item in payload.items],
                source=payload.source,
            )
        except SQLAlchemyError:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable")
        return {"count": count}

    @app.post("/v1/projects/search", response_model=SearchResponse)
    def search_projects_endpoint(
        payload: SearchRequest,
        _: None = Depends(require_bearer),
    ) -> SearchResponse:
        rows = search_projects(app.state.engine, payload.query, payload.limit)
        results: List[SearchResult] = []
        for row in rows:
            score = score_match(payload.query, row.get("name", ""))
            results.append(
                SearchResult(
                    id=row["project_id"],
                    label=row.get("name", ""),
                    score=score,
                    status=row.get("status"),
                    meta={"source": row.get("source"), "updated_at": row.get("updated_at")},
                )
            )
        results.sort(key=lambda item: item.score, reverse=True)
        return SearchResponse(results=results[: payload.limit])

    @app.post("/v1/tasks/search", response_model=SearchResponse)
    def search_tasks_endpoint(
        payload: TaskSearchRequest,
        _: None = Depends(require_bearer),
    ) -> SearchResponse:
        rows = search_tasks(
            app.state.engine,
            query=payload.query,
            limit=payload.limit,
            project_id=payload.project_id,
            status=payload.status,
        )
        results: List[SearchResult] = []
        for row in rows:
            score = score_match(payload.query, row.get("title", ""))
            results.append(
                SearchResult(
                    id=row["task_id"],
                    label=row.get("title", ""),
                    score=score,
                    status=row.get("status"),
                    meta={
                        "project_id": row.get("project_id"),
                        "priority": row.get("priority"),
                        "due": row.get("due"),
                        "source": row.get("source"),
                        "updated_at": row.get("updated_at"),
                    },
                )
            )
        results.sort(key=lambda item: item.score, reverse=True)
        return SearchResponse(results=results[: payload.limit])

    @app.get("/v1/projects/{project_id}", response_model=ProjectResponse)
    def get_project_endpoint(
        project_id: str,
        _: None = Depends(require_bearer),
    ) -> ProjectResponse:
        row = get_project(app.state.engine, project_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return ProjectResponse(**row)

    @app.get("/v1/tasks/{task_id}", response_model=TaskResponse)
    def get_task_endpoint(
        task_id: str,
        _: None = Depends(require_bearer),
    ) -> TaskResponse:
        row = get_task(app.state.engine, task_id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
        return TaskResponse(**row)

    return app


app = create_app()
