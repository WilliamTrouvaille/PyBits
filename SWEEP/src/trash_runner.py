"""执行 SWEEP 配置的 trash 命令。

本模块只负责调用已解析的 trash 命令，不决定 fallback 目标，也不执行权限修复。
这些失败恢复策略集中在 `failure_handler` 中。
"""

from __future__ import annotations

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from .config import SweepConfig
from .models import CleanupCandidate, MovedPath, MoveFailure


@dataclass(frozen=True)
class TrashAvailability:
    """单次 SWEEP 进程中已解析的 trash 命令状态。"""

    command: tuple[str, ...] | None

    @property
    def available(self) -> bool:
        """
        判断启动阶段是否成功解析 trash 命令。

        Returns:
            trash 命令可用时返回 True；否则返回 False。
        """
        return self.command is not None


@dataclass(frozen=True)
class TrashRunResult:
    """一次 trash 执行阶段的结果。"""

    moved: tuple[MovedPath, ...]
    failures: tuple[MoveFailure, ...]
    trash_unavailable: bool = False


def move_with_trash(
    candidates: list[CleanupCandidate],
    config: SweepConfig,
    availability: TrashAvailability,
) -> TrashRunResult:
    """
    使用配置中的 trash 命令移动候选路径。

    Args:
        candidates: 本轮要移动的 Cleanup Candidate 列表。
        config: 已校验的 SWEEP 配置。
        availability: 启动时解析出的 trash 命令状态。

    Returns:
        trash 移动成功、失败和命令可用性状态。
    """
    if not candidates:
        return TrashRunResult(moved=(), failures=())
    if not availability.available:
        return TrashRunResult(
            moved=(),
            failures=tuple(
                MoveFailure(
                    candidate=candidate,
                    stage="trash",
                    code="trash_unavailable",
                    message="配置的 trash 命令不可用。",
                )
                for candidate in candidates
            ),
            trash_unavailable=True,
        )

    chunks = _chunk_candidates(candidates, config.trash.batch_size)
    moved: list[MovedPath] = []
    failures: list[MoveFailure] = []
    worker_count = min(config.trash.workers, len(chunks))
    if worker_count <= 1:
        for chunk in chunks:
            chunk_moved, chunk_failures = _move_chunk(chunk, config, availability)
            moved.extend(chunk_moved)
            failures.extend(chunk_failures)
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(_move_chunk, chunk, config, availability): chunk for chunk in chunks
            }
            for future in as_completed(futures):
                chunk_moved, chunk_failures = future.result()
                moved.extend(chunk_moved)
                failures.extend(chunk_failures)

    return TrashRunResult(moved=tuple(moved), failures=tuple(failures))


def move_single_with_trash(
    candidate: CleanupCandidate,
    config: SweepConfig,
    availability: TrashAvailability,
) -> TrashRunResult:
    """
    使用 trash 移动单个候选路径。

    该入口用于权限修复后的单路径重试，避免调用方重复构造列表。

    Args:
        candidate: 要重试移动的 Cleanup Candidate。
        config: 已校验的 SWEEP 配置。
        availability: 启动时解析出的 trash 命令状态。

    Returns:
        单候选 trash 执行结果。
    """
    return move_with_trash([candidate], config, availability)


def _move_chunk(
    candidates: list[CleanupCandidate],
    config: SweepConfig,
    availability: TrashAvailability,
) -> tuple[list[MovedPath], list[MoveFailure]]:
    if _run_trash_command(candidates, availability):
        return [MovedPath(candidate=candidate, method="trash") for candidate in candidates], []

    moved: list[MovedPath] = []
    failures: list[MoveFailure] = []
    for candidate in candidates:
        if _run_single_with_retries(candidate, config, availability):
            moved.append(MovedPath(candidate=candidate, method="trash"))
        else:
            failures.append(
                MoveFailure(
                    candidate=candidate,
                    stage="trash",
                    code="trash_failed",
                    message="trash 命令在批次拆分和重试后仍然失败。",
                )
            )
    return moved, failures


def _run_single_with_retries(
    candidate: CleanupCandidate,
    config: SweepConfig,
    availability: TrashAvailability,
) -> bool:
    attempts = config.trash.retries + 1
    for attempt in range(attempts):
        if _run_trash_command([candidate], availability):
            return True
        if attempt < attempts - 1 and config.trash.retry_backoff_seconds > 0:
            time.sleep(config.trash.retry_backoff_seconds)
    return False


def _run_trash_command(
    candidates: list[CleanupCandidate],
    availability: TrashAvailability,
) -> bool:
    if availability.command is None:
        return False
    args = [*availability.command, *(str(candidate.path) for candidate in candidates)]
    try:
        completed = subprocess.run(
            args,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _chunk_candidates(
    candidates: list[CleanupCandidate],
    batch_size: int,
) -> list[list[CleanupCandidate]]:
    return [
        candidates[index : index + batch_size] for index in range(0, len(candidates), batch_size)
    ]
