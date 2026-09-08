"""扫描项目 trash-bin 内容，同时保留 trash-bin 根目录。"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from .candidate_rules import project_candidate
from .config import SweepConfig
from .filesystem_scan import entry_is_dir, entry_is_file, list_directory_entries, safe_entry_path
from .models import CandidateGroup, CandidateKind, CleanupCandidate, ProjectEntry
from .path_rules import is_expired
from .project_tree_scanner import scan_temp_tree


def scan_trash_bin_contents(
    trash_dir: Path,
    project_entry: ProjectEntry,
    watch_dir: Path,
    config: SweepConfig,
    now: datetime,
) -> list[CleanupCandidate]:
    """
    扫描 `_trash_bin_` 内部过期内容，但保留 trash bin 根目录本身。

    Args:
        trash_dir: 当前项目内的 trash bin 目录。
        project_entry: 所属项目根和 Watch Dir 描述。
        watch_dir: 授权扫描该 trash bin 的 Watch Dir。
        config: 已校验的 SWEEP 配置。
        now: 本轮扫描使用的当前时间。

    Returns:
        trash bin 内部可移动候选；不会包含 trash bin 根目录。
    """
    candidates: list[CleanupCandidate] = []
    for entry in list_directory_entries(trash_dir):
        candidates.extend(_trash_bin_entry_candidates(entry, project_entry, watch_dir, config, now))
    return candidates


def _trash_bin_entry_candidates(
    entry: os.DirEntry[str],
    project_entry: ProjectEntry,
    watch_dir: Path,
    config: SweepConfig,
    now: datetime,
) -> tuple[CleanupCandidate, ...]:
    """处理 trash bin 内的单个文件或子目录。"""
    path = safe_entry_path(entry, config)
    if path is None:
        return ()
    if entry_is_file(entry):
        candidate = _trash_bin_file_candidate(path, project_entry, watch_dir, config, now)
        return (candidate,) if candidate is not None else ()
    if entry_is_dir(entry):
        return tuple(
            scan_temp_tree(
                path,
                project_entry,
                watch_dir,
                config,
                now,
                whole_dir_group=CandidateGroup.PARTIAL_ITEMS,
            )
        )
    return ()


def _trash_bin_file_candidate(
    path: Path,
    project_entry: ProjectEntry,
    watch_dir: Path,
    config: SweepConfig,
    now: datetime,
) -> CleanupCandidate | None:
    """创建 trash bin 内部过期文件候选。"""
    if not is_expired(path, config.projects.keep_days, now):
        return None
    return project_candidate(
        path=path,
        group=CandidateGroup.PARTIAL_ITEMS,
        kind=CandidateKind.FILE,
        reason="trash_bin_expired_file",
        watch_dir=watch_dir,
        project_entry=project_entry,
        config=config,
    )
