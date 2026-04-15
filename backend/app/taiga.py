from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, time
from typing import Any, Iterable

import httpx

from .config import AppConfig
from .schemas import (
    ItemsResponse,
    MetadataResponse,
    SessionUser,
    SprintOption,
    StatusOption,
    TrackerItem,
    UserOption,
    WarningSummary,
)


_MEMORY_CACHE: dict[str, tuple[float, Any]] = {}


def _normalize_name(value: str) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _is_cancel_status(value: str) -> bool:
    normalized = _normalize_name(value)
    return "cancel" in normalized


def _filter_qc_users(users: Iterable[UserOption], qc_names: list[str]) -> list[UserOption]:
    qc_set = {_normalize_name(name) for name in qc_names}
    return [user for user in users if user.role_group == "QC" or _normalize_name(user.full_name) in qc_set]


def _role_group_from_role_name(value: str | None) -> str | None:
    normalized = _normalize_name(value or "")
    if not normalized:
        return None
    if "qc" in normalized or "test" in normalized:
        return "QC"
    if normalized in {"product", "stakeholder"}:
        return "PO"
    if normalized in {"web", "back", "architect"}:
        return "DEV"
    return None


def _memory_cache_get(key: str) -> Any | None:
    entry = _MEMORY_CACHE.get(key)
    if not entry:
        return None
    expires_at, value = entry
    if monotonic() > expires_at:
        _MEMORY_CACHE.pop(key, None)
        return None
    return value


def _memory_cache_set(key: str, value: Any, ttl_seconds: int) -> Any:
    _MEMORY_CACHE[key] = (monotonic() + ttl_seconds, value)
    return value


def _snapshot_path(config: AppConfig, name: str) -> Path:
    return config.snapshot_dir / f"{name}.json"


def _read_snapshot(config: AppConfig, name: str) -> Any | None:
    path = _snapshot_path(config, name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_snapshot(config: AppConfig, name: str, payload: Any) -> None:
    config.snapshot_dir.mkdir(parents=True, exist_ok=True)
    _snapshot_path(config, name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _clear_snapshots(config: AppConfig) -> None:
    if not config.snapshot_dir.exists():
        return
    for path in config.snapshot_dir.glob("*.json"):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            continue


def _metadata_snapshot_missing_roles(snapshot: Any) -> bool:
    users = snapshot.get("users") if isinstance(snapshot, dict) else None
    if not isinstance(users, list) or not users:
        return False
    return any(user.get("role_group") is None for user in users if isinstance(user, dict))


def _items_snapshot_missing_roles(snapshot: Any) -> bool:
    if not isinstance(snapshot, list) or not snapshot:
        return False
    for row in snapshot:
        if not isinstance(row, dict):
            continue
        for person in [*(row.get("assignees") or []), *(row.get("watchers") or [])]:
            if isinstance(person, dict) and person.get("role_group") is None:
                return True
    return False


class TaigaClient:
    def __init__(self, config: AppConfig, token: str | None = None) -> None:
        self.config = config
        self.token = token

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _cache_key(self, name: str, extra: str = "") -> str:
        token_part = self.token or "anonymous"
        return f"{self.config.project_slug}:{token_part}:{name}:{extra}"

    def _cache_file(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.config.cache_dir / f"{digest}.json"

    def _disk_cache_get(self, key: str) -> Any | None:
        path = self._cache_file(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        cached_at = float(payload.get("cached_at", 0))
        if time() - cached_at > self.config.cache_ttl_seconds:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        return payload.get("data")

    def _disk_cache_set(self, key: str, value: Any) -> Any:
        path = self._cache_file(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"cached_at": time(), "data": value}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return value

    def _get_cached(self, key: str) -> Any | None:
        cached = _memory_cache_get(key)
        if cached is not None:
            return cached
        cached = self._disk_cache_get(key)
        if cached is not None:
            return _memory_cache_set(key, cached, self.config.cache_ttl_seconds)
        return None

    def _set_cached(self, key: str, value: Any) -> Any:
        self._disk_cache_set(key, value)
        return _memory_cache_set(key, value, self.config.cache_ttl_seconds)

    def invalidate_project_cache(self) -> None:
        prefix = f"{self.config.project_slug}:{self.token or 'anonymous'}:"
        keys_to_drop = [key for key in _MEMORY_CACHE if key.startswith(prefix)]
        for key in keys_to_drop:
            _MEMORY_CACHE.pop(key, None)
        cache_dir = self.config.cache_dir
        if not cache_dir.exists():
            return
        for file_path in cache_dir.glob("*.json"):
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            data = payload.get("data")
            # Files are hashed, so we store no raw key; easiest safe strategy is clear all cached files for this app.
            try:
                file_path.unlink(missing_ok=True)
            except OSError:
                continue

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.config.taiga_base_url}/api/v1{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=self._headers(),
            )
        response.raise_for_status()
        return response.json() if response.content else None

    async def _get_paginated(self, path: str, *, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        page = 1
        all_rows: list[dict[str, Any]] = []
        while True:
            page_params = dict(params or {})
            page_params["page"] = page
            url = f"{self.config.taiga_base_url}/api/v1{path}"
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(url, params=page_params, headers=self._headers())
            response.raise_for_status()
            rows = response.json()
            all_rows.extend(rows)
            next_page = response.headers.get("x-pagination-next")
            if not next_page or not rows:
                break
            page += 1
        return all_rows

    async def login(self, username: str, password: str) -> tuple[str, SessionUser]:
        data = await self._request(
            "POST",
            "/auth",
            json_body={"type": "normal", "username": username, "password": password},
        )
        user = SessionUser(
            id=data["id"],
            full_name=data.get("full_name") or data.get("full_name_display") or username,
            email=data.get("email"),
            username=data.get("username"),
        )
        return data["auth_token"], user

    async def get_project(self) -> dict[str, Any]:
        key = self._cache_key("project", self.config.project_slug)
        cached = self._get_cached(key)
        if cached is not None:
            return cached
        return self._set_cached(key, await self._request("GET", "/projects/by_slug", params={"slug": self.config.project_slug}))

    async def get_users(self, project_id: int) -> list[dict[str, Any]]:
        key = self._cache_key("users", str(project_id))
        cached = self._get_cached(key)
        if cached is not None:
            return cached
        return self._set_cached(key, await self._get_paginated("/users", params={"project": project_id}))

    async def get_milestones(self, project_id: int) -> list[dict[str, Any]]:
        key = self._cache_key("milestones", str(project_id))
        cached = self._get_cached(key)
        if cached is not None:
            return cached
        return self._set_cached(key, await self._get_paginated("/milestones", params={"project": project_id}))

    async def get_memberships(self, project_id: int) -> list[dict[str, Any]]:
        key = self._cache_key("memberships", str(project_id))
        cached = self._get_cached(key)
        if cached is not None:
            return cached
        return self._set_cached(key, await self._get_paginated("/memberships", params={"project": project_id}))

    async def get_statuses(self, project_id: int, kind: str) -> list[dict[str, Any]]:
        endpoint_map = {
            "userstory": "/userstory-statuses",
            "task": "/task-statuses",
            "issue": "/issue-statuses",
        }
        key = self._cache_key(f"statuses:{kind}", str(project_id))
        cached = self._get_cached(key)
        if cached is not None:
            return cached
        return self._set_cached(key, await self._request("GET", endpoint_map[kind], params={"project": project_id}))

    async def get_items(self, project_id: int, kind: str) -> list[dict[str, Any]]:
        endpoint_map = {
            "userstory": "/userstories",
            "task": "/tasks",
            "issue": "/issues",
        }
        key = self._cache_key(f"items:{kind}", str(project_id))
        cached = self._get_cached(key)
        if cached is not None:
            return cached
        return self._set_cached(key, await self._get_paginated(endpoint_map[kind], params={"project": project_id}))

    async def get_item_detail(self, kind: str, item_id: int) -> dict[str, Any]:
        endpoint_map = {
            "userstory": f"/userstories/{item_id}",
            "task": f"/tasks/{item_id}",
            "issue": f"/issues/{item_id}",
        }
        return await self._request("GET", endpoint_map[kind])

    async def update_item(self, kind: str, item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        endpoint_map = {
            "userstory": f"/userstories/{item_id}",
            "task": f"/tasks/{item_id}",
            "issue": f"/issues/{item_id}",
        }
        result = await self._request("PATCH", endpoint_map[kind], json_body=payload)
        self.invalidate_project_cache()
        return result


def _get_name_map(users: Iterable[dict[str, Any]]) -> dict[int, UserOption]:
    result: dict[int, UserOption] = {}
    for user in users:
        result[int(user["id"])] = UserOption(
            id=int(user["id"]),
            full_name=user.get("full_name_display") or user.get("full_name") or user.get("username") or "",
            username=user.get("username"),
            role_name=None,
            role_group=None,
        )
    return result


def _merge_membership_users(
    name_map: dict[int, UserOption],
    memberships: Iterable[dict[str, Any]],
) -> dict[int, UserOption]:
    for membership in memberships:
        user_id = membership.get("user")
        if user_id is None:
            continue
        user_id = int(user_id)
        if user_id not in name_map:
            name_map[user_id] = UserOption(
                id=user_id,
                full_name=membership.get("full_name") or membership.get("user_email") or str(user_id),
                username=None,
                role_name=membership.get("role_name"),
                role_group=_role_group_from_role_name(membership.get("role_name")),
            )
        else:
            existing = name_map[user_id]
            name_map[user_id] = UserOption(
                id=existing.id,
                full_name=existing.full_name,
                username=existing.username,
                role_name=membership.get("role_name") or existing.role_name,
                role_group=_role_group_from_role_name(membership.get("role_name")) or existing.role_group,
            )
    return name_map


def _extract_users(item: dict[str, Any], name_map: dict[int, UserOption]) -> tuple[list[UserOption], list[UserOption]]:
    assignee_ids = item.get("assigned_users") or []
    if not assignee_ids and item.get("assigned_to"):
        assignee_ids = [item["assigned_to"]]
    watcher_ids = item.get("watchers") or []
    assignees = [name_map[int(user_id)] for user_id in assignee_ids if int(user_id) in name_map]
    watchers = [name_map[int(user_id)] for user_id in watcher_ids if int(user_id) in name_map]
    return assignees, watchers


def _sprint_for_item(item: dict[str, Any]) -> tuple[int | None, str | None]:
    milestone_id = item.get("milestone")
    milestone_name = None
    extra_info = item.get("milestone_extra_info") or {}
    if extra_info:
        milestone_name = extra_info.get("name")
    if not milestone_id:
        user_story_extra = item.get("user_story_extra_info") or {}
        milestone_id = user_story_extra.get("milestone")
        milestone_name = milestone_name or user_story_extra.get("milestone_name")
    return int(milestone_id) if milestone_id else None, milestone_name


def _status_name(item: dict[str, Any], status_map: dict[int, StatusOption]) -> tuple[int | None, str, str | None]:
    status_id = item.get("status")
    if status_id is None:
        return None, "", None
    option = status_map.get(int(status_id))
    if option:
        return option.id, option.name, option.color
    return int(status_id), "", None


def _normalize_tags(value: Any) -> list[str]:
    tags: list[str] = []
    for tag in value or []:
        if isinstance(tag, str):
            cleaned = tag.strip()
        elif isinstance(tag, (list, tuple)) and tag:
            cleaned = str(tag[0] or "").strip()
        else:
            cleaned = str(tag or "").strip()
        if cleaned:
            tags.append(cleaned)
    return tags


def _item_url(base_url: str, project_slug: str, kind: str, ref: int | None, item_id: int) -> str:
    fragment = {"userstory": "us", "task": "task", "issue": "issue"}[kind]
    value = ref if ref is not None else item_id
    return f"{base_url}/project/{project_slug}/{fragment}/{value}"


def _to_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_warning_summary(
    items: list[TrackerItem],
    sprints: list[SprintOption],
    qc_names: list[str],
    days_before_sprint_end: int,
    days_without_update: int,
) -> WarningSummary:
    sprint_map = {s.id: s for s in sprints}
    qc_set = {_normalize_name(name) for name in qc_names}
    now = datetime.now(UTC)
    near_sprint_end: list[TrackerItem] = []
    stale_items: list[TrackerItem] = []
    missing_qc: list[TrackerItem] = []

    for item in items:
        has_qc = any(_normalize_name(person.full_name) in qc_set for person in (*item.assignees, *item.watchers))
        if not has_qc:
            missing_qc.append(item)

        updated_at = _to_iso_date(item.updated_at)
        if updated_at and (now - updated_at).days >= days_without_update:
            stale_items.append(item)

        if item.sprint_id and item.status_name:
            sprint = sprint_map.get(item.sprint_id)
            if sprint and sprint.estimated_finish:
                finish = _to_iso_date(f"{sprint.estimated_finish}T23:59:59+07:00")
                if finish is not None:
                    remaining_days = (finish - now).days
                    status_text = _normalize_name(item.status_name)
                    is_done = any(word in status_text for word in ("done", "closed", "resolved", "passed", "live"))
                    if remaining_days <= days_before_sprint_end and not is_done:
                        near_sprint_end.append(item)

    return WarningSummary(
        near_sprint_end=near_sprint_end,
        stale_items=stale_items,
        missing_qc=missing_qc,
    )


async def _load_reference_data(
    client: TaigaClient,
    project_id: int,
) -> tuple[list[UserOption], dict[int, UserOption], list[SprintOption], dict[int, str], dict[str, list[StatusOption]], dict[str, dict[int, StatusOption]]]:
    users_raw, memberships_raw, sprint_raw, userstory_statuses, task_statuses, issue_statuses = await asyncio.gather(
        client.get_users(project_id),
        client.get_memberships(project_id),
        client.get_milestones(project_id),
        client.get_statuses(project_id, "userstory"),
        client.get_statuses(project_id, "task"),
        client.get_statuses(project_id, "issue"),
    )

    user_map = _merge_membership_users(_get_name_map(users_raw), memberships_raw)
    user_options = sorted(user_map.values(), key=lambda user: user.full_name.casefold())
    sprints = [
        SprintOption(
            id=int(s["id"]),
            name=s["name"],
            estimated_start=s.get("estimated_start"),
            estimated_finish=s.get("estimated_finish"),
            closed=bool(s.get("closed")),
        )
        for s in sprint_raw
    ]
    sprint_name_map = {s.id: s.name for s in sprints}

    statuses: dict[str, list[StatusOption]] = {}
    status_maps: dict[str, dict[int, StatusOption]] = {}
    for kind, rows in (
        ("userstory", userstory_statuses),
        ("task", task_statuses),
        ("issue", issue_statuses),
    ):
        options = [StatusOption(id=int(row["id"]), name=row["name"], color=row.get("color")) for row in rows]
        statuses[kind] = options
        status_maps[kind] = {option.id: option for option in options}

    return user_options, user_map, sprints, sprint_name_map, statuses, status_maps


async def _build_snapshot_bundle(client: TaigaClient, config: AppConfig) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    project = await client.get_project()
    project_id = int(project["id"])
    user_options, user_map, sprints, sprint_name_map, statuses, status_maps = await _load_reference_data(client, project_id)
    qc_users = _filter_qc_users(user_options, config.qc_names)

    metadata_payload = {
        "project_name": project["name"],
        "auto_refresh_minutes": config.auto_refresh_minutes,
        "qc_names": config.qc_names,
        "sprints": [s.model_dump(mode="json") for s in sorted(sprints, key=lambda sprint: (sprint.closed, sprint.name.casefold()))],
        "statuses": {
            kind: [status.model_dump(mode="json") for status in values]
            for kind, values in statuses.items()
        },
        "users": [user.model_dump(mode="json") for user in qc_users],
    }

    rows_by_kind = await asyncio.gather(
        client.get_items(project_id, "userstory"),
        client.get_items(project_id, "task"),
        client.get_items(project_id, "issue"),
    )
    kind_rows = {
        "userstory": rows_by_kind[0],
        "task": rows_by_kind[1],
        "issue": rows_by_kind[2],
    }

    items_by_kind: dict[str, list[TrackerItem]] = {
        current_kind: _build_tracker_items(
            rows,
            kind=current_kind,
            user_map=user_map,
            sprint_name_map=sprint_name_map,
            status_map=status_maps[current_kind],
        )
        for current_kind, rows in kind_rows.items()
    }

    explicit_userstory_sprints: set[tuple[int, int | None]] = set()
    for item in items_by_kind["userstory"]:
        if item.ref is not None:
            explicit_userstory_sprints.add((int(item.ref), item.sprint_id))

    inferred_seen: set[tuple[int, int | None]] = set()
    for task in kind_rows["task"]:
        info = task.get("user_story_extra_info") or {}
        us_id = info.get("id")
        us_ref = info.get("ref")
        if not us_id or not us_ref:
            continue
        sprint_id, sprint_name = _sprint_for_item(task)
        if sprint_id is None:
            continue
        key = (int(us_ref), sprint_id)
        if key in explicit_userstory_sprints or key in inferred_seen:
            continue
        inferred_seen.add(key)
        assignees, watchers = _extract_users(task, user_map)
        status_id, status_name, status_color = _status_name(task, status_maps["task"])
        items_by_kind["userstory"].append(
            TrackerItem(
                kind="userstory",
                id=int(us_id),
                ref=int(us_ref),
                subject=info.get("subject") or task.get("subject") or "",
                status_id=status_id,
                status_name=f"{status_name} (Inferred)" if status_name else "Inferred from task",
                status_color=status_color,
                assignees=assignees,
                watchers=watchers,
                sprint_id=sprint_id,
                sprint_name=sprint_name or sprint_name_map.get(sprint_id),
                is_no_sprint=False,
                updated_at=task.get("modified_date"),
                created_at=task.get("created_date"),
                due_date=task.get("due_date"),
                tags=_normalize_tags(task.get("tags")),
                severity=None,
                priority=None,
                url=_item_url(config.taiga_base_url, config.project_slug, "userstory", int(us_ref), int(us_id)),
            )
        )

    serialized_items = {
        current_kind: [item.model_dump(mode="json") for item in _finalize_item_urls(current_items, config)]
        for current_kind, current_items in items_by_kind.items()
    }
    return metadata_payload, serialized_items


async def refresh_snapshots(client: TaigaClient, config: AppConfig) -> None:
    metadata_payload, serialized_items = await _build_snapshot_bundle(client, config)
    _write_snapshot(config, "metadata", metadata_payload)
    for kind, payload in serialized_items.items():
        _write_snapshot(config, f"items-{kind}", payload)


async def build_metadata(client: TaigaClient, config: AppConfig, me: SessionUser) -> MetadataResponse:
    snapshot = _read_snapshot(config, "metadata")
    if snapshot is None or _metadata_snapshot_missing_roles(snapshot):
        await refresh_snapshots(client, config)
        snapshot = _read_snapshot(config, "metadata") or {}
    snapshot["me"] = me.model_dump(mode="json")
    return MetadataResponse.model_validate(snapshot)


def _build_tracker_items(
    raw_rows: list[dict[str, Any]],
    *,
    kind: str,
    user_map: dict[int, UserOption],
    sprint_name_map: dict[int, str],
    status_map: dict[int, StatusOption],
) -> list[TrackerItem]:
    items: list[TrackerItem] = []
    for raw in raw_rows:
        assignees, watchers = _extract_users(raw, user_map)
        sprint_id, sprint_name = _sprint_for_item(raw)
        status_id, status_name, status_color = _status_name(raw, status_map)
        items.append(
            TrackerItem(
                kind=kind,  # type: ignore[arg-type]
                id=int(raw["id"]),
                ref=raw.get("ref"),
                subject=raw.get("subject") or "",
                status_id=status_id,
                status_name=status_name,
                status_color=status_color,
                assignees=assignees,
                watchers=watchers,
                sprint_id=sprint_id,
                sprint_name=sprint_name or sprint_name_map.get(sprint_id),
                is_no_sprint=sprint_id is None,
                updated_at=raw.get("modified_date"),
                created_at=raw.get("created_date"),
                due_date=raw.get("due_date"),
                tags=_normalize_tags(raw.get("tags")),
                severity=(raw.get("severity_extra_info") or {}).get("name"),
                priority=(raw.get("priority_extra_info") or {}).get("name"),
                url=None,
            )
        )
    return items


def _finalize_item_urls(items: list[TrackerItem], config: AppConfig) -> list[TrackerItem]:
    for item in items:
        item.url = _item_url(config.taiga_base_url, config.project_slug, item.kind, item.ref, item.id)
    return items


async def build_tracker_item_from_detail(
    client: TaigaClient,
    config: AppConfig,
    *,
    kind: str,
    detail: dict[str, Any],
) -> TrackerItem:
    project = await client.get_project()
    project_id = int(project["id"])
    _, user_map, _, sprint_name_map, _, status_maps = await _load_reference_data(client, project_id)
    item = _build_tracker_items(
        [detail],
        kind=kind,
        user_map=user_map,
        sprint_name_map=sprint_name_map,
        status_map=status_maps[kind],
    )[0]
    return _finalize_item_urls([item], config)[0]


def update_snapshot_item(config: AppConfig, item: TrackerItem) -> None:
    snapshot_name = f"items-{item.kind}"
    rows = _read_snapshot(config, snapshot_name) or []
    updated = False
    normalized_item = item.model_dump(mode="json")
    for index, row in enumerate(rows):
        if int(row.get("id", -1)) == item.id:
            rows[index] = normalized_item
            updated = True
            break
    if not updated:
        rows.append(normalized_item)
    _write_snapshot(config, snapshot_name, rows)


async def build_items(
    client: TaigaClient,
    config: AppConfig,
    *,
    me_user_id: int | None = None,
    kind: str | None = None,
    sprint_ids: set[int] | None = None,
    statuses: set[str] | None = None,
    assignee_ids: set[int] | None = None,
    search: str = "",
    no_sprint_only: bool = False,
    not_assigned_qc_only: bool = False,
    assigned_to_me_only: bool = False,
) -> ItemsResponse:
    kinds = ("userstory", "task", "issue") if not kind or kind == "all" else (kind,)
    serialized_items: list[dict[str, Any]] = []
    for current_kind in kinds:
        snapshot = _read_snapshot(config, f"items-{current_kind}")
        if snapshot is None or _items_snapshot_missing_roles(snapshot):
            await refresh_snapshots(client, config)
            snapshot = _read_snapshot(config, f"items-{current_kind}") or []
        serialized_items.extend(snapshot)
    items = [TrackerItem.model_validate(row) for row in serialized_items]
    normalized_statuses = {_normalize_name(value) for value in (statuses or set())}
    normalized_search = _normalize_name(search)
    qc_set = {_normalize_name(name) for name in config.qc_names}

    filtered: list[TrackerItem] = []
    for item in items:
        if kind and kind != "all" and item.kind != kind:
            continue
        if _is_cancel_status(item.status_name):
            continue
        if no_sprint_only and not item.is_no_sprint:
            continue
        has_qc = any(_normalize_name(user.full_name) in qc_set for user in (*item.assignees, *item.watchers))
        if not_assigned_qc_only and has_qc:
            continue
        if assigned_to_me_only and (me_user_id is None or not any(user.id == me_user_id for user in item.assignees)):
            continue
        if sprint_ids and (item.sprint_id is None or item.sprint_id not in sprint_ids):
            continue
        if normalized_statuses and _normalize_name(item.status_name) not in normalized_statuses:
            continue
        if assignee_ids and not any(user.id in assignee_ids for user in item.assignees):
            continue
        if normalized_search:
            haystack = " ".join(
                [
                    item.subject,
                    item.kind,
                    str(item.ref or ""),
                    item.status_name,
                    item.sprint_name or "",
                    *[user.full_name for user in item.assignees],
                    *[user.full_name for user in item.watchers],
                    *item.tags,
                ]
            )
            if normalized_search not in _normalize_name(haystack):
                continue
        filtered.append(item)

    return ItemsResponse(items=filtered)


async def _dashboard_summary_from_items(
    client: TaigaClient,
    config: AppConfig,
    items: list[TrackerItem],
) -> WarningSummary:
    project = await client.get_project()
    project_id = int(project["id"])
    _, _, sprints, _, _, _ = await _load_reference_data(client, project_id)
    return _build_warning_summary(
        items,
        sprints,
        config.qc_names,
        config.warning_days_before_sprint_end,
        config.warning_days_without_update,
    )


async def build_dashboard_counts(
    client: TaigaClient,
    config: AppConfig,
    *,
    sprint_ids: set[int] | None = None,
    statuses: set[str] | None = None,
    assignee_ids: set[int] | None = None,
    search: str = "",
) -> DashboardCounts:
    items_response = await build_items(
        client,
        config,
        kind="all",
        sprint_ids=sprint_ids,
        statuses=statuses,
        assignee_ids=assignee_ids,
        search=search,
        no_sprint_only=False,
    )
    summary = await _dashboard_summary_from_items(client, config, items_response.items)
    return DashboardCounts(
        near_sprint_end=len(summary.near_sprint_end),
        stale_items=len(summary.stale_items),
        missing_qc=len(summary.missing_qc),
    )


async def build_dashboard_items(
    client: TaigaClient,
    config: AppConfig,
    *,
    warning_type: str,
    sprint_ids: set[int] | None = None,
    statuses: set[str] | None = None,
    assignee_ids: set[int] | None = None,
    search: str = "",
) -> ItemsResponse:
    items_response = await build_items(
        client,
        config,
        kind="all",
        sprint_ids=sprint_ids,
        statuses=statuses,
        assignee_ids=assignee_ids,
        search=search,
        no_sprint_only=False,
    )
    summary = await _dashboard_summary_from_items(client, config, items_response.items)
    mapping = {
        "near_sprint_end": summary.near_sprint_end,
        "stale_items": summary.stale_items,
        "missing_qc": summary.missing_qc,
    }
    return ItemsResponse(items=mapping.get(warning_type, []))
