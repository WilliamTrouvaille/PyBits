"""扫描项目临时目录树并折叠可移动目录候选。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .candidate_rules import project_candidate
from .config import SweepConfig
from .filesystem_scan import (
    entry_is_dir,
    entry_is_file,
    read_directory_entries,
    safe_entry_path,
)
from .models import CandidateGroup, CandidateKind, CleanupCandidate, ProjectEntry
from .path_rules import is_basic_safe_path, is_expired


@dataclass(frozen=True)
class _TreeScanState:
    """单棵子树扫描后的候选与残留状态。"""

    candidates: tuple[CleanupCandidate, ...]
    remaining_after_cleanup: bool
    all_expired: bool


@dataclass(frozen=True)
class _ProjectTreeScan:
    """项目临时树扫描所需的稳定上下文。"""

    project_entry: ProjectEntry
    watch_dir: Path
    config: SweepConfig
    now: datetime
    allow_directory_candidate: bool


def scan_temp_tree(
    root: Path,
    project_entry: ProjectEntry,
    watch_dir: Path,
    config: SweepConfig,
    now: datetime,
    *,
    whole_dir_group: CandidateGroup,
) -> list[CleanupCandidate]:
    """
    扫描项目临时目录树，并返回可移动候选。

    Args:
        root: 临时目录树根。
        project_entry: 所属项目根和 Watch Dir 描述。
        watch_dir: 授权扫描当前树的 Watch Dir。
        config: 已校验的 SWEEP 配置。
        now: 本轮扫描使用的当前时间。
        whole_dir_group: 当前根目录整体过期时使用的可见候选分组。

    Returns:
        当前临时树中的文件、目录或延迟空目录候选。
    """
    scan = _ProjectTreeScan(
        project_entry=project_entry,
        watch_dir=watch_dir,
        config=config,
        now=now,
        allow_directory_candidate=config.projects.allow_dir_candidates,
    )
    state = _scan_expirable_tree(
        directory=root,
        scan=scan,
        whole_dir_group=whole_dir_group,
    )
    return list(state.candidates)


def _scan_expirable_tree(
    *,
    directory: Path,
    scan: _ProjectTreeScan,
    whole_dir_group: CandidateGroup,
) -> _TreeScanState:
    """
    后序扫描项目临时目录树。

    采用后序遍历的原因是，SWEEP 必须先确认所有后代是否都过期，才能安全地用
    一个 `whole_dir` 目录移动替换多个子候选。
    """
    if not is_basic_safe_path(directory, scan.config) or directory.is_symlink():
        return _blocked_tree_state()

    candidates: list[CleanupCandidate] = []
    remaining_after_cleanup = False
    all_children_expired = True
    child_candidate_seen = False

    entries = read_directory_entries(directory)
    if entries is None:
        return _blocked_tree_state()

    for entry in entries:
        child_state = _scan_expirable_child(entry, scan)
        candidates.extend(child_state.candidates)
        child_candidate_seen = child_candidate_seen or bool(child_state.candidates)
        remaining_after_cleanup = remaining_after_cleanup or child_state.remaining_after_cleanup
        all_children_expired = all_children_expired and child_state.all_expired

    return _finalize_tree_state(
        directory=directory,
        candidates=candidates,
        child_candidate_seen=child_candidate_seen,
        remaining_after_cleanup=remaining_after_cleanup,
        all_children_expired=all_children_expired,
        scan=scan,
        whole_dir_group=whole_dir_group,
    )


def _scan_expirable_child(entry: os.DirEntry[str], scan: _ProjectTreeScan) -> _TreeScanState:
    """把一个子条目折叠为父目录可合并的树状态。"""
    path = safe_entry_path(entry, scan.config)
    if path is None:
        return _blocked_tree_state()
    if entry_is_file(entry):
        return _expired_file_tree_state(path, scan)
    if not entry_is_dir(entry) or entry.name in scan.config.scan.skip_dirs:
        return _blocked_tree_state()
    return _scan_expirable_tree(
        directory=path,
        scan=scan,
        whole_dir_group=CandidateGroup.PARTIAL_ITEMS,
    )


def _expired_file_tree_state(path: Path, scan: _ProjectTreeScan) -> _TreeScanState:
    """把过期文件表示为可清理且不残留的子树状态。"""
    if not is_expired(path, scan.config.projects.keep_days, scan.now):
        return _blocked_tree_state()
    return _TreeScanState(
        candidates=(
            project_candidate(
                path=path,
                group=CandidateGroup.PARTIAL_ITEMS,
                kind=CandidateKind.FILE,
                reason="temp_tree_expired_file",
                watch_dir=scan.watch_dir,
                project_entry=scan.project_entry,
                config=scan.config,
            ),
        ),
        remaining_after_cleanup=False,
        all_expired=True,
    )


def _finalize_tree_state(
    *,
    directory: Path,
    candidates: list[CleanupCandidate],
    child_candidate_seen: bool,
    remaining_after_cleanup: bool,
    all_children_expired: bool,
    scan: _ProjectTreeScan,
    whole_dir_group: CandidateGroup,
) -> _TreeScanState:
    """根据子树状态决定产出目录候选、延迟空目录候选或保留残留。"""
    directory_expired = is_expired(directory, scan.config.projects.keep_days, scan.now)
    all_expired = directory_expired and all_children_expired
    if scan.allow_directory_candidate and all_expired:
        return _directory_candidate_state(directory, scan, whole_dir_group)

    if scan.allow_directory_candidate and child_candidate_seen and not remaining_after_cleanup:
        candidates.append(_post_cleanup_empty_dir_candidate(directory, scan))
        remaining_after_cleanup = False
    else:
        remaining_after_cleanup = True

    return _TreeScanState(
        candidates=tuple(candidates),
        remaining_after_cleanup=remaining_after_cleanup,
        all_expired=all_expired,
    )


def _directory_candidate_state(
    directory: Path,
    scan: _ProjectTreeScan,
    whole_dir_group: CandidateGroup,
) -> _TreeScanState:
    """把整棵过期目录树折叠为单个目录候选。"""
    return _TreeScanState(
        candidates=(
            project_candidate(
                path=directory,
                group=whole_dir_group,
                kind=CandidateKind.DIRECTORY,
                reason="expired_directory_tree",
                watch_dir=scan.watch_dir,
                project_entry=scan.project_entry,
                config=scan.config,
            ),
        ),
        remaining_after_cleanup=False,
        all_expired=True,
    )


def _post_cleanup_empty_dir_candidate(
    directory: Path,
    scan: _ProjectTreeScan,
) -> CleanupCandidate:
    """创建文件候选清理后才检查的空目录候选。"""
    return project_candidate(
        path=directory,
        group=CandidateGroup.PARTIAL_ITEMS,
        kind=CandidateKind.POST_CLEANUP_EMPTY_DIRECTORY,
        reason="post_cleanup_empty_directory",
        watch_dir=scan.watch_dir,
        project_entry=scan.project_entry,
        config=scan.config,
    )


def _blocked_tree_state() -> _TreeScanState:
    """返回会阻止父目录整体折叠的保守状态。"""
    return _TreeScanState(candidates=(), remaining_after_cleanup=True, all_expired=False)
