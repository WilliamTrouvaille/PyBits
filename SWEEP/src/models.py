"""定义 SWEEP 清理规划和执行过程中的领域模型。

这些模型负责在模块之间传递状态，但不直接执行文件系统操作。保持模型纯粹可以
降低 scanner、planner、reporter 和 executor 之间的耦合。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class ScopeType(StrEnum):
    """配置中的顶层 Cleanup Scope 类型。"""

    SYSTEM_TEMP = "system_temp"
    DOWNLOADS = "downloads"
    PROJECT = "project"


class CandidateGroup(StrEnum):
    """执行前展示给用户看的候选分组。"""

    WHOLE_DIR = "whole_dir"
    PARTIAL_ITEMS = "partial_items"


class CandidateKind(StrEnum):
    """用于安全排序执行顺序的内部路径类型。"""

    FILE = "file"
    DIRECTORY = "directory"
    POST_CLEANUP_EMPTY_DIRECTORY = "post_cleanup_empty_directory"


@dataclass(frozen=True)
class CleanupCandidate:
    """当前已通过清理资格检查的实时路径。"""

    path: Path
    scope_type: ScopeType
    group: CandidateGroup
    kind: CandidateKind
    keep_days: int
    reason: str
    watch_dir: Path
    project_root: Path | None = None
    retry_unresolved: bool = False

    def key(self) -> str:
        """
        返回稳定的去重键，不要求路径当前存在。

        Returns:
            解析后的 POSIX 风格路径字符串。
        """
        return self.path.resolve(strict=False).as_posix()

    def for_retry(self) -> CleanupCandidate:
        """
        返回标记为 unresolved manifest 重试来源的候选副本。

        Returns:
            `retry_unresolved` 为 True 的 CleanupCandidate。
        """
        return CleanupCandidate(
            path=self.path,
            scope_type=self.scope_type,
            group=self.group,
            kind=self.kind,
            keep_days=self.keep_days,
            reason=self.reason,
            watch_dir=self.watch_dir,
            project_root=self.project_root,
            retry_unresolved=True,
        )

    def to_json(self) -> dict[str, Any]:
        """
        序列化候选，用于终端 JSON 输出和运行摘要。

        Returns:
            可 JSON 编码的候选详情字典。
        """
        data: dict[str, Any] = {
            "path": str(self.path),
            "scope_type": self.scope_type.value,
            "group": self.group.value,
            "kind": (
                CandidateKind.DIRECTORY.value
                if self.kind is CandidateKind.POST_CLEANUP_EMPTY_DIRECTORY
                else self.kind.value
            ),
            "deferred_empty_check": self.kind is CandidateKind.POST_CLEANUP_EMPTY_DIRECTORY,
            "keep_days": self.keep_days,
            "reason": self.reason,
            "watch_dir": str(self.watch_dir),
            "retry_unresolved": self.retry_unresolved,
        }
        if self.project_root is not None:
            data["project_root"] = str(self.project_root)
        return data


@dataclass(frozen=True)
class WatchDir:
    """从项目 Cleanup Scope 派生出的可复用扫描目标。"""

    path: Path
    kind: str

    def to_json(self) -> dict[str, str]:
        """
        序列化为 Watch Dir 缓存条目。

        Returns:
            包含路径和类型的缓存字典。
        """
        return {"path": str(self.path), "kind": self.kind}


@dataclass(frozen=True)
class ProjectEntry:
    """可缓存的项目根目录及其 Watch Dir 列表。"""

    root: Path
    markers: tuple[str, ...]
    watch_dirs: tuple[WatchDir, ...]

    def to_json(self) -> dict[str, Any]:
        """
        序列化为 `project_watch_dirs.json` 中的项目条目。

        Returns:
            可写入缓存 JSON 的项目描述。
        """
        return {
            "root": str(self.root),
            "markers": list(self.markers),
            "watch_dirs": [watch_dir.to_json() for watch_dir in self.watch_dirs],
        }


@dataclass
class CacheStats:
    """运行摘要中可观察的缓存行为统计。"""

    enabled: bool
    loaded: bool = False
    saved: bool = False
    cache_hits: int = 0
    refreshed_projects: int = 0
    full_refresh: bool = False
    reason: str = ""

    def to_json(self) -> dict[str, Any]:
        """
        序列化缓存诊断信息。

        Returns:
            可 JSON 编码的缓存统计字典。
        """
        return {
            "enabled": self.enabled,
            "loaded": self.loaded,
            "saved": self.saved,
            "cache_hits": self.cache_hits,
            "refreshed_projects": self.refreshed_projects,
            "full_refresh": self.full_refresh,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ScanResult:
    """合并 unresolved 记录前的一次扫描结果。"""

    candidates: tuple[CleanupCandidate, ...]
    project_entries: tuple[ProjectEntry, ...]
    cache_stats: CacheStats
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class UnresolvedRecord:
    """某个原始路径在 unresolved manifest 中的最新事件。"""

    original_path: Path
    event: str
    failure_code: str
    failure_stage: str
    message: str
    scope_type: ScopeType | None = None
    group: CandidateGroup | None = None
    project_root: Path | None = None


@dataclass(frozen=True)
class BlockedUnresolved:
    """当前规则下不应重试的 unresolved 路径。"""

    path: Path
    reason: str
    record: UnresolvedRecord

    def to_json(self) -> dict[str, str]:
        """
        序列化 blocked unresolved 详情。

        Returns:
            可 JSON 编码的 blocked unresolved 字典。
        """
        return {
            "path": str(self.path),
            "reason": self.reason,
            "failure_code": self.record.failure_code,
            "failure_stage": self.record.failure_stage,
        }


@dataclass(frozen=True)
class SkippedCandidate:
    """在重验或延迟空目录检查中被跳过的候选。"""

    candidate: CleanupCandidate
    reason: str

    def to_json(self) -> dict[str, Any]:
        """
        序列化跳过候选的详情。

        Returns:
            可 JSON 编码的跳过记录。
        """
        return {"candidate": self.candidate.to_json(), "reason": self.reason}


@dataclass(frozen=True)
class MoveFailure:
    """在某个执行阶段失败的候选。"""

    candidate: CleanupCandidate
    stage: str
    code: str
    message: str

    def to_json(self) -> dict[str, Any]:
        """
        序列化执行失败详情。

        Returns:
            可 JSON 编码的失败记录。
        """
        return {
            "candidate": self.candidate.to_json(),
            "stage": self.stage,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class MovedPath:
    """一次成功的 trash 或 soft-delete 移动。"""

    candidate: CleanupCandidate
    method: str
    destination: Path | None = None

    def to_json(self) -> dict[str, Any]:
        """
        序列化移动结果详情。

        Returns:
            可 JSON 编码的移动记录。
        """
        data = {"candidate": self.candidate.to_json(), "method": self.method}
        if self.destination is not None:
            data["destination"] = str(self.destination)
        return data


@dataclass
class ExecutionSummary:
    """单次 SWEEP 运行的可变执行结果累加器。"""

    moved: list[MovedPath] = field(default_factory=list)
    skipped: list[SkippedCandidate] = field(default_factory=list)
    unresolved: list[MoveFailure] = field(default_factory=list)
    repaired: list[Path] = field(default_factory=list)
    resolved_unresolved: list[CleanupCandidate] = field(default_factory=list)
    trash_unavailable: bool = False

    def to_json(self) -> dict[str, Any]:
        """
        序列化执行结果，用于人类可读报告和 JSON 报告。

        Returns:
            可 JSON 编码的执行摘要。
        """
        return {
            "moved": [item.to_json() for item in self.moved],
            "skipped": [item.to_json() for item in self.skipped],
            "unresolved": [item.to_json() for item in self.unresolved],
            "repaired": [str(path) for path in self.repaired],
            "resolved_unresolved": [candidate.to_json() for candidate in self.resolved_unresolved],
            "trash_unavailable": self.trash_unavailable,
        }
