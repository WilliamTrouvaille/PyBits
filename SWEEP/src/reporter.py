"""生成 SWEEP 的人类可读报告和 JSON 报告。

报告模块只格式化已经计算出的候选和摘要，尽量不产生副作用。它不重新扫描，
也不修改 unresolved manifest。
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .models import (
    BlockedUnresolved,
    CandidateGroup,
    CleanupCandidate,
    ExecutionSummary,
    MoveFailure,
)


def print_candidate_report(
    candidates: list[CleanupCandidate],
    blocked_unresolved: list[BlockedUnresolved],
    *,
    dry_run: bool,
) -> None:
    """
    按用户可见分组和父目录打印完整候选清单。

    Args:
        candidates: 已通过重验的 Cleanup Candidate 列表。
        blocked_unresolved: 当前规则下不可重试的历史 unresolved 路径。
        dry_run: 是否为 dry-run 输出。
    """
    title = "SWEEP dry-run 候选清单" if dry_run else "SWEEP 候选清单"
    print(title)
    print("=" * len(title))
    for group in (CandidateGroup.WHOLE_DIR, CandidateGroup.PARTIAL_ITEMS):
        grouped = _group_by_parent(
            [candidate for candidate in candidates if candidate.group is group]
        )
        print()
        print(f"{group.value}: {sum(len(items) for items in grouped.values())}")
        if not grouped:
            print("  (无)")
            continue
        for parent, items in grouped.items():
            print(f"  {parent}")
            for candidate in items:
                retry = " retry_unresolved" if candidate.retry_unresolved else ""
                deferred = (
                    " deferred_empty_check"
                    if candidate.to_json().get("deferred_empty_check")
                    else ""
                )
                print(f"    - {candidate.path.name} [{candidate.reason}{retry}{deferred}]")

    if blocked_unresolved:
        print()
        print(f"unresolved blocked: {len(blocked_unresolved)}")
        for blocked in blocked_unresolved:
            print(f"  - {blocked.path} [{blocked.reason}]")


def print_execution_summary(summary: ExecutionSummary, dry_run: bool) -> None:
    """
    打印紧凑的人类可读执行摘要。

    Args:
        summary: 本轮执行摘要。
        dry_run: 是否为 dry-run 输出。
    """
    print()
    title = "SWEEP dry-run 摘要" if dry_run else "SWEEP 摘要"
    print(title)
    print("=" * len(title))
    print(f"trash_unavailable: {summary.trash_unavailable}")
    print(f"moved: {len(summary.moved)}")
    print(f"skipped: {len(summary.skipped)}")
    print(f"unresolved: {len(summary.unresolved)}")
    print(f"repaired: {len(summary.repaired)}")
    print(f"resolved_unresolved: {len(summary.resolved_unresolved)}")
    if summary.skipped:
        print("skipped 详情:")
        for item in summary.skipped:
            print(f"  - {item.candidate.path} [{item.reason}]")
    if summary.unresolved:
        print("unresolved 详情:")
        for failure in summary.unresolved:
            print(f"  - {failure.candidate.path} [{failure.stage}:{failure.code}]")


def build_json_summary(
    *,
    dry_run: bool,
    candidates: list[CleanupCandidate],
    blocked_unresolved: list[BlockedUnresolved],
    validation_failures: list[MoveFailure],
    execution_summary: ExecutionSummary,
    cache_stats: dict[str, Any],
    warnings: list[str],
    summary_file: Path,
) -> dict[str, Any]:
    """
    构建可持久化并可选输出的机器可读运行摘要。

    Args:
        dry_run: 是否为 dry-run 运行。
        candidates: 本轮有效候选列表。
        blocked_unresolved: 当前不可重试的历史 unresolved 路径。
        validation_failures: 候选重验失败列表。
        execution_summary: 执行阶段摘要。
        cache_stats: 缓存统计信息。
        warnings: 扫描期间产生的警告信息。
        summary_file: 本轮摘要追加写入的目标文件路径。

    Returns:
        可 JSON 编码的运行摘要字典。
    """
    counts = _candidate_counts(candidates)
    return {
        "tool": "SWEEP",
        "dry_run": dry_run,
        "candidate_counts": counts,
        "candidates": [candidate.to_json() for candidate in candidates],
        "blocked_unresolved": [item.to_json() for item in blocked_unresolved],
        "validation_failures": [failure.to_json() for failure in validation_failures],
        "execution": execution_summary.to_json(),
        "cache": cache_stats,
        "warnings": warnings,
        "summary_file": str(summary_file),
    }


def print_json_summary(summary: dict[str, Any]) -> None:
    """
    使用稳定格式打印 JSON 摘要。

    Args:
        summary: 可 JSON 编码的摘要字典。
    """
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def _group_by_parent(candidates: list[CleanupCandidate]) -> dict[Path, list[CleanupCandidate]]:
    """按父目录聚合候选，便于终端输出阅读。"""
    grouped: dict[Path, list[CleanupCandidate]] = defaultdict(list)
    for candidate in sorted(candidates, key=lambda item: str(item.path)):
        grouped[candidate.path.parent].append(candidate)
    return dict(sorted(grouped.items(), key=lambda item: str(item[0])))


def _candidate_counts(candidates: list[CleanupCandidate]) -> dict[str, int]:
    """按可见分组和重试状态统计候选数量。"""
    counts = {
        CandidateGroup.WHOLE_DIR.value: 0,
        CandidateGroup.PARTIAL_ITEMS.value: 0,
    }
    for candidate in candidates:
        counts[candidate.group.value] += 1
    counts["total"] = len(candidates)
    counts["retry_unresolved"] = sum(1 for candidate in candidates if candidate.retry_unresolved)
    return counts
