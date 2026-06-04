"""Cleanup Candidate 的创建、重验、历史失败重建与去重。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .config import SweepConfig
from .models import (
    CandidateGroup,
    CandidateKind,
    CleanupCandidate,
    MoveFailure,
    ProjectEntry,
    ScopeType,
)
from .path_rules import (
    belongs_to_any,
    is_basic_safe_path,
    is_expired,
    is_in_cleanup_scope,
    is_protected_root,
    is_temp_named_file,
    is_under,
    is_under_any_named,
    tree_all_expired,
)
from .project_discovery import find_project_root_for_path, nearest_watch_dir


def project_candidate(
    *,
    path: Path,
    group: CandidateGroup,
    kind: CandidateKind,
    reason: str,
    watch_dir: Path,
    project_entry: ProjectEntry,
    config: SweepConfig,
) -> CleanupCandidate:
    """创建规范化的项目范围 Cleanup Candidate。"""
    return CleanupCandidate(
        path=path.resolve(strict=False),
        scope_type=ScopeType.PROJECT,
        group=group,
        kind=kind,
        keep_days=config.projects.keep_days,
        reason=reason,
        watch_dir=watch_dir.resolve(strict=False),
        project_root=project_entry.root,
    )


def validate_candidate(candidate: CleanupCandidate, config: SweepConfig, now: datetime) -> bool:
    """按当前文件系统状态重新确认候选仍然可以移动。"""
    path = candidate.path
    if not is_basic_safe_path(path, config):
        return False
    if not is_in_cleanup_scope(path, config):
        return False
    if is_protected_root(path, config):
        return False

    if candidate.scope_type in (ScopeType.SYSTEM_TEMP, ScopeType.DOWNLOADS):
        return (
            path.is_file()
            and not path.is_symlink()
            and is_expired(path, candidate.keep_days, now)
            and is_under(path, candidate.watch_dir)
        )

    if candidate.project_root is None or not is_under(path, candidate.project_root):
        return False
    if candidate.kind is CandidateKind.POST_CLEANUP_EMPTY_DIRECTORY:
        return path.is_dir()
    if candidate.kind is CandidateKind.FILE:
        return path.is_file() and is_expired(path, candidate.keep_days, now)
    if candidate.kind is CandidateKind.DIRECTORY:
        if not path.is_dir():
            return False
        return tree_all_expired(path, candidate.keep_days, config, now)
    return False


def candidate_from_unresolved_path(
    path: Path,
    scope_type: ScopeType | None,
    group: CandidateGroup | None,
    project_root: Path | None,
    config: SweepConfig,
    now: datetime,
) -> CleanupCandidate | None:
    """仅在历史失败路径仍满足当前规则时重建重试候选。"""
    resolved = path.expanduser().resolve(strict=False)
    if not is_basic_safe_path(resolved, config):
        return None
    if scope_type is ScopeType.SYSTEM_TEMP or belongs_to_any(resolved, config.system_temp.dirs):
        return _candidate_for_age_scope_path(
            resolved,
            ScopeType.SYSTEM_TEMP,
            config.system_temp.keep_days,
            config,
            now,
        )
    if scope_type is ScopeType.DOWNLOADS or belongs_to_any(resolved, config.downloads.dirs):
        return _candidate_for_age_scope_path(
            resolved,
            ScopeType.DOWNLOADS,
            config.downloads.keep_days,
            config,
            now,
        )

    root = project_root.expanduser().resolve(strict=False) if project_root else None
    if root is None or not is_under(resolved, root):
        root = find_project_root_for_path(resolved, config)
    if root is None:
        return None

    candidate_group = group or CandidateGroup.PARTIAL_ITEMS
    if resolved.is_file() and _project_file_is_candidate(resolved, root, config, now):
        return CleanupCandidate(
            path=resolved,
            scope_type=ScopeType.PROJECT,
            group=CandidateGroup.PARTIAL_ITEMS,
            kind=CandidateKind.FILE,
            keep_days=config.projects.keep_days,
            reason="retry_unresolved_project_file",
            watch_dir=nearest_watch_dir(resolved, root, config) or root,
            project_root=root,
            retry_unresolved=True,
        )
    if resolved.is_dir() and _project_dir_is_candidate(
        resolved, root, candidate_group, config, now
    ):
        return CleanupCandidate(
            path=resolved,
            scope_type=ScopeType.PROJECT,
            group=candidate_group,
            kind=CandidateKind.DIRECTORY,
            keep_days=config.projects.keep_days,
            reason="retry_unresolved_project_dir",
            watch_dir=nearest_watch_dir(resolved, root, config) or root,
            project_root=root,
            retry_unresolved=True,
        )
    return None


def revalidate_candidates(
    candidates: list[CleanupCandidate],
    config: SweepConfig,
    now: datetime,
) -> tuple[list[CleanupCandidate], list[MoveFailure]]:
    """把候选拆成可执行项和应跳过的重验失败项。"""
    valid: list[CleanupCandidate] = []
    skipped: list[MoveFailure] = []
    for candidate in candidates:
        if validate_candidate(candidate, config, now):
            valid.append(candidate)
        else:
            skipped.append(
                MoveFailure(
                    candidate=candidate,
                    stage="revalidate",
                    code="not_candidate",
                    message="路径已不再满足当前 Cleanup Candidate 规则。",
                )
            )
    return valid, skipped


def dedupe_candidates(candidates: list[CleanupCandidate]) -> list[CleanupCandidate]:
    """候选去重，并移除已被 whole_dir 覆盖的子路径。"""
    selected: dict[str, CleanupCandidate] = {}
    for candidate in candidates:
        key = candidate.key()
        existing = selected.get(key)
        if existing is None or _candidate_priority(candidate) < _candidate_priority(existing):
            selected[key] = candidate

    whole_dirs = [
        candidate.path.resolve(strict=False)
        for candidate in selected.values()
        if candidate.group is CandidateGroup.WHOLE_DIR
    ]
    result: list[CleanupCandidate] = []
    for candidate in selected.values():
        path = candidate.path.resolve(strict=False)
        if candidate.group is not CandidateGroup.WHOLE_DIR and any(
            is_under(path, whole_dir) and path != whole_dir for whole_dir in whole_dirs
        ):
            continue
        result.append(candidate)
    return sorted(result, key=lambda item: (item.group.value, str(item.path)))


def _candidate_for_age_scope_path(
    path: Path,
    scope_type: ScopeType,
    keep_days: int,
    config: SweepConfig,
    now: datetime,
) -> CleanupCandidate | None:
    roots = (
        config.system_temp.dirs if scope_type is ScopeType.SYSTEM_TEMP else config.downloads.dirs
    )
    if not path.is_file() or not is_expired(path, keep_days, now):
        return None
    for root in roots:
        if is_under(path, root):
            return CleanupCandidate(
                path=path,
                scope_type=scope_type,
                group=CandidateGroup.PARTIAL_ITEMS,
                kind=CandidateKind.FILE,
                keep_days=keep_days,
                reason=f"retry_unresolved_{scope_type.value}_file",
                watch_dir=root,
                retry_unresolved=True,
            )
    return None


def _project_file_is_candidate(path: Path, root: Path, config: SweepConfig, now: datetime) -> bool:
    """判断历史失败中的项目文件是否仍符合当前项目清理规则。"""
    if not path.is_file() or not is_expired(path, config.projects.keep_days, now):
        return False
    watch_dir = nearest_watch_dir(path, root, config)
    if watch_dir is None:
        return False
    if is_under_any_named(path, root, config.projects.temp_dirs):
        return True
    if is_under_any_named(path, root, config.projects.trash_bin_names):
        return True
    return is_temp_named_file(path.name, config)


def _project_dir_is_candidate(
    path: Path,
    root: Path,
    group: CandidateGroup,
    config: SweepConfig,
    now: datetime,
) -> bool:
    """判断历史失败中的项目目录是否仍可作为目录候选重试。"""
    if not path.is_dir() or not nearest_watch_dir(path, root, config):
        return False
    if any(path.name == name for name in config.projects.trash_bin_names):
        return False
    if group is CandidateGroup.WHOLE_DIR and path.name not in config.projects.temp_dirs:
        return False
    return tree_all_expired(path, config.projects.keep_days, config, now)


def _candidate_priority(candidate: CleanupCandidate) -> tuple[int, int]:
    group_score = 0 if candidate.group is CandidateGroup.WHOLE_DIR else 1
    kind_score = 2 if candidate.kind is CandidateKind.POST_CLEANUP_EMPTY_DIRECTORY else 0
    return group_score, kind_score
