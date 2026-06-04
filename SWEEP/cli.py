"""SWEEP 命令行入口。

本文件只编排配置、扫描、历史失败重试、移动执行、fallback 和报告输出。
具体领域规则放在 `SWEEP.src.*` 模块中，避免 CLI 层承担清理判定。
"""

from __future__ import annotations

import sys
from argparse import Namespace
from dataclasses import replace
from datetime import datetime

from loguru import logger

from _shared.utils.logging import setup_tool_logger

from .src.cache import append_run_summary
from .src.candidate_rules import revalidate_candidates
from .src.cli_parser import build_parser
from .src.config import SweepConfig, SweepConfigError, load_config, resolve_trash_command
from .src.failure_handler import handle_failures
from .src.models import (
    CandidateKind,
    CleanupCandidate,
    ExecutionSummary,
    MovedPath,
    MoveFailure,
    SkippedCandidate,
)
from .src.planner import merge_unresolved_candidates, order_for_execution
from .src.project_root import find_sweep_data_dir
from .src.reporter import (
    build_json_summary,
    print_candidate_report,
    print_execution_summary,
    print_json_summary,
)
from .src.scanner import scan
from .src.trash_runner import TrashAvailability, move_with_trash
from .src.unresolved_manifest import append_resolved_event, load_latest_unresolved


def main(argv: list[str] | None = None) -> int:
    """解析命令行参数并运行一次 SWEEP。"""
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr.encoding != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8")

    data_dir = find_sweep_data_dir()
    parser = build_parser(data_dir / "setting.yaml")
    args = parser.parse_args(argv)

    if args.workers is not None and args.workers < 1:
        parser.error("--workers 必须大于 0")

    try:
        config = load_config(args.config.expanduser().resolve(strict=False), data_dir)
        if args.workers is not None:
            config = replace(config, scan=replace(config.scan, workers=args.workers))
        setup_tool_logger("SWEEP", logs_dir=data_dir / "logs", verbose=args.verbose)
        return _run(args, config)
    except SweepConfigError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("操作已取消。", file=sys.stderr)
        return 130
    except Exception as exc:
        logger.exception("SWEEP 运行失败")
        print(f"错误: {exc}", file=sys.stderr)
        return 1


def _run(args: Namespace, config: SweepConfig) -> int:
    """执行一次扫描、移动和报告流程。"""
    current_time = datetime.now()
    trash_command = resolve_trash_command(config.trash.command)
    availability = TrashAvailability(command=trash_command)
    trash_unavailable = not availability.available

    scan_result = scan(config, now=current_time)
    unresolved_records = load_latest_unresolved(config)
    merged_candidates, blocked_unresolved = merge_unresolved_candidates(
        list(scan_result.candidates),
        unresolved_records,
        config,
        current_time,
    )
    valid_candidates, validation_failures = revalidate_candidates(
        merged_candidates,
        config,
        current_time,
    )

    execution_summary = ExecutionSummary(trash_unavailable=trash_unavailable)
    execution_summary.skipped.extend(
        SkippedCandidate(candidate=failure.candidate, reason=failure.code)
        for failure in validation_failures
    )

    if args.dry_run:
        _finish_report(
            args=args,
            config=config,
            candidates=valid_candidates,
            blocked_unresolved=blocked_unresolved,
            validation_failures=validation_failures,
            execution_summary=execution_summary,
            cache_stats=scan_result.cache_stats.to_json(),
            warnings=list(scan_result.warnings),
        )
        return 0

    if not args.json:
        print_candidate_report(valid_candidates, blocked_unresolved, dry_run=False)

    ordered = order_for_execution(valid_candidates)
    concrete_candidates = [
        candidate
        for candidate in ordered
        if candidate.kind is not CandidateKind.POST_CLEANUP_EMPTY_DIRECTORY
    ]
    empty_dir_candidates = [
        candidate
        for candidate in ordered
        if candidate.kind is CandidateKind.POST_CLEANUP_EMPTY_DIRECTORY
    ]

    _move_candidates(concrete_candidates, config, availability, execution_summary)
    _move_candidates(
        empty_dir_candidates,
        config,
        availability,
        execution_summary,
        require_empty=True,
    )

    _finish_report(
        args=args,
        config=config,
        candidates=valid_candidates,
        blocked_unresolved=blocked_unresolved,
        validation_failures=validation_failures,
        execution_summary=execution_summary,
        cache_stats=scan_result.cache_stats.to_json(),
        warnings=list(scan_result.warnings),
    )

    has_unresolved = bool(execution_summary.unresolved or blocked_unresolved)
    if has_unresolved and config.failure_policy.exit_nonzero_on_unresolved:
        return 1
    return 0


def _move_candidates(
    candidates: list[CleanupCandidate],
    config: SweepConfig,
    availability: TrashAvailability,
    execution_summary: ExecutionSummary,
    *,
    require_empty: bool = False,
) -> None:
    """移动候选，并在移动前重新校验实时文件系统状态。"""
    if not candidates:
        return

    executable_candidates = _revalidate_before_move(candidates, config, execution_summary)
    if require_empty:
        executable_candidates = _filter_ready_empty_dirs(
            executable_candidates,
            execution_summary,
        )
    if not executable_candidates:
        return

    trash_result = move_with_trash(executable_candidates, config, availability)
    execution_summary.trash_unavailable = (
        execution_summary.trash_unavailable or trash_result.trash_unavailable
    )
    execution_summary.moved.extend(trash_result.moved)
    failure_result = handle_failures(list(trash_result.failures), config, availability)
    execution_summary.moved.extend(failure_result.moved)
    execution_summary.unresolved.extend(failure_result.unresolved)
    execution_summary.repaired.extend(failure_result.repaired)

    for moved in (*trash_result.moved, *failure_result.moved):
        _record_resolved_if_needed(moved, config, execution_summary)


def _revalidate_before_move(
    candidates: list[CleanupCandidate],
    config: SweepConfig,
    execution_summary: ExecutionSummary,
) -> list[CleanupCandidate]:
    """缩短扫描判定和实际移动之间的竞态窗口。"""
    valid_candidates, validation_failures = revalidate_candidates(
        candidates,
        config,
        datetime.now(),
    )
    execution_summary.skipped.extend(
        SkippedCandidate(candidate=failure.candidate, reason=failure.code)
        for failure in validation_failures
    )
    return valid_candidates


def _filter_ready_empty_dirs(
    candidates: list[CleanupCandidate],
    execution_summary: ExecutionSummary,
) -> list[CleanupCandidate]:
    """只移动清理后仍为空的延迟目录候选。"""
    ready = []
    for candidate in candidates:
        if not candidate.path.exists():
            execution_summary.skipped.append(
                SkippedCandidate(candidate=candidate, reason="missing_after_cleanup")
            )
            continue
        if not candidate.path.is_dir():
            execution_summary.skipped.append(
                SkippedCandidate(candidate=candidate, reason="not_directory_after_cleanup")
            )
            continue
        try:
            has_entries = any(candidate.path.iterdir())
        except OSError:
            execution_summary.skipped.append(
                SkippedCandidate(candidate=candidate, reason="cannot_check_empty_directory")
            )
            continue
        if has_entries:
            execution_summary.skipped.append(
                SkippedCandidate(candidate=candidate, reason="non_empty_after_cleanup")
            )
            continue
        ready.append(candidate)
    return ready


def _record_resolved_if_needed(
    moved: MovedPath,
    config: SweepConfig,
    execution_summary: ExecutionSummary,
) -> None:
    """历史 unresolved 重试成功后追加 resolved 审计事件。"""
    if not moved.candidate.retry_unresolved:
        return
    append_resolved_event(config, moved.candidate, moved.method)
    execution_summary.resolved_unresolved.append(moved.candidate)


def _finish_report(
    *,
    args: object,
    config: SweepConfig,
    candidates: list[CleanupCandidate],
    blocked_unresolved: list[object],
    validation_failures: list[MoveFailure],
    execution_summary: ExecutionSummary,
    cache_stats: dict[str, object],
    warnings: list[str],
) -> None:
    """持久化本轮摘要，并输出 JSON 或人类可读报告。"""
    json_summary = build_json_summary(
        dry_run=args.dry_run,
        candidates=candidates,
        blocked_unresolved=blocked_unresolved,
        validation_failures=validation_failures,
        execution_summary=execution_summary,
        cache_stats=cache_stats,
        warnings=warnings,
        summary_file=config.cache.summary_file,
    )
    append_run_summary(config, json_summary)

    if args.json:
        print_json_summary(json_summary)
        return

    if args.dry_run:
        print_candidate_report(candidates, blocked_unresolved, dry_run=True)
    print_execution_summary(execution_summary, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
