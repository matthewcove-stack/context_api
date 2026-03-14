from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.models import (
    DashboardSummary,
    InboxResponse,
    ProjectListItem,
    ProjectResponse,
    ProjectWorkspaceResponse,
    RelatedContextItem,
    ReviewPackResponse,
    TaskListItem,
    TodayDashboardResponse,
    UpcomingResponse,
)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_due(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = str(value).strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _status_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_done(status: Any) -> bool:
    return _status_key(status) in {"done", "complete", "completed", "cancelled", "canceled"}


def _is_waiting(status: Any) -> bool:
    return _status_key(status) in {"waiting", "blocked", "on hold", "paused"}


def _task_item(row: Dict[str, Any], *, today: date) -> TaskListItem:
    due_dt = _parse_due(row.get("due"))
    due_day = due_dt.astimezone(timezone.utc).date() if due_dt else None
    return TaskListItem(
        task_id=str(row.get("task_id") or ""),
        title=str(row.get("title") or ""),
        status=str(row.get("status") or "") or None,
        priority=str(row.get("priority") or "") or None,
        due=str(row.get("due") or "") or None,
        project_id=str(row.get("project_id") or "") or None,
        project_name=str(row.get("project_name") or "") or None,
        updated_at=row.get("updated_at"),
        is_overdue=bool(due_day and due_day < today and not _is_done(row.get("status"))),
        is_due_today=bool(due_day and due_day == today and not _is_done(row.get("status"))),
    )


def _project_health(open_count: int, overdue_count: int, done_count: int) -> str:
    if overdue_count > 0:
        return "at_risk"
    if open_count == 0 and done_count > 0:
        return "complete"
    if open_count >= 5:
        return "active"
    return "steady"


def _project_items(project_rows: List[Dict[str, Any]], task_rows: List[Dict[str, Any]]) -> List[ProjectListItem]:
    counts: Dict[str, Dict[str, int]] = {}
    latest_updates: Dict[str, Optional[datetime]] = {}
    today = _now_utc().date()
    for row in task_rows:
        project_id = str(row.get("project_id") or "").strip()
        if not project_id:
            continue
        counter = counts.setdefault(
            project_id,
            {"open": 0, "done": 0, "overdue": 0, "total": 0},
        )
        counter["total"] += 1
        if _is_done(row.get("status")):
            counter["done"] += 1
        else:
            counter["open"] += 1
            due_dt = _parse_due(row.get("due"))
            if due_dt and due_dt.astimezone(timezone.utc).date() < today:
                counter["overdue"] += 1
        latest = row.get("updated_at")
        if latest and (
            project_id not in latest_updates
            or latest_updates[project_id] is None
            or latest > latest_updates[project_id]
        ):
            latest_updates[project_id] = latest

    items: List[ProjectListItem] = []
    for row in project_rows:
        project_id = str(row.get("project_id") or "")
        counter = counts.get(project_id, {"open": 0, "done": 0, "overdue": 0, "total": 0})
        items.append(
            ProjectListItem(
                project_id=project_id,
                name=str(row.get("name") or ""),
                status=str(row.get("status") or "") or None,
                open_task_count=counter["open"],
                done_task_count=counter["done"],
                overdue_task_count=counter["overdue"],
                total_task_count=counter["total"],
                updated_at=latest_updates.get(project_id) or row.get("updated_at"),
                health=_project_health(counter["open"], counter["overdue"], counter["done"]),
            )
        )
    items.sort(key=lambda item: (item.overdue_task_count, item.open_task_count, item.name.lower()), reverse=True)
    return items


def build_today_dashboard(project_rows: List[Dict[str, Any]], task_rows: List[Dict[str, Any]]) -> TodayDashboardResponse:
    now = _now_utc()
    today = now.date()
    open_items: List[TaskListItem] = []
    done_items: List[TaskListItem] = []
    for row in task_rows:
        item = _task_item(row, today=today)
        if _is_done(item.status):
            done_items.append(item)
        else:
            open_items.append(item)

    overdue = [item for item in open_items if item.is_overdue]
    waiting = [item for item in open_items if _is_waiting(item.status)]
    today_items = [
        item
        for item in open_items
        if item.is_due_today or _status_key(item.status) == "in progress"
    ]
    next_items = []
    for item in open_items:
        if item in overdue or item in waiting or item in today_items:
            continue
        due_dt = _parse_due(item.due)
        if due_dt is None:
            continue
        due_day = due_dt.astimezone(timezone.utc).date()
        if today < due_day <= today + timedelta(days=7):
            next_items.append(item)

    recent_captures = sorted(
        open_items,
        key=lambda item: item.updated_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )[:6]
    projects = _project_items(project_rows, task_rows)[:6]

    return TodayDashboardResponse(
        generated_at=now,
        summary=DashboardSummary(
            overdue_count=len(overdue),
            due_today_count=len(today_items),
            next_count=len(next_items),
            waiting_count=len(waiting),
            inbox_count=sum(1 for item in open_items if not item.project_id),
        ),
        overdue=overdue[:8],
        today=today_items[:8],
        next=next_items[:8],
        waiting=waiting[:8],
        recent_captures=recent_captures,
        projects=projects,
    )


def build_upcoming(task_rows: List[Dict[str, Any]]) -> UpcomingResponse:
    today = _now_utc().date()
    items = []
    for row in task_rows:
        if _is_done(row.get("status")):
            continue
        item = _task_item(row, today=today)
        due_dt = _parse_due(item.due)
        if due_dt is None:
            continue
        due_day = due_dt.astimezone(timezone.utc).date()
        if today <= due_day <= today + timedelta(days=14):
            items.append(item)
    items.sort(key=lambda item: (_parse_due(item.due) or datetime.max.replace(tzinfo=timezone.utc), item.title.lower()))
    return UpcomingResponse(generated_at=_now_utc(), items=items[:20])


def build_inbox(task_rows: List[Dict[str, Any]]) -> InboxResponse:
    today = _now_utc().date()
    items = [
        _task_item(row, today=today)
        for row in task_rows
        if not _is_done(row.get("status")) and not str(row.get("project_id") or "").strip()
    ]
    items.sort(key=lambda item: item.updated_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return InboxResponse(generated_at=_now_utc(), items=items[:25])


def build_project_workspace(
    project_row: Dict[str, Any],
    project_rows: List[Dict[str, Any]],
    task_rows: List[Dict[str, Any]],
    related_topics: List[Dict[str, Any]],
) -> ProjectWorkspaceResponse:
    project_id = str(project_row.get("project_id") or "")
    today = _now_utc().date()
    project_tasks = [_task_item(row, today=today) for row in task_rows if str(row.get("project_id") or "") == project_id]
    project_tasks.sort(
        key=lambda item: (
            _is_done(item.status),
            _parse_due(item.due) or datetime.max.replace(tzinfo=timezone.utc),
            item.title.lower(),
        )
    )
    summary = next(
        (
            item
            for item in _project_items(project_rows, task_rows)
            if item.project_id == project_id
        ),
        ProjectListItem(
            project_id=project_id,
            name=str(project_row.get("name") or ""),
            status=str(project_row.get("status") or "") or None,
        ),
    )
    return ProjectWorkspaceResponse(
        generated_at=_now_utc(),
        project=ProjectResponse(**project_row),
        summary=summary,
        tasks=project_tasks[:50],
        related_context=[
            RelatedContextItem(
                kind="research_topic",
                id=str(topic.get("topic_key") or ""),
                label=str(topic.get("label") or ""),
                description=str(topic.get("description") or "") or None,
            )
            for topic in related_topics[:4]
            if str(topic.get("topic_key") or "").strip()
        ],
    )


def build_review_pack(
    *,
    mode: str,
    project_rows: List[Dict[str, Any]],
    task_rows: List[Dict[str, Any]],
) -> ReviewPackResponse:
    normalized_mode = "weekly" if mode == "weekly" else "daily"
    now = _now_utc()
    today = now.date()
    recent_done_window = timedelta(days=7 if normalized_mode == "weekly" else 2)
    stalled_window = timedelta(days=14 if normalized_mode == "weekly" else 7)

    task_items = [_task_item(row, today=today) for row in task_rows]
    open_items = [item for item in task_items if not _is_done(item.status)]
    focus_items = [
        item
        for item in open_items
        if item.is_overdue or item.is_due_today or str(item.priority or "").lower() == "high"
    ]

    completed_recent = [
        item
        for item in task_items
        if _is_done(item.status)
        and item.updated_at
        and now - item.updated_at.replace(tzinfo=item.updated_at.tzinfo or timezone.utc) <= recent_done_window
    ]
    project_summaries = _project_items(project_rows, task_rows)
    stalled_projects = []
    for project in project_summaries:
        if project.health == "complete":
            continue
        updated_at = project.updated_at
        if updated_at is None:
            stalled_projects.append(project)
            continue
        candidate = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=timezone.utc)
        if now - candidate >= stalled_window:
            stalled_projects.append(project)

    return ReviewPackResponse(
        generated_at=now,
        mode="weekly" if normalized_mode == "weekly" else "daily",
        summary=DashboardSummary(
            overdue_count=sum(1 for item in open_items if item.is_overdue),
            due_today_count=sum(1 for item in open_items if item.is_due_today),
            next_count=sum(
                1
                for item in open_items
                if not item.is_overdue and not item.is_due_today and _parse_due(item.due) is not None
            ),
            waiting_count=sum(1 for item in open_items if _is_waiting(item.status)),
            inbox_count=sum(1 for item in open_items if not item.project_id),
        ),
        focus_items=focus_items[:12],
        completed_recent=sorted(
            completed_recent,
            key=lambda item: item.updated_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )[:12],
        stalled_projects=stalled_projects[:8],
    )
