from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    taiga_base_url: str
    project_slug: str
    qc_names: list[str]
    warning_days_before_sprint_end: int
    warning_days_without_update: int
    auto_refresh_minutes: int
    session_secret: str
    cache_ttl_seconds: int
    cache_dir: Path
    snapshot_dir: Path


def load_config() -> AppConfig:
    root = Path(__file__).resolve().parents[2]
    local_path = root / "config.local.json"
    example_path = root / "config.example.json"
    config_path = local_path if local_path.exists() else example_path
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    return AppConfig(
        taiga_base_url=str(raw["taigaBaseUrl"]).rstrip("/"),
        project_slug=str(raw["projectSlug"]).strip(),
        qc_names=[str(name).strip() for name in raw.get("qcNames", []) if str(name).strip()],
        warning_days_before_sprint_end=int(raw.get("warningDaysBeforeSprintEnd", 3)),
        warning_days_without_update=int(raw.get("warningDaysWithoutUpdate", 5)),
        auto_refresh_minutes=int(raw.get("autoRefreshMinutes", 10)),
        session_secret=str(raw.get("sessionSecret") or secrets.token_hex(32)),
        cache_ttl_seconds=int(raw.get("cacheTtlSeconds", 300)),
        cache_dir=root / ".cache" / "taiga",
        snapshot_dir=root / ".cache" / "snapshots",
    )
