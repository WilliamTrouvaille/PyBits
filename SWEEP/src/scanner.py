"""编排 SWEEP 顶层扫描流程。

`scanner.py` 协调基于缓存的项目发现和独立 Cleanup Scope walker。路径规则、
候选校验和树遍历放在更小的模块中，避免修改单个清理规则时必须改动本文件。
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from .cache import load_project_entries, save_project_entries
from .candidate_rules import dedupe_candidates
from .config import SweepConfig
from .models import CacheStats, CleanupCandidate, ProjectEntry, ScanResult, ScopeType
from .project_discovery import discover_project_entries
from .scope_scanner import ScopeScanOutput, scan_age_scope_files, scan_project

ScanJob = Callable[[], ScopeScanOutput]


def scan(config: SweepConfig, now: datetime | None = None) -> ScanResult:
    """
    扫描所有已配置的 Cleanup Scope，并返回当前候选。

    Args:
        config: 已校验的 SWEEP 配置。
        now: 可选的当前时间；测试可传入固定时间。

    Returns:
        包含候选、项目缓存条目、缓存统计和警告信息的扫描结果。
    """
    current_time = now or datetime.now()
    project_entries, cache_stats = _resolve_project_entries(config)

    outputs = _run_scan_jobs(
        _build_scan_jobs(config, project_entries, current_time),
        workers=config.scan.workers,
    )
    candidates: list[CleanupCandidate] = []
    warnings: list[str] = []
    for output in outputs:
        candidates.extend(output.candidates)
        warnings.extend(output.warnings)

    return ScanResult(
        candidates=tuple(dedupe_candidates(candidates)),
        project_entries=tuple(project_entries),
        cache_stats=cache_stats,
        warnings=tuple(warnings),
    )


def _resolve_project_entries(config: SweepConfig) -> tuple[list[ProjectEntry], CacheStats]:
    """从缓存或实时发现中解析项目条目。"""
    cached_entries, stats = load_project_entries(config)
    if cached_entries and not stats.full_refresh:
        return cached_entries, stats

    discovered = discover_project_entries(config)
    stats.refreshed_projects = len(discovered)
    stats.full_refresh = True
    save_project_entries(config, discovered, stats)
    return discovered, stats


def _build_scan_jobs(
    config: SweepConfig,
    project_entries: list[ProjectEntry],
    now: datetime,
) -> list[ScanJob]:
    """构建系统临时目录、下载目录和项目目录的扫描任务。"""
    jobs: list[ScanJob] = []
    for root in config.system_temp.dirs:
        jobs.append(
            lambda root=root: scan_age_scope_files(
                root=root,
                scope_type=ScopeType.SYSTEM_TEMP,
                keep_days=config.system_temp.keep_days,
                reason="system_temp_expired_file",
                config=config,
                now=now,
            )
        )
    for root in config.downloads.dirs:
        jobs.append(
            lambda root=root: scan_age_scope_files(
                root=root,
                scope_type=ScopeType.DOWNLOADS,
                keep_days=config.downloads.keep_days,
                reason="downloads_expired_file",
                config=config,
                now=now,
            )
        )
    for project_entry in project_entries:
        jobs.append(lambda project_entry=project_entry: scan_project(project_entry, config, now))
    return jobs


def _run_scan_jobs(jobs: list[ScanJob], workers: int) -> list[ScopeScanOutput]:
    """按配置并发度执行扫描任务。"""
    if not jobs:
        return []
    worker_count = min(workers, len(jobs))
    if worker_count <= 1:
        return [job() for job in jobs]

    results: list[ScopeScanOutput] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(job) for job in jobs]
        for future in as_completed(futures):
            results.append(future.result())
    return results
