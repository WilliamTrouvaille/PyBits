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
from .models import CandidateGroup, CandidateKind, CleanupCandidate, ProjectEntry, ScopeType
from .path_rules import is_basic_safe_path, is_expired, is_temp_named_file


@dataclass(frozen=True)
class ScopeScanOutput:
    """单个独立扫描任务产出的候选和警告。"""

    candidates: list[CleanupCandidate]
    warnings: list[str]


@dataclass(frozen=True)
class _TreeScanState:
    candidates: tuple[CleanupCandidate, ...]
    remaining_after_cleanup: bool
    all_expired: bool


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

    candidates: list[CleanupCandidate] = []

    def walk(directory: Path, depth: int) -> None:
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    if not is_basic_safe_path(path, config) or entry.is_symlink():
                        continue
                    if entry.is_file(follow_symlinks=False):
                        if is_expired(path, keep_days, now):
                            candidates.append(
                                CleanupCandidate(
                                    path=path.resolve(strict=False),
                                    scope_type=scope_type,
                                    group=CandidateGroup.PARTIAL_ITEMS,
                                    kind=CandidateKind.FILE,
                                    keep_days=keep_days,
                                    reason=reason,
                                    watch_dir=root,
                                )
                            )
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name in config.scan.skip_dirs:
                            continue
                        if depth < config.scan.max_depth:
                            walk(path, depth + 1)
        except OSError:
            return

    walk(root, 0)
    return ScopeScanOutput(candidates=candidates, warnings=warnings)


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
                _scan_temp_tree(
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
    candidates: list[CleanupCandidate] = []

    def walk(directory: Path, depth: int) -> None:
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    if not is_basic_safe_path(path, config) or entry.is_symlink():
                        continue
                    if entry.is_file(follow_symlinks=False):
                        if is_temp_named_file(entry.name, config) and is_expired(
                            path, config.projects.keep_days, now
                        ):
                            candidates.append(
                                project_candidate(
                                    path=path,
                                    group=CandidateGroup.PARTIAL_ITEMS,
                                    kind=CandidateKind.FILE,
                                    reason="managed_temp_named_file",
                                    watch_dir=managed_dir,
                                    project_entry=project_entry,
                                    config=config,
                                )
                            )
                        continue
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    if entry.name in config.scan.skip_dirs:
                        continue
                    if entry.name in config.projects.trash_bin_names:
                        candidates.extend(
                            _scan_trash_bin_contents(path, project_entry, path, config, now)
                        )
                        continue
                    if entry.name in config.projects.temp_dirs:
                        candidates.extend(
                            _scan_temp_tree(
                                path,
                                project_entry,
                                path,
                                config,
                                now,
                                whole_dir_group=CandidateGroup.WHOLE_DIR,
                            )
                        )
                        continue
                    if depth < config.scan.max_depth:
                        walk(path, depth + 1)
        except OSError:
            return

    walk(managed_dir, 0)
    return candidates


def _scan_trash_bin_contents(
    trash_dir: Path,
    project_entry: ProjectEntry,
    watch_dir: Path,
    config: SweepConfig,
    now: datetime,
) -> list[CleanupCandidate]:
    """扫描 `_trash_bin_` 内部过期内容，但保留 trash bin 根目录本身。"""
    candidates: list[CleanupCandidate] = []
    try:
        children = list(os.scandir(trash_dir))
    except OSError:
        return candidates

    for entry in children:
        path = Path(entry.path)
        if not is_basic_safe_path(path, config) or entry.is_symlink():
            continue
        if entry.is_file(follow_symlinks=False):
            if is_expired(path, config.projects.keep_days, now):
                candidates.append(
                    project_candidate(
                        path=path,
                        group=CandidateGroup.PARTIAL_ITEMS,
                        kind=CandidateKind.FILE,
                        reason="trash_bin_expired_file",
                        watch_dir=watch_dir,
                        project_entry=project_entry,
                        config=config,
                    )
                )
            continue
        if entry.is_dir(follow_symlinks=False):
            candidates.extend(
                _scan_temp_tree(
                    path,
                    project_entry,
                    watch_dir,
                    config,
                    now,
                    whole_dir_group=CandidateGroup.PARTIAL_ITEMS,
                )
            )
    return candidates


def _scan_temp_tree(
    root: Path,
    project_entry: ProjectEntry,
    watch_dir: Path,
    config: SweepConfig,
    now: datetime,
    *,
    whole_dir_group: CandidateGroup,
) -> list[CleanupCandidate]:
    """扫描项目临时目录树，并返回可移动候选。"""
    state = _scan_expirable_tree(
        directory=root,
        project_entry=project_entry,
        watch_dir=watch_dir,
        config=config,
        now=now,
        allow_directory_candidate=config.projects.allow_dir_candidates,
        whole_dir_group=whole_dir_group,
    )
    return list(state.candidates)


def _scan_expirable_tree(
    *,
    directory: Path,
    project_entry: ProjectEntry,
    watch_dir: Path,
    config: SweepConfig,
    now: datetime,
    allow_directory_candidate: bool,
    whole_dir_group: CandidateGroup,
) -> _TreeScanState:
    """
    后序扫描项目临时目录树。

    采用后序遍历的原因是，SWEEP 必须先确认所有后代是否都过期，才能安全地用
    一个 `whole_dir` 目录移动替换多个子候选。

    Args:
        directory: 当前正在检查的目录。
        project_entry: 所属项目根和 Watch Dir 描述。
        watch_dir: 授权扫描当前树的 Watch Dir。
        config: 已校验的 SWEEP 配置。
        now: 本轮扫描使用的当前时间。
        allow_directory_candidate: 是否允许目录本身成为候选。
        whole_dir_group: 当前根目录整体过期时使用的可见候选分组。

    Returns:
        当前子树的候选、清理后是否仍有残留，以及整棵树是否过期。
    """
    if not is_basic_safe_path(directory, config) or directory.is_symlink():
        return _TreeScanState(candidates=(), remaining_after_cleanup=True, all_expired=False)

    candidates: list[CleanupCandidate] = []
    remaining_after_cleanup = False
    all_children_expired = True
    child_candidate_seen = False

    try:
        entries = list(os.scandir(directory))
    except OSError:
        return _TreeScanState(candidates=(), remaining_after_cleanup=True, all_expired=False)

    for entry in entries:
        path = Path(entry.path)
        if not is_basic_safe_path(path, config) or entry.is_symlink():
            remaining_after_cleanup = True
            all_children_expired = False
            continue
        if entry.is_file(follow_symlinks=False):
            if is_expired(path, config.projects.keep_days, now):
                candidates.append(
                    project_candidate(
                        path=path,
                        group=CandidateGroup.PARTIAL_ITEMS,
                        kind=CandidateKind.FILE,
                        reason="temp_tree_expired_file",
                        watch_dir=watch_dir,
                        project_entry=project_entry,
                        config=config,
                    )
                )
                child_candidate_seen = True
            else:
                remaining_after_cleanup = True
                all_children_expired = False
            continue
        if not entry.is_dir(follow_symlinks=False):
            remaining_after_cleanup = True
            all_children_expired = False
            continue
        if entry.name in config.scan.skip_dirs:
            remaining_after_cleanup = True
            all_children_expired = False
            continue

        child_state = _scan_expirable_tree(
            directory=path,
            project_entry=project_entry,
            watch_dir=watch_dir,
            config=config,
            now=now,
            allow_directory_candidate=allow_directory_candidate,
            whole_dir_group=CandidateGroup.PARTIAL_ITEMS,
        )
        candidates.extend(child_state.candidates)
        child_candidate_seen = child_candidate_seen or bool(child_state.candidates)
        remaining_after_cleanup = remaining_after_cleanup or child_state.remaining_after_cleanup
        all_children_expired = all_children_expired and child_state.all_expired

    directory_expired = is_expired(directory, config.projects.keep_days, now)
    all_expired = directory_expired and all_children_expired
    if allow_directory_candidate and all_expired:
        return _TreeScanState(
            candidates=(
                project_candidate(
                    path=directory,
                    group=whole_dir_group,
                    kind=CandidateKind.DIRECTORY,
                    reason="expired_directory_tree",
                    watch_dir=watch_dir,
                    project_entry=project_entry,
                    config=config,
                ),
            ),
            remaining_after_cleanup=False,
            all_expired=True,
        )

    if allow_directory_candidate and child_candidate_seen and not remaining_after_cleanup:
        candidates.append(
            project_candidate(
                path=directory,
                group=CandidateGroup.PARTIAL_ITEMS,
                kind=CandidateKind.POST_CLEANUP_EMPTY_DIRECTORY,
                reason="post_cleanup_empty_directory",
                watch_dir=watch_dir,
                project_entry=project_entry,
                config=config,
            )
        )
        remaining_after_cleanup = False
    else:
        remaining_after_cleanup = True

    return _TreeScanState(
        candidates=tuple(candidates),
        remaining_after_cleanup=remaining_after_cleanup,
        all_expired=all_expired,
    )
