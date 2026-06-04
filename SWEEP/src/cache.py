"""项目 Watch Dir 缓存和运行摘要持久化。

缓存只保存项目根和 Watch Dir，不保存最终 Cleanup Candidate。候选资格依赖
mtime、symlink 状态和所有权，必须在每次运行时重新读取实时文件系统。
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import SweepConfig
from .models import CacheStats, ProjectEntry, WatchDir

CACHE_VERSION = 1


def load_project_entries(config: SweepConfig) -> tuple[list[ProjectEntry], CacheStats]:
    """在缓存匹配当前配置时读取可复用的项目描述。"""
    stats = CacheStats(enabled=config.cache.enabled)
    if not config.cache.enabled:
        stats.reason = "disabled"
        return [], stats

    cache_file = config.cache.project_watch_dirs_file
    if not cache_file.is_file():
        stats.reason = "missing"
        return [], stats

    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        stats.reason = f"unreadable: {exc}"
        stats.full_refresh = True
        return [], stats

    if payload.get("version") != CACHE_VERSION:
        stats.reason = "version_mismatch"
        stats.full_refresh = True
        return [], stats
    if payload.get("config_hash") != config.config_hash:
        stats.reason = "config_hash_mismatch"
        stats.full_refresh = True
        return [], stats
    if _is_expired(payload.get("generated_at"), config.cache.ttl_hours):
        stats.reason = "ttl_expired"
        stats.full_refresh = True
        return [], stats

    entries: list[ProjectEntry] = []
    for raw_entry in payload.get("projects", []):
        entry = _parse_project_entry(raw_entry)
        if entry is None:
            stats.full_refresh = True
            continue
        if not _validate_project_entry(entry, config):
            stats.full_refresh = True
            continue
        entries.append(entry)

    stats.loaded = True
    stats.cache_hits = len(entries)
    if not entries:
        stats.reason = stats.reason or "empty"
    return entries, stats


def save_project_entries(
    config: SweepConfig,
    entries: list[ProjectEntry],
    stats: CacheStats,
) -> None:
    """原子写入项目根和 Watch Dir，用于后续加速扫描。"""
    if not config.cache.enabled:
        return

    config.cache.dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "config_hash": config.config_hash,
        "generated_at": _now_iso(),
        "projects": [entry.to_json() for entry in entries],
    }
    _atomic_write_json(config.cache.project_watch_dirs_file, payload)
    stats.saved = True


def append_run_summary(config: SweepConfig, summary: dict[str, Any]) -> None:
    """追加一条运行摘要；无候选运行也写入，便于审计。"""
    config.cache.dir.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp": _now_iso(), **summary}
    with config.cache.summary_file.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        file.write("\n")


def _parse_project_entry(raw_entry: Any) -> ProjectEntry | None:
    """防御式解析单个缓存项目；格式异常时忽略整项。"""
    if not isinstance(raw_entry, dict):
        return None
    root = raw_entry.get("root")
    markers = raw_entry.get("markers")
    watch_dirs = raw_entry.get("watch_dirs")
    if (
        not isinstance(root, str)
        or not isinstance(markers, list)
        or not isinstance(watch_dirs, list)
    ):
        return None

    parsed_watch_dirs: list[WatchDir] = []
    for item in watch_dirs:
        if not isinstance(item, dict):
            return None
        path = item.get("path")
        kind = item.get("kind")
        if not isinstance(path, str) or not isinstance(kind, str):
            return None
        if kind not in {"temp", "managed"}:
            return None
        parsed_watch_dirs.append(WatchDir(path=Path(path), kind=kind))

    return ProjectEntry(
        root=Path(root),
        markers=tuple(str(marker) for marker in markers),
        watch_dirs=tuple(parsed_watch_dirs),
    )


def _validate_project_entry(entry: ProjectEntry, config: SweepConfig) -> bool:
    """在缓存项授权扫描前拒绝过期、污染或越界的项目描述。"""
    if not entry.root.exists() or not entry.root.is_dir() or entry.root.is_symlink():
        return False
    if not _is_under_any(
        entry.root,
        (*config.projects.roots, *config.projects.extra_dirs),
    ):
        return False
    if config.cache.validate_project_markers and not any(
        (entry.root / marker).exists() for marker in config.projects.root_markers
    ):
        return False
    return all(_validate_watch_dir(entry, watch_dir, config) for watch_dir in entry.watch_dirs)


def _validate_watch_dir(
    entry: ProjectEntry,
    watch_dir: WatchDir,
    config: SweepConfig,
) -> bool:
    """确认缓存中的 Watch Dir 仍是当前配置允许的项目直属目录。"""
    if watch_dir.path.is_symlink():
        return False
    if watch_dir.path.exists() and not watch_dir.path.is_dir():
        return False
    if config.cache.validate_watch_dirs_exist and not watch_dir.path.exists():
        return False

    root = entry.root.resolve(strict=False)
    path = watch_dir.path.resolve(strict=False)
    if path == root or not _is_under(path, root):
        return False
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return False
    if len(parts) != 1:
        return False
    if watch_dir.kind == "temp":
        return parts[0] in config.projects.temp_dirs
    if watch_dir.kind == "managed":
        return parts[0] in config.projects.managed_dirs
    return False


def _is_expired(raw_timestamp: Any, ttl_hours: int) -> bool:
    """判断缓存时间戳是否超过 TTL。"""
    if ttl_hours <= 0:
        return True
    if not isinstance(raw_timestamp, str):
        return True
    try:
        generated_at = datetime.fromisoformat(raw_timestamp)
    except ValueError:
        return True
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    age_seconds = (datetime.now(UTC) - generated_at).total_seconds()
    return age_seconds > ttl_hours * 3600


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """通过同目录临时文件写入 JSON，再原子替换目标文件。"""
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def _now_iso() -> str:
    """返回带时区的缓存和摘要时间戳。"""
    return datetime.now(UTC).isoformat()


def _is_under_any(path: Path, roots: tuple[Path, ...]) -> bool:
    """判断路径是否等于或位于任一配置根目录下。"""
    return any(_is_under(path, root) for root in roots)


def _is_under(path: Path, root: Path) -> bool:
    """判断路径是否等于或位于指定根目录下。"""
    resolved_path = path.expanduser().resolve(strict=False)
    resolved_root = root.expanduser().resolve(strict=False)
    return resolved_path == resolved_root or resolved_root in resolved_path.parents
