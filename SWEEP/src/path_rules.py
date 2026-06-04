"""提供 SWEEP 安全边界和过期判断所需的路径谓词。

本模块刻意保持轻依赖，只回答单个文件系统路径的性质问题。路径是否属于项目、
retry manifest 或执行计划，由更高层模块决定。
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from .config import SweepConfig


def is_basic_safe_path(path: Path, config: SweepConfig) -> bool:
    """
    判断 SWEEP 是否可以在基础安全边界内检查该路径。

    Args:
        path: 待检查路径。
        config: 已校验的 SWEEP 配置。

    Returns:
        路径不含被拒绝字符且不是 symlink 时返回 True。
    """
    if config.scan.reject_paths_containing_newline and "\n" in path.as_posix():
        return False
    return not path.is_symlink()


def is_expired(path: Path, keep_days: int, now: datetime) -> bool:
    """
    判断路径是否早于配置的保留窗口。

    Args:
        path: 待检查路径。
        keep_days: 保留天数。
        now: 本轮扫描使用的当前时间。

    Returns:
        路径 mtime 早于或等于截止时间时返回 True；无法 stat 时返回 False。
    """
    try:
        mtime = datetime.fromtimestamp(path.stat(follow_symlinks=False).st_mtime)
    except OSError:
        return False
    return mtime <= now - timedelta(days=keep_days)


def tree_all_expired(path: Path, keep_days: int, config: SweepConfig, now: datetime) -> bool:
    """
    判断目录及其所有后代是否都过期且安全。

    Args:
        path: 待检查目录。
        keep_days: 保留天数。
        config: 已校验的 SWEEP 配置。
        now: 本轮扫描使用的当前时间。

    Returns:
        目录本身和所有后代都过期、可检查且不含 symlink 时返回 True。
    """
    if not path.is_dir() or not is_expired(path, keep_days, now):
        return False
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                child = Path(entry.path)
                if not is_basic_safe_path(child, config) or entry.is_symlink():
                    return False
                if entry.is_dir(follow_symlinks=False):
                    if not tree_all_expired(child, keep_days, config, now):
                        return False
                elif not is_expired(child, keep_days, now):
                    return False
    except OSError:
        return False
    return True


def is_in_cleanup_scope(path: Path, config: SweepConfig) -> bool:
    """
    判断路径是否属于任一配置的 Cleanup Scope。

    Args:
        path: 待检查路径。
        config: 已校验的 SWEEP 配置。

    Returns:
        路径等于或位于任一授权根目录下时返回 True。
    """
    return belongs_to_any(path, config.cleanup_scope_roots())


def is_protected_root(path: Path, config: SweepConfig) -> bool:
    """
    判断路径是否属于永远不能成为 Cleanup Candidate 的保护根。

    Args:
        path: 待检查路径。
        config: 已校验的 SWEEP 配置。

    Returns:
        路径是文件系统根、用户 HOME 或 Cleanup Scope 根目录本身时返回 True。
    """
    resolved = path.expanduser().resolve(strict=False)
    home = Path.home().resolve(strict=False)
    protected = {Path("/").resolve(), home, *config.cleanup_scope_roots()}
    return any(resolved == item for item in protected)


def belongs_to_any(path: Path, roots: tuple[Path, ...]) -> bool:
    """
    判断路径是否等于或位于任一根目录下。

    Args:
        path: 待检查路径。
        roots: 可作为上级的根目录列表。

    Returns:
        任一根目录包含该路径时返回 True。
    """
    return any(is_under(path, root) for root in roots)


def is_under(path: Path, root: Path) -> bool:
    """
    展开路径后判断它是否等于或嵌套在指定根目录下。

    Args:
        path: 待检查路径。
        root: 预期根目录。

    Returns:
        `path` 等于 `root` 或位于 `root` 内部时返回 True。
    """
    resolved_path = path.expanduser().resolve(strict=False)
    resolved_root = root.expanduser().resolve(strict=False)
    return resolved_path == resolved_root or resolved_root in resolved_path.parents


def is_under_any_named(path: Path, root: Path, names: tuple[str, ...]) -> bool:
    """
    判断项目相对路径是否经过指定名称的目录。

    Args:
        path: 项目内路径。
        root: 项目根目录。
        names: 需要匹配的目录名集合。

    Returns:
        项目相对路径中任一段命中 `names` 时返回 True。
    """
    try:
        parts = path.resolve(strict=False).relative_to(root.resolve(strict=False)).parts
    except ValueError:
        return False
    return any(part in names for part in parts)


def is_temp_named_file(name: str, config: SweepConfig) -> bool:
    """
    判断文件名是否命中项目临时文件标记。

    Args:
        name: 文件名，不含路径。
        config: 已校验的 SWEEP 配置。

    Returns:
        文件名包含任一配置的临时文件标记时返回 True。
    """
    return any(token in name for token in config.projects.temp_file_name_contains)
