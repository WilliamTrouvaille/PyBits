"""处理 unresolved 重试合并和执行顺序的规划辅助函数。

planner 位于扫描和执行之间。它不判断路径是否像临时文件，只负责把扫描结果与
append-only unresolved manifest 合并，并决定执行顺序。
"""

from __future__ import annotations

from datetime import datetime

from .candidate_rules import candidate_from_unresolved_path
from .config import SweepConfig
from .models import (
    BlockedUnresolved,
    CandidateGroup,
    CandidateKind,
    CleanupCandidate,
    UnresolvedRecord,
)

NON_RETRIABLE_FAILURE_CODES = {
    "root_owned",
    "other_user_owned",
    "acl_unclear",
    "out_of_scope",
    "symlink",
    "not_candidate",
}


def merge_unresolved_candidates(
    candidates: list[CleanupCandidate],
    unresolved_records: list[UnresolvedRecord],
    config: SweepConfig,
    now: datetime,
) -> tuple[list[CleanupCandidate], list[BlockedUnresolved]]:
    """
    在当前规则校验后合并可重试的 unresolved 路径。

    Args:
        candidates: 本轮扫描得到的候选列表。
        unresolved_records: unresolved manifest 中仍处于 unresolved 状态的最新记录。
        config: 已校验的 SWEEP 配置。
        now: 本轮判断使用的当前时间。

    Returns:
        合并后的候选列表，以及当前不可重试的 unresolved 路径列表。
    """
    by_key = {candidate.key(): candidate for candidate in candidates}
    blocked: list[BlockedUnresolved] = []

    for record in unresolved_records:
        if record.failure_code in NON_RETRIABLE_FAILURE_CODES:
            blocked.append(
                BlockedUnresolved(
                    path=record.original_path,
                    reason=f"non_retriable_failure:{record.failure_code}",
                    record=record,
                )
            )
            continue

        existing = by_key.get(record.original_path.resolve(strict=False).as_posix())
        if existing is not None:
            by_key[existing.key()] = existing.for_retry()
            continue

        candidate = candidate_from_unresolved_path(
            path=record.original_path,
            scope_type=record.scope_type,
            group=record.group,
            project_root=record.project_root,
            config=config,
            now=now,
        )
        if candidate is None:
            blocked.append(
                BlockedUnresolved(
                    path=record.original_path,
                    reason="no_longer_matches_current_candidate_rules",
                    record=record,
                )
            )
            continue
        by_key[candidate.key()] = candidate.for_retry()

    merged = list(by_key.values())
    merged.sort(key=_display_sort_key)
    return merged, blocked


def order_for_execution(candidates: list[CleanupCandidate]) -> list[CleanupCandidate]:
    """
    把具体候选排在延迟空目录候选之前。

    Args:
        candidates: 已通过重验的候选列表。

    Returns:
        适合执行阶段使用的排序后候选列表。
    """
    return sorted(candidates, key=_execution_sort_key)


def _display_sort_key(candidate: CleanupCandidate) -> tuple[int, str]:
    retry_score = 0 if candidate.retry_unresolved else 1
    return retry_score, candidate.path.as_posix()


def _execution_sort_key(candidate: CleanupCandidate) -> tuple[int, int, str]:
    empty_score = 1 if candidate.kind is CandidateKind.POST_CLEANUP_EMPTY_DIRECTORY else 0
    depth_score = -len(candidate.path.parts)
    group_score = 0 if candidate.group is CandidateGroup.PARTIAL_ITEMS else 1
    return empty_score, group_score, f"{depth_score:06d}:{candidate.path.as_posix()}"
