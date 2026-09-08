"""遍历文件系统并生成当前 Cleanup Candidate。

本模块中的函数职责刻意收窄：它们只遍历已知 Watch Dir 或按年龄判断的
Cleanup Scope 并产出候选，不读取缓存文件、不处理 unresolved 重试，也不执行移动。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .candidate_rules import project_candidate
from .config import SweepConfig
from .filesystem_scan import entry_is_dir, entry_is_file, list_directory_entries, safe_entry_path
from .models import CandidateGroup, CandidateKind, CleanupCandidate, ProjectEntry, ScopeType
from .path_rules import is_basic_safe_path, is_expired, is_temp_named_file
from .project_tree_scanner import scan_temp_tree
from .trash_bin_scanner import scan_trash_bin_contents


@dataclass(frozen=True)
class ScopeScanOutput:
    """单个独立扫描任务产出的候选和警告。"""

    candidates: list[CleanupCandidate]
    warnings: list[str]


@dataclass(frozen=True)
class _AgeScopeScan:
    """年龄型 Cleanup Scope 扫描所需的上下文。"""

    root: Path
    scope_type: ScopeType
    keep_days: int
    reason: str
    config: SweepConfig
    now: datetime


@dataclass(frozen=True)
class _ManagedDirScan:
    """项目受控目录扫描所需的上下文。"""

    managed_dir: Path
    project_entry: ProjectEntry
    config: SweepConfig
    now: datetime


def scan_age_scope_files(
    *,
    root: Path,
    scope_type: ScopeType,
    keep_days: int,
    reason: str,
    config: SweepConfig,
    now: datetime,
) -> ScopeScanOutput:
    """
    扫描 system-temp 或 downloads 范围，并且只产出文件候选。

    Args:
        root: 本次 age-based Cleanup Scope 的扫描根。
        scope_type: 输出候选所属的 Cleanup Scope 类型。
        keep_days: 保留天数。
        reason: 候选进入清单的机器可读原因。
        config: 已校验的 SWEEP 配置。
        now: 本轮扫描使用的当前时间。

    Returns:
        包含文件候选和扫描警告的 ScopeScanOutput。
    """
    warnings: list[str] = []
    if not root.exists():
        return ScopeScanOutput(candidates=[], warnings=warnings)
    if not root.is_dir() or root.is_symlink() or not is_basic_safe_path(root, config):
        warnings.append(f"已跳过无效扫描根: {root}")
        return ScopeScanOutput(candidates=[], warnings=warnings)

    scan = _AgeScopeScan(
        root=root,
        scope_type=scope_type,
        keep_days=keep_days,
        reason=reason,
        config=config,
        now=now,
    )
    candidates = _scan_age_file_tree(scan)
    return ScopeScanOutput(candidates=candidates, warnings=warnings)


def _scan_age_file_tree(scan: _AgeScopeScan) -> list[CleanupCandidate]:
    """
    栈式扫描年龄型 Cleanup Scope，并只生成文件候选。

    system-temp 和 downloads 范围不能把目录本身变成候选；因此目录条目只作为
    继续下钻的容器，最终输出始终是 `partial_items` 文件候选。
    """
    candidates: list[CleanupCandidate] = []
    stack: list[tuple[Path, int]] = [(scan.root, 0)]
    while stack:
        directory, depth = stack.pop()
        for entry in list_directory_entries(directory):
            path = safe_entry_path(entry, scan.config)
            if path is None:
                continue
            candidate = _age_scope_file_candidate(path, entry, scan)
            if candidate is not None:
                candidates.append(candidate)
                continue
            if _should_descend_age_scope(entry, depth, scan):
                stack.append((path, depth + 1))
    return candidates


def _age_scope_file_candidate(
    path: Path,
    entry: os.DirEntry[str],
    scan: _AgeScopeScan,
) -> CleanupCandidate | None:
    """创建 system-temp/downloads 的过期文件候选。"""
    if not entry_is_file(entry) or not is_expired(path, scan.keep_days, scan.now):
        return None
    return CleanupCandidate(
        path=path.resolve(strict=False),
        scope_type=scan.scope_type,
        group=CandidateGroup.PARTIAL_ITEMS,
        kind=CandidateKind.FILE,
        keep_days=scan.keep_days,
        reason=scan.reason,
        watch_dir=scan.root,
    )


def _should_descend_age_scope(
    entry: os.DirEntry[str],
    depth: int,
    scan: _AgeScopeScan,
) -> bool:
    """判断年龄型 Cleanup Scope 是否可以继续扫描子目录。"""
    return (
        entry_is_dir(entry)
        and entry.name not in scan.config.scan.skip_dirs
        and depth < scan.config.scan.max_depth
    )


def scan_project(
    project_entry: ProjectEntry, config: SweepConfig, now: datetime
) -> ScopeScanOutput:
    """
    扫描单个项目根目录下缓存的 Watch Dir。

    Args:
        project_entry: 项目根目录和 Watch Dir 描述。
        config: 已校验的 SWEEP 配置。
        now: 本轮扫描使用的当前时间。

    Returns:
        该项目产出的候选和扫描警告。
    """
    warnings: list[str] = []
    candidates: list[CleanupCandidate] = []
    for watch_dir in project_entry.watch_dirs:
        if not is_basic_safe_path(watch_dir.path, config):
            warnings.append(f"已跳过无效 Watch Dir: {watch_dir.path}")
            continue
        if watch_dir.kind == "temp":
            candidates.extend(
                scan_temp_tree(
                    watch_dir.path,
                    project_entry,
                    watch_dir.path,
                    config,
                    now,
                    whole_dir_group=CandidateGroup.WHOLE_DIR,
                )
            )
        elif watch_dir.kind == "managed":
            candidates.extend(_scan_managed_dir(watch_dir.path, project_entry, config, now))
    return ScopeScanOutput(candidates=candidates, warnings=warnings)


def _scan_managed_dir(
    managed_dir: Path,
    project_entry: ProjectEntry,
    config: SweepConfig,
    now: datetime,
) -> list[CleanupCandidate]:
    """扫描项目受控目录，发现内部临时文件、临时目录和 trash bin 内容。"""
    scan = _ManagedDirScan(
        managed_dir=managed_dir,
        project_entry=project_entry,
        config=config,
        now=now,
    )
    candidates: list[CleanupCandidate] = []
    stack: list[tuple[Path, int]] = [(managed_dir, 0)]
    while stack:
        directory, depth = stack.pop()
        for entry in list_directory_entries(directory):
            entry_candidates, descend_dir = _scan_managed_entry(entry, depth, scan)
            candidates.extend(entry_candidates)
            if descend_dir is not None:
                stack.append((descend_dir, depth + 1))
    return candidates


def _scan_managed_entry(
    entry: os.DirEntry[str],
    depth: int,
    scan: _ManagedDirScan,
) -> tuple[tuple[CleanupCandidate, ...], Path | None]:
    """
    处理项目受控目录中的单个条目。

    Returns:
        第一项是当前条目直接产生的候选；第二项是需要继续下钻的普通目录。
    """
    path = safe_entry_path(entry, scan.config)
    if path is None:
        return (), None

    candidate = _managed_temp_file_candidate(path, entry, scan)
    if candidate is not None:
        return (candidate,), None

    if not _is_scannable_managed_dir(entry, scan.config):
        return (), None
    if entry.name in scan.config.projects.trash_bin_names:
        return tuple(
            scan_trash_bin_contents(
                path,
                scan.project_entry,
                path,
                scan.config,
                scan.now,
            )
        ), None
    if entry.name in scan.config.projects.temp_dirs:
        return tuple(
            scan_temp_tree(
                path,
                scan.project_entry,
                path,
                scan.config,
                scan.now,
                whole_dir_group=CandidateGroup.WHOLE_DIR,
            )
        ), None
    if depth < scan.config.scan.max_depth:
        return (), path
    return (), None


def _managed_temp_file_candidate(
    path: Path,
    entry: os.DirEntry[str],
    scan: _ManagedDirScan,
) -> CleanupCandidate | None:
    """创建受控目录内按名称识别出的过期临时文件候选。"""
    if not entry_is_file(entry):
        return None
    if not is_temp_named_file(entry.name, scan.config):
        return None
    if not is_expired(path, scan.config.projects.keep_days, scan.now):
        return None
    return project_candidate(
        path=path,
        group=CandidateGroup.PARTIAL_ITEMS,
        kind=CandidateKind.FILE,
        reason="managed_temp_named_file",
        watch_dir=scan.managed_dir,
        project_entry=scan.project_entry,
        config=scan.config,
    )


def _is_scannable_managed_dir(entry: os.DirEntry[str], config: SweepConfig) -> bool:
    """判断受控目录条目是否是可继续分类处理的子目录。"""
    return entry_is_dir(entry) and entry.name not in config.scan.skip_dirs
