"""发现 SWEEP 的项目根目录和 Watch Dir。

缓存保存本模块产出的 ProjectEntry 对象。缓存只记录 Watch Dir，不记录最终
Cleanup Candidate，因为过期和安全检查必须在每次运行时重新读取实时文件系统。
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import SweepConfig
from .models import ProjectEntry, WatchDir
from .path_rules import is_basic_safe_path, is_temp_named_file, is_under


def discover_project_entries(config: SweepConfig) -> list[ProjectEntry]:
    """
    从配置的项目范围中发现项目根目录和可复用 Watch Dir。

    Args:
        config: 已校验的 SWEEP 配置。

    Returns:
        按路径排序且去重后的项目描述列表。
    """
    roots: dict[str, ProjectEntry] = {}
    for scan_root in config.projects.roots:
        for project_root in _discover_project_roots(scan_root, config):
            entry = build_project_entry(project_root, config)
            roots[entry.root.as_posix()] = entry

    for explicit_root in config.projects.extra_dirs:
        if is_project_root(explicit_root, config):
            entry = build_project_entry(explicit_root, config)
            roots[entry.root.as_posix()] = entry

    return [roots[key] for key in sorted(roots)]


def build_project_entry(project_root: Path, config: SweepConfig) -> ProjectEntry:
    """
    为一个项目根目录构建可缓存的项目描述。

    Args:
        project_root: 已识别出的项目根目录。
        config: 已校验的 SWEEP 配置。

    Returns:
        包含项目 marker 和 Watch Dir 的 ProjectEntry。
    """
    root = project_root.resolve(strict=False)
    markers = tuple(marker for marker in config.projects.root_markers if (root / marker).exists())
    watch_dirs: list[WatchDir] = []
    for name in config.projects.temp_dirs:
        candidate = root / name
        if candidate.is_dir() and not candidate.is_symlink():
            watch_dirs.append(WatchDir(path=candidate.resolve(strict=False), kind="temp"))
    for name in config.projects.managed_dirs:
        candidate = root / name
        if candidate.is_dir() and not candidate.is_symlink():
            watch_dirs.append(WatchDir(path=candidate.resolve(strict=False), kind="managed"))
    return ProjectEntry(root=root, markers=markers, watch_dirs=tuple(watch_dirs))


def find_project_root_for_path(path: Path, config: SweepConfig) -> Path | None:
    """
    为历史失败路径查找仍然存在的最近项目根目录。

    Args:
        path: unresolved manifest 中记录的原始路径。
        config: 已校验的 SWEEP 配置。

    Returns:
        最近的项目根目录；找不到时返回 None。
    """
    for root in (*config.projects.extra_dirs, *config.projects.roots):
        if is_under(path, root):
            current = path if path.is_dir() else path.parent
            for directory in (current, *current.parents):
                if directory == root.parent:
                    break
                if is_project_root(directory, config):
                    return directory.resolve(strict=False)
    return None


def nearest_watch_dir(path: Path, root: Path, config: SweepConfig) -> Path | None:
    """
    返回授权扫描某个项目相对路径的 Watch Dir。

    Args:
        path: 项目内待检查路径。
        root: 项目根目录。
        config: 已校验的 SWEEP 配置。

    Returns:
        匹配的 Watch Dir；路径不在受控清理区域内时返回 None。
    """
    relative_parts = path.resolve(strict=False).relative_to(root.resolve(strict=False)).parts
    if not relative_parts:
        return None
    first = relative_parts[0]
    direct = root / first
    if first in config.projects.temp_dirs:
        return direct
    if first not in config.projects.managed_dirs:
        return None
    for index, part in enumerate(relative_parts):
        if part in config.projects.temp_dirs or part in config.projects.trash_bin_names:
            return root.joinpath(*relative_parts[: index + 1])
    if is_temp_named_file(path.name, config):
        return direct
    return None


def is_project_root(path: Path, config: SweepConfig) -> bool:
    """
    判断目录是否满足当前项目根 marker 规则。

    Args:
        path: 待检查目录。
        config: 已校验的 SWEEP 配置。

    Returns:
        目录存在、不是 symlink 且包含任一项目 marker 时返回 True。
    """
    return (
        path.exists()
        and path.is_dir()
        and not path.is_symlink()
        and any((path / marker).exists() for marker in config.projects.root_markers)
    )


def _discover_project_roots(scan_root: Path, config: SweepConfig) -> list[Path]:
    """在一个项目扫描根目录下按深度限制发现项目根。"""
    if not scan_root.exists() or scan_root.is_symlink() or not scan_root.is_dir():
        return []

    discovered: list[Path] = []

    def walk(directory: Path, depth: int) -> None:
        if not is_basic_safe_path(directory, config):
            return
        if is_project_root(directory, config):
            discovered.append(directory.resolve(strict=False))
            return
        if depth >= config.scan.max_depth:
            return
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    if entry.name in config.scan.skip_dirs:
                        continue
                    walk(Path(entry.path), depth + 1)
        except OSError:
            return

    walk(scan_root, 0)
    return discovered
