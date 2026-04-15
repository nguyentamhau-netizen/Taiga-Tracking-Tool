from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import app_root, load_config
from .schemas import DashboardCounts, ItemUpdateRequest, ItemUpdateResponse, ItemsResponse, LoginRequest, MetadataResponse, SessionUser
from .taiga import TaigaClient, build_dashboard_counts, build_dashboard_items, build_items, build_metadata, build_tracker_item_from_detail, refresh_snapshots, update_snapshot_item


config = load_config()
app = FastAPI(title="Taiga QC Tracker API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=config.session_secret)
FRONTEND_DIST = app_root() / "frontend" / "dist"


def _session_client(request: Request) -> tuple[TaigaClient, SessionUser]:
    token = request.session.get("token")
    user = request.session.get("user")
    if not token or not user:
        raise HTTPException(status_code=401, detail="Please log in first.")
    return TaigaClient(config, token=token), SessionUser.model_validate(user)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/login")
async def login(payload: LoginRequest, request: Request) -> dict[str, object]:
    client = TaigaClient(config)
    try:
        token, user = await client.login(payload.username, payload.password)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Taiga login failed: {exc}") from exc
    request.session["token"] = token
    request.session["user"] = user.model_dump()
    return {"ok": True, "user": user.model_dump()}


@app.post("/api/auth/logout")
async def logout(request: Request) -> dict[str, bool]:
    request.session.clear()
    return {"ok": True}


@app.get("/api/auth/me")
async def me(request: Request) -> dict[str, object]:
    _, user = _session_client(request)
    return {"ok": True, "user": user.model_dump()}


@app.get("/api/metadata", response_model=MetadataResponse)
async def metadata(request: Request) -> MetadataResponse:
    client, user = _session_client(request)
    return await build_metadata(client, config, user)


@app.post("/api/sync")
async def sync_from_taiga(request: Request) -> dict[str, bool]:
    client, _ = _session_client(request)
    await refresh_snapshots(client, config)
    return {"ok": True}


@app.get("/api/dashboard", response_model=DashboardCounts)
async def dashboard(
    request: Request,
    sprint_ids: str = "",
    statuses: str = "",
    assignee_ids: str = "",
    search: str = "",
) -> DashboardCounts:
    client, _ = _session_client(request)
    sprint_id_set = {int(value) for value in sprint_ids.split(",") if value.strip()}
    status_set = {value.strip() for value in statuses.split(",") if value.strip()}
    assignee_id_set = {int(value) for value in assignee_ids.split(",") if value.strip()}
    return await build_dashboard_counts(
        client,
        config,
        sprint_ids=sprint_id_set,
        statuses=status_set,
        assignee_ids=assignee_id_set,
        search=search,
    )


@app.get("/api/dashboard/items", response_model=ItemsResponse)
async def dashboard_items(
    request: Request,
    warning_type: str,
    sprint_ids: str = "",
    statuses: str = "",
    assignee_ids: str = "",
    search: str = "",
) -> ItemsResponse:
    client, _ = _session_client(request)
    sprint_id_set = {int(value) for value in sprint_ids.split(",") if value.strip()}
    status_set = {value.strip() for value in statuses.split(",") if value.strip()}
    assignee_id_set = {int(value) for value in assignee_ids.split(",") if value.strip()}
    return await build_dashboard_items(
        client,
        config,
        warning_type=warning_type,
        sprint_ids=sprint_id_set,
        statuses=status_set,
        assignee_ids=assignee_id_set,
        search=search,
    )


@app.get("/api/items", response_model=ItemsResponse)
async def items(
    request: Request,
    kind: str | None = None,
    sprint_ids: str = "",
    statuses: str = "",
    assignee_ids: str = "",
    search: str = "",
    no_sprint_only: bool = False,
    not_assigned_qc_only: bool = False,
    assigned_to_me_only: bool = False,
) -> ItemsResponse:
    client, user = _session_client(request)
    sprint_id_set = {int(value) for value in sprint_ids.split(",") if value.strip()}
    status_set = {value.strip() for value in statuses.split(",") if value.strip()}
    assignee_id_set = {int(value) for value in assignee_ids.split(",") if value.strip()}
    return await build_items(
        client,
        config,
        me_user_id=user.id,
        kind=kind,
        sprint_ids=sprint_id_set,
        statuses=status_set,
        assignee_ids=assignee_id_set,
        search=search,
        no_sprint_only=no_sprint_only,
        not_assigned_qc_only=not_assigned_qc_only,
        assigned_to_me_only=assigned_to_me_only,
    )


@app.patch("/api/items/{kind}/{item_id}", response_model=ItemUpdateResponse)
async def update_item(kind: str, item_id: int, payload: ItemUpdateRequest, request: Request) -> ItemUpdateResponse:
    if kind not in {"userstory", "task", "issue"}:
        raise HTTPException(status_code=400, detail="Unsupported item type.")
    client, _ = _session_client(request)
    current = await client.get_item_detail(kind, item_id)

    patch_payload: dict[str, object] = {"version": current.get("version")}
    if payload.status_id is not None:
        patch_payload["status"] = payload.status_id
    if payload.sprint_id is not None:
        patch_payload["milestone"] = payload.sprint_id
    if payload.assignee_ids is not None:
        patch_payload["assigned_users"] = payload.assignee_ids
        patch_payload["assigned_to"] = payload.assignee_ids[0] if payload.assignee_ids else None
    if payload.watcher_ids is not None:
        patch_payload["watchers"] = payload.watcher_ids
    if payload.comment:
        patch_payload["comment"] = payload.comment

    await client.update_item(kind, item_id, patch_payload)
    updated_detail = await client.get_item_detail(kind, item_id)
    updated_item = await build_tracker_item_from_detail(client, config, kind=kind, detail=updated_detail)
    update_snapshot_item(config, updated_item)
    return ItemUpdateResponse(ok=True, item=updated_item)


if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    async def frontend_index() -> FileResponse:
        return FileResponse(FRONTEND_DIST / "index.html")


    @app.get("/{full_path:path}", include_in_schema=False)
    async def frontend_spa(full_path: str) -> FileResponse:
        requested_path = FRONTEND_DIST / full_path
        if requested_path.is_file():
            return FileResponse(requested_path)
        return FileResponse(FRONTEND_DIST / "index.html")
