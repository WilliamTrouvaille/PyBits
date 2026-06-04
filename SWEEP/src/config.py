"""加载并校验 SWEEP 配置。

本模块负责把 YAML 转换为类型化 dataclass，并校验路径边界。它不包含清理
行为；扫描和执行模块只消费这里产出的已校验配置。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class SweepConfigError(ValueError):
    """SWEEP 配置无效时抛出的异常。"""


DEFAULT_CONFIG: dict[str, Any] = {
    "system_temp": {
        "dirs": ["~/TEMP"],
        "keep_days": 15,
        "allow_dir_candidates": False,
    },
    "downloads": {
        "dirs": ["~/Downloads"],
        "keep_days": 30,
        "allow_dir_candidates": False,
    },
    "projects": {
        "roots": ["~/CODE"],
        "extra_dirs": [],
        "root_markers": [".git", "pyproject.toml", "Makefile", "main.tex"],
        "managed_dirs": [".codex", ".claude"],
        "temp_dirs": [".temp", ".tmp", "tmp", "temp"],
        "keep_days": 7,
        "allow_dir_candidates": True,
        "trash_bin_names": ["_trash_bin_"],
        "temp_file_name_contains": [".tmp.", ".temp."],
    },
    "cache": {
        "enabled": True,
        "dir": "_cache",
        "project_watch_dirs_file": "project_watch_dirs.json",
        "summary_file": "run_summaries.jsonl",
        "ttl_hours": 168,
        "validate_project_markers": True,
        "validate_watch_dirs_exist": True,
        "refresh_missing_projects": True,
    },
    "trash": {
        "command": ["/usr/bin/trash"],
        "batch_size": 100,
        "workers": 4,
        "retries": 2,
        "retry_backoff_seconds": 0.5,
        "fallback_to_soft_delete": True,
    },
    "failure_policy": {
        "project_trash_dir_name": ".codex/_trash_bin_",
        "external_trash_dir": "../.codex/_trash_bin_/SWEEP-external",
        "unresolved_manifest": "_cache/unresolved_failures.jsonl",
        "repair_owned_paths": True,
        "clear_macos_user_immutable_flag": True,
        "exit_nonzero_on_unresolved": True,
    },
    "scan": {
        "max_depth": 4,
        "workers": 8,
        "skip_symlinks": True,
        "skip_dirs": [".git", ".hg", ".svn"],
        "reject_paths_containing_newline": True,
    },
}


@dataclass(frozen=True)
class AgeScopeConfig:
    """按年龄判断的扁平 Cleanup Scope 保留策略。"""

    dirs: tuple[Path, ...]
    keep_days: int
    allow_dir_candidates: bool


@dataclass(frozen=True)
class ProjectsConfig:
    """从 YAML `projects` 段解析出的项目清理配置。"""

    roots: tuple[Path, ...]
    extra_dirs: tuple[Path, ...]
    root_markers: tuple[str, ...]
    managed_dirs: tuple[str, ...]
    temp_dirs: tuple[str, ...]
    keep_days: int
    allow_dir_candidates: bool
    trash_bin_names: tuple[str, ...]
    temp_file_name_contains: tuple[str, ...]


@dataclass(frozen=True)
class CacheConfig:
    """运行时缓存路径和缓存校验策略。"""

    enabled: bool
    dir: Path
    project_watch_dirs_file: Path
    summary_file: Path
    ttl_hours: int
    validate_project_markers: bool
    validate_watch_dirs_exist: bool
    refresh_missing_projects: bool


@dataclass(frozen=True)
class TrashConfig:
    """已配置的 trash 命令和重试策略。"""

    command: tuple[str, ...]
    batch_size: int
    workers: int
    retries: int
    retry_backoff_seconds: float
    fallback_to_soft_delete: bool


@dataclass(frozen=True)
class FailurePolicyConfig:
    """soft-delete fallback、权限修复和 unresolved manifest 策略。"""

    project_trash_dir_name: Path
    external_trash_dir: Path
    unresolved_manifest: Path
    repair_owned_paths: bool
    clear_macos_user_immutable_flag: bool
    exit_nonzero_on_unresolved: bool


@dataclass(frozen=True)
class ScanConfig:
    """遍历限制和路径拒绝策略。"""

    max_depth: int
    workers: int
    skip_symlinks: bool
    skip_dirs: tuple[str, ...]
    reject_paths_containing_newline: bool


@dataclass(frozen=True)
class SweepConfig:
    """运行时模块使用的完整已校验 SWEEP 配置。"""

    config_path: Path
    data_dir: Path
    system_temp: AgeScopeConfig
    downloads: AgeScopeConfig
    projects: ProjectsConfig
    cache: CacheConfig
    trash: TrashConfig
    failure_policy: FailurePolicyConfig
    scan: ScanConfig
    config_hash: str

    def cleanup_scope_roots(self) -> tuple[Path, ...]:
        """
        返回 YAML 授权且可能包含候选路径的所有根目录。

        Returns:
            去重后的 Cleanup Scope 根目录元组。
        """
        roots = [
            *self.system_temp.dirs,
            *self.downloads.dirs,
            *self.projects.roots,
            *self.projects.extra_dirs,
        ]
        return tuple(_dedupe_paths(roots))


def load_config(config_path: Path, data_dir: Path) -> SweepConfig:
    """
    加载 YAML、合并默认值并校验所有运行时配置段。

    Args:
        config_path: YAML 配置文件路径。
        data_dir: SWEEP 数据目录，用于解析缓存和审计文件位置。

    Returns:
        已完成语义校验的 SWEEP 配置。

    Raises:
        SweepConfigError: 配置文件缺失、解析失败或字段不满足安全边界。
    """
    raw_config = _read_yaml(config_path)
    merged = _merge_dicts(DEFAULT_CONFIG, raw_config)

    system_temp = _load_age_scope(merged["system_temp"])
    downloads = _load_age_scope(merged["downloads"])
    projects = _load_projects(merged["projects"])
    cache = _load_cache(merged["cache"], data_dir)
    trash = _load_trash(merged["trash"])
    failure_policy = _load_failure_policy(merged["failure_policy"], data_dir)
    scan = _load_scan(merged["scan"])
    config_hash = _hash_config(merged)

    return SweepConfig(
        config_path=config_path,
        data_dir=data_dir,
        system_temp=system_temp,
        downloads=downloads,
        projects=projects,
        cache=cache,
        trash=trash,
        failure_policy=failure_policy,
        scan=scan,
        config_hash=config_hash,
    )


def resolve_trash_command(command: tuple[str, ...]) -> tuple[str, ...] | None:
    """
    为当前进程解析一次配置中的 trash 命令。

    Args:
        command: YAML 中的 trash.command 参数列表。

    Returns:
        可执行文件已解析后的命令元组；不可用时返回 None。
    """
    if not command:
        return None

    executable = command[0]
    if Path(executable).is_absolute():
        path = Path(executable).expanduser()
        if path.is_file() and path.stat().st_mode & 0o111:
            return (str(path), *command[1:])
        return None

    resolved = shutil.which(executable)
    if resolved is None:
        return None
    return (resolved, *command[1:])


def _read_yaml(config_path: Path) -> dict[str, Any]:
    """读取 YAML 映射，语义校验由调用方继续完成。"""
    if not config_path.is_file():
        raise SweepConfigError(f"找不到配置文件: {config_path}")
    try:
        content = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SweepConfigError(f"无法解析 YAML 配置 {config_path}: {exc}") from exc
    if not isinstance(content, dict):
        raise SweepConfigError(f"配置根节点必须是映射: {config_path}")
    return content


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """把用户 YAML 合并到默认配置，同时拒绝未知键。"""
    merged: dict[str, Any] = {}
    for key, value in base.items():
        if isinstance(value, dict):
            override_value = override.get(key, {})
            if override_value is not None and not isinstance(override_value, dict):
                raise SweepConfigError(f"配置段必须是映射: {key}")
            merged[key] = _merge_dicts(value, override_value or {})
        else:
            merged[key] = override.get(key, value)
    for key in override:
        if key not in merged:
            raise SweepConfigError(f"未知配置段或配置键: {key}")
    return merged


def _load_age_scope(raw: dict[str, Any]) -> AgeScopeConfig:
    """规范化按年龄判断的清理范围配置段。"""
    dirs = tuple(_resolve_user_path(item) for item in _require_str_list(raw, "dirs"))
    keep_days = _require_int(raw, "keep_days", minimum=0)
    return AgeScopeConfig(
        dirs=tuple(_dedupe_paths(dirs)),
        keep_days=keep_days,
        allow_dir_candidates=bool(raw["allow_dir_candidates"]),
    )


def _load_projects(raw: dict[str, Any]) -> ProjectsConfig:
    """规范化项目发现和项目临时文件清理配置。"""
    root_markers = tuple(_require_str_list(raw, "root_markers"))
    managed_dirs = tuple(_require_relative_names(raw, "managed_dirs"))
    temp_dirs = tuple(_require_relative_names(raw, "temp_dirs"))
    trash_bin_names = tuple(_require_relative_names(raw, "trash_bin_names"))
    skip_contains = tuple(_require_str_list(raw, "temp_file_name_contains"))

    return ProjectsConfig(
        roots=tuple(
            _dedupe_paths(_resolve_user_path(item) for item in _require_str_list(raw, "roots"))
        ),
        extra_dirs=tuple(
            _dedupe_paths(_resolve_user_path(item) for item in _require_str_list(raw, "extra_dirs"))
        ),
        root_markers=root_markers,
        managed_dirs=managed_dirs,
        temp_dirs=temp_dirs,
        keep_days=_require_int(raw, "keep_days", minimum=0),
        allow_dir_candidates=bool(raw["allow_dir_candidates"]),
        trash_bin_names=trash_bin_names,
        temp_file_name_contains=skip_contains,
    )


def _load_cache(raw: dict[str, Any], data_dir: Path) -> CacheConfig:
    """校验缓存路径，确保运行状态保留在 `SWEEP/_cache` 下。"""
    cache_dir = _resolve_data_child(data_dir, str(raw["dir"]), "cache.dir")
    if cache_dir.name != "_cache" or cache_dir.parent != data_dir.resolve():
        raise SweepConfigError("cache.dir 必须解析到 SWEEP/_cache")
    return CacheConfig(
        enabled=bool(raw["enabled"]),
        dir=cache_dir,
        project_watch_dirs_file=cache_dir / str(raw["project_watch_dirs_file"]),
        summary_file=cache_dir / str(raw["summary_file"]),
        ttl_hours=_require_int(raw, "ttl_hours", minimum=0),
        validate_project_markers=bool(raw["validate_project_markers"]),
        validate_watch_dirs_exist=bool(raw["validate_watch_dirs_exist"]),
        refresh_missing_projects=bool(raw["refresh_missing_projects"]),
    )


def _load_trash(raw: dict[str, Any]) -> TrashConfig:
    """校验 trash 命令形状和重试设置。"""
    command = tuple(_require_str_list(raw, "command"))
    if not command:
        raise SweepConfigError("trash.command 至少需要包含一个条目")
    return TrashConfig(
        command=command,
        batch_size=_require_int(raw, "batch_size", minimum=1),
        workers=_require_int(raw, "workers", minimum=1),
        retries=_require_int(raw, "retries", minimum=0),
        retry_backoff_seconds=float(raw["retry_backoff_seconds"]),
        fallback_to_soft_delete=bool(raw["fallback_to_soft_delete"]),
    )


def _load_failure_policy(raw: dict[str, Any], data_dir: Path) -> FailurePolicyConfig:
    """校验 fallback 路径和 unresolved manifest 位置。"""
    project_trash = Path(str(raw["project_trash_dir_name"]))
    if project_trash.is_absolute() or ".." in project_trash.parts:
        raise SweepConfigError("failure_policy.project_trash_dir_name 必须是项目相对路径")
    if project_trash.parts[:2] != (".codex", "_trash_bin_"):
        raise SweepConfigError("项目 trash 目录必须位于 .codex/_trash_bin_ 下")

    external_trash_dir = _resolve_data_child(
        data_dir,
        str(raw["external_trash_dir"]),
        "failure_policy.external_trash_dir",
        allow_parent=True,
    )
    if not _has_codex_trash_parent(external_trash_dir):
        raise SweepConfigError("外部 trash 目录必须位于某个 .codex/_trash_bin_ 路径下")

    unresolved_manifest = _resolve_data_child(
        data_dir, str(raw["unresolved_manifest"]), "failure_policy.unresolved_manifest"
    )
    if unresolved_manifest.parent != data_dir.resolve() / "_cache":
        raise SweepConfigError("unresolved manifest 必须位于 SWEEP/_cache 下")

    return FailurePolicyConfig(
        project_trash_dir_name=project_trash,
        external_trash_dir=external_trash_dir,
        unresolved_manifest=unresolved_manifest,
        repair_owned_paths=bool(raw["repair_owned_paths"]),
        clear_macos_user_immutable_flag=bool(raw["clear_macos_user_immutable_flag"]),
        exit_nonzero_on_unresolved=bool(raw["exit_nonzero_on_unresolved"]),
    )


def _load_scan(raw: dict[str, Any]) -> ScanConfig:
    """规范化所有范围扫描器共用的遍历设置。"""
    return ScanConfig(
        max_depth=_require_int(raw, "max_depth", minimum=0),
        workers=_require_int(raw, "workers", minimum=1),
        skip_symlinks=bool(raw["skip_symlinks"]),
        skip_dirs=tuple(_require_relative_names(raw, "skip_dirs")),
        reject_paths_containing_newline=bool(raw["reject_paths_containing_newline"]),
    )


def _require_str_list(raw: dict[str, Any], key: str) -> list[str]:
    """从配置段读取必需的字符串列表。"""
    value = raw[key]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SweepConfigError(f"{key} 必须是字符串列表")
    return value


def _require_relative_names(raw: dict[str, Any], key: str) -> list[str]:
    """读取 `.codex`、`tmp` 或 `.git` 这类单段相对名称。"""
    values = _require_str_list(raw, key)
    for value in values:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
            raise SweepConfigError(f"{key} 条目必须是简单相对名称: {value}")
    return values


def _require_int(raw: dict[str, Any], key: str, minimum: int) -> int:
    """读取带下界的整数配置。"""
    value = raw[key]
    if not isinstance(value, int) or value < minimum:
        raise SweepConfigError(f"{key} 必须是大于等于 {minimum} 的整数")
    return value


def _resolve_user_path(raw_path: str) -> Path:
    """展开用户路径，但不要求路径当前已经存在。"""
    return Path(raw_path).expanduser().resolve(strict=False)


def _resolve_data_child(
    data_dir: Path,
    raw_path: str,
    key: str,
    *,
    allow_parent: bool = False,
) -> Path:
    """解析相对于 SWEEP 数据目录的路径。"""
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = data_dir / path
    resolved = path.resolve(strict=False)
    if not allow_parent and ".." in Path(raw_path).parts:
        raise SweepConfigError(f"{key} 不能包含 '..': {raw_path}")
    return resolved


def _has_codex_trash_parent(path: Path) -> bool:
    """判断 fallback 目标是否位于 `.codex/_trash_bin_` 之下。"""
    parts = path.parts
    for index, part in enumerate(parts[:-1]):
        if part == ".codex" and index + 1 < len(parts) and parts[index + 1] == "_trash_bin_":
            return True
    return False


def _dedupe_paths(paths: Any) -> list[Path]:
    """规范化路径并去重，同时保留首次出现顺序。"""
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        resolved = Path(path).expanduser().resolve(strict=False)
        key = resolved.as_posix()
        if key not in seen:
            result.append(resolved)
            seen.add(key)
    return result


def _hash_config(config: dict[str, Any]) -> str:
    """计算合并后配置的哈希，用于缓存失效判断。"""
    payload = json.dumps(config, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
