"""读写 append-only unresolved manifest。

manifest 是审计日志，不是可变数据库。本模块集中处理 JSONL 解析和追加写入，
避免 planner 与 failure_handler 为共享重试状态而互相依赖。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import SweepConfig
from .models import CandidateGroup, CleanupCandidate, MoveFailure, ScopeType, UnresolvedRecord


def load_latest_unresolved(config: SweepConfig) -> list[UnresolvedRecord]:
    """
    读取每个路径最新的 unresolved 事件，不修改审计日志。

    Args:
        config: 已校验的 SWEEP 配置。

    Returns:
        仍处于 unresolved 状态的最新记录列表。
    """
    manifest = config.failure_policy.unresolved_manifest
    if not manifest.is_file():
        return []

    latest: dict[str, UnresolvedRecord] = {}
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    for line in lines:
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        record = _parse_unresolved_record(raw)
        if record is not None:
            latest[record.original_path.as_posix()] = record

    return [record for _, record in sorted(latest.items()) if record.event == "unresolved"]


def append_unresolved_event(
    config: SweepConfig,
    failure: MoveFailure,
    *,
    event: str = "unresolved",
) -> None:
    """
    追加 unresolved 或 resolved 审计事件，不改写旧记录。

    Args:
        config: 已校验的 SWEEP 配置。
        failure: 需要写入 manifest 的失败或 resolved 事件载体。
        event: 写入的事件类型，默认是 `unresolved`。
    """
    manifest = config.failure_policy.unresolved_manifest
    manifest.parent.mkdir(parents=True, exist_ok=True)
    candidate = failure.candidate
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        "original_path": str(candidate.path),
        "failure_stage": failure.stage,
        "failure_code": failure.code,
        "message": failure.message,
        "scope_type": candidate.scope_type.value,
        "group": candidate.group.value,
        "project_root": str(candidate.project_root) if candidate.project_root else None,
    }
    with manifest.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        file.write("\n")


def append_resolved_event(config: SweepConfig, candidate: CleanupCandidate, method: str) -> None:
    """
    为成功移动的重试候选追加 resolved 事件。

    Args:
        config: 已校验的 SWEEP 配置。
        candidate: 已成功处理的 retry_unresolved 候选。
        method: 成功处理该候选的方法。
    """
    append_unresolved_event(
        config,
        MoveFailure(
            candidate=candidate,
            stage="resolved",
            code="resolved",
            message=f"已通过 {method} 处理完成。",
        ),
        event="resolved",
    )


def _parse_unresolved_record(raw: dict[str, Any]) -> UnresolvedRecord | None:
    """从 JSONL 字典中解析 unresolved 记录，格式不合法时返回 None。"""
    original_path = raw.get("original_path")
    event = raw.get("event")
    failure_code = raw.get("failure_code")
    failure_stage = raw.get("failure_stage")
    message = raw.get("message", "")
    if not all(
        isinstance(item, str) for item in (original_path, event, failure_code, failure_stage)
    ):
        return None

    scope_type = _parse_scope(raw.get("scope_type"))
    group = _parse_group(raw.get("group"))
    project_root = raw.get("project_root")
    return UnresolvedRecord(
        original_path=Path(original_path),
        event=event,
        failure_code=failure_code,
        failure_stage=failure_stage,
        message=str(message),
        scope_type=scope_type,
        group=group,
        project_root=Path(project_root) if isinstance(project_root, str) else None,
    )


def _parse_scope(raw_scope: Any) -> ScopeType | None:
    """解析 scope_type 字段，未知值返回 None。"""
    if not isinstance(raw_scope, str):
        return None
    try:
        return ScopeType(raw_scope)
    except ValueError:
        return None


def _parse_group(raw_group: Any) -> CandidateGroup | None:
    """解析 group 字段，未知值返回 None。"""
    if not isinstance(raw_group, str):
        return None
    try:
        return CandidateGroup(raw_group)
    except ValueError:
        return None
