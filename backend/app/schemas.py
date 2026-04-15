from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ItemKind = Literal["userstory", "task", "issue"]


class LoginRequest(BaseModel):
    username: str
    password: str


class SessionUser(BaseModel):
    id: int
    full_name: str
    email: str | None = None
    username: str | None = None


class SprintOption(BaseModel):
    id: int
    name: str
    estimated_start: str | None = None
    estimated_finish: str | None = None
    closed: bool = False


class StatusOption(BaseModel):
    id: int
    name: str
    color: str | None = None


class UserOption(BaseModel):
    id: int
    full_name: str
    username: str | None = None
    role_name: str | None = None
    role_group: str | None = None


class TrackerItem(BaseModel):
    kind: ItemKind
    id: int
    ref: int | None = None
    subject: str
    status_id: int | None = None
    status_name: str = ""
    status_color: str | None = None
    assignees: list[UserOption] = Field(default_factory=list)
    watchers: list[UserOption] = Field(default_factory=list)
    sprint_id: int | None = None
    sprint_name: str | None = None
    is_no_sprint: bool = False
    updated_at: str | None = None
    created_at: str | None = None
    due_date: str | None = None
    tags: list[str] = Field(default_factory=list)
    severity: str | None = None
    priority: str | None = None
    url: str | None = None


class WarningSummary(BaseModel):
    near_sprint_end: list[TrackerItem] = Field(default_factory=list)
    stale_items: list[TrackerItem] = Field(default_factory=list)
    missing_qc: list[TrackerItem] = Field(default_factory=list)


class DashboardCounts(BaseModel):
    near_sprint_end: int = 0
    stale_items: int = 0
    missing_qc: int = 0


class MetadataResponse(BaseModel):
    project_name: str
    auto_refresh_minutes: int
    qc_names: list[str]
    me: SessionUser
    sprints: list[SprintOption]
    statuses: dict[str, list[StatusOption]]
    users: list[UserOption]


class ItemsResponse(BaseModel):
    items: list[TrackerItem]


class ItemUpdateRequest(BaseModel):
    status_id: int | None = None
    assignee_ids: list[int] | None = None
    watcher_ids: list[int] | None = None
    sprint_id: int | None = None
    comment: str | None = None


class ItemUpdateResponse(BaseModel):
    ok: bool = True
    item: TrackerItem
