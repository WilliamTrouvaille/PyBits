"""处理 SWEEP 失败候选的 soft-delete fallback 和有限权限修复。

本模块是唯一尝试权限修复的位置。权限修复策略保持收紧：路径必须已经是
Cleanup Candidate、位于已配置 Cleanup Scope、归当前用户所有，且不是 symlink。
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

from _shared.utils.trash import soft_delete

from .config import SweepConfig
from .models import CleanupCandidate, MovedPath, MoveFailure
from .trash_runner import TrashAvailability, move_single_with_trash
from .unresolved_manifest import append_unresolved_event


@dataclass(frozen=True)
class FailureHandlingResult:
    """trash 失败后 fallback 和权限修复阶段的处理结果。"""

    moved: tuple[MovedPath, ...]
    unresolved: tuple[MoveFailure, ...]
    repaired: tuple[Path, ...]


def handle_failures(
    failures: list[MoveFailure],
    config: SweepConfig,
    availability: TrashAvailability,
) -> FailureHandlingResult:
    """
    尝试 fallback、可选权限修复，并追加 unresolved 审计事件。

    Args:
        failures: trash 阶段产生的失败候选列表。
        config: 已校验的 SWEEP 配置。
        availability: 启动时解析出的 trash 命令状态。

    Returns:
        fallback 成功移动、仍 unresolved 以及已修复路径的汇总结果。
    """
    moved: list[MovedPath] = []
    unresolved: list[MoveFailure] = []
    repaired: list[Path] = []

    for failure in failures:
        candidate = failure.candidate
        fallback = _try_soft_delete(candidate, config, failure)
        if fallback is not None:
            moved.append(fallback)
            continue

        repair_code = _repair_candidate(candidate, config)
        if repair_code == "repaired":
            repaired.append(candidate.path)
            retry_result = (
                move_single_with_trash(candidate, config, availability)
                if availability.available
                else None
            )
            if retry_result is not None and retry_result.moved:
                moved.extend(retry_result.moved)
                continue
            retry_failure = (
                retry_result.failures[0]
                if retry_result is not None and retry_result.failures
                else failure
            )
            fallback = _try_soft_delete(candidate, config, retry_failure)
            if fallback is not None:
                moved.append(fallback)
                continue
            final_failure = MoveFailure(
                candidate=candidate,
                stage="fallback",
                code="fallback_failed",
                message="有限权限修复后 soft-delete fallback 仍然失败。",
            )
        else:
            final_failure = MoveFailure(
                candidate=candidate,
                stage="repair",
                code=repair_code,
                message=f"有限权限修复不允许执行或执行失败: {repair_code}。",
            )

        append_unresolved_event(config, final_failure)
        unresolved.append(final_failure)

    return FailureHandlingResult(
        moved=tuple(moved),
        unresolved=tuple(unresolved),
        repaired=tuple(repaired),
    )


def _try_soft_delete(
    candidate: CleanupCandidate,
    config: SweepConfig,
    failure: MoveFailure,
) -> MovedPath | None:
    """尝试把失败候选移动到配置的 `.codex/_trash_bin_` 区域。"""
    if not config.trash.fallback_to_soft_delete:
        return None
    if not candidate.path.exists() and not candidate.path.is_symlink():
        return MovedPath(candidate=candidate, method="already_missing")

    trash_root = _fallback_trash_root(candidate, config)
    try:
        destination = soft_delete(
            candidate.path,
            reason=f"sweep-{failure.code}",
            trash_root=trash_root,
        )
    except Exception:
        return None
    return MovedPath(candidate=candidate, method="soft_delete", destination=destination)


def _fallback_trash_root(candidate: CleanupCandidate, config: SweepConfig) -> Path:
    """优先使用项目内 trash；外部范围使用 PyBits 级 trash 区域。"""
    if candidate.project_root is not None:
        codex_dir = candidate.project_root / ".codex"
        if codex_dir.exists() and codex_dir.is_dir():
            project_trash = candidate.project_root / config.failure_policy.project_trash_dir_name
            if not _is_under(candidate.path, project_trash):
                return project_trash
    return config.failure_policy.external_trash_dir


def _repair_candidate(candidate: CleanupCandidate, config: SweepConfig) -> str:
    """尝试策略允许的、仅限当前用户拥有路径的有限权限修复。"""
    if not config.failure_policy.repair_owned_paths:
        return "repair_disabled"
    if candidate.path.is_symlink():
        return "symlink"
    if not candidate.path.exists():
        return "missing"
    if not _is_in_scope(candidate.path, config):
        return "out_of_scope"

    try:
        path_stat = candidate.path.stat(follow_symlinks=False)
    except OSError:
        return "stat_failed"

    current_uid = os.getuid()
    if path_stat.st_uid == 0:
        return "root_owned"
    if path_stat.st_uid != current_uid:
        return "other_user_owned"
    if _has_unclear_acl(candidate.path):
        return "acl_unclear"

    try:
        mode = stat.S_IMODE(path_stat.st_mode)
        if candidate.path.is_dir():
            candidate.path.chmod(mode | stat.S_IWUSR | stat.S_IXUSR)
        else:
            candidate.path.chmod(mode | stat.S_IWUSR)
        if config.failure_policy.clear_macos_user_immutable_flag and platform.system() == "Darwin":
            _clear_user_immutable_flag(candidate.path)
    except OSError:
        return "chmod_failed"

    return "repaired"


def _clear_user_immutable_flag(path: Path) -> None:
    """在配置允许且命令可用时清理 macOS 用户不可变标记。"""
    chflags = shutil.which("chflags")
    if chflags is None:
        return
    subprocess.run(
        [chflags, "nouchg", str(path)],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def _has_unclear_acl(path: Path) -> bool:
    """把带 macOS ACL 标记的路径视为权限不明确，从而跳过修复。"""
    if platform.system() != "Darwin":
        return False
    try:
        completed = subprocess.run(
            ["/bin/ls", "-lde", str(path)],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return True
    if completed.returncode != 0 or not completed.stdout:
        return True
    mode_text = completed.stdout.split(maxsplit=1)[0]
    return mode_text.endswith("+")


def _is_in_scope(path: Path, config: SweepConfig) -> bool:
    """判断权限修复是否仍被约束在配置的 Cleanup Scope 内。"""
    return any(_is_under(path, root) for root in config.cleanup_scope_roots())


def _is_under(path: Path, root: Path) -> bool:
    """判断路径是否等于或位于指定根目录下。"""
    resolved_path = path.expanduser().resolve(strict=False)
    resolved_root = root.expanduser().resolve(strict=False)
    return resolved_path == resolved_root or resolved_root in resolved_path.parents
