"""类型定义"""

from __future__ import annotations

from typing import Any, TypedDict


class ProcessResult(TypedDict, total=False):
    """进程执行结果"""

    started_at: str
    finished_at: str
    duration_ms: int
    timed_out: bool
    exit_code: int | None
    stdout: str
    stderr: str


class AuthSummary(TypedDict, total=False):
    """认证状态摘要"""

    checked: bool
    ok: bool | None
    exit_code: int
    duration_ms: int
    timed_out: bool
    parsed: dict[str, Any]
    stdout_tail: str
    stderr_tail: str
    reason: str


class ServiceResult(TypedDict, total=False):
    """单个服务的探测结果"""

    service: str
    ok: bool
    status: str
    started_at: str
    finished_at: str
    cli: dict[str, Any]
    config: dict[str, Any]
    auth: AuthSummary
    request: dict[str, Any] | None
    response: dict[str, Any] | None
    process: dict[str, Any] | None
    warnings: list[str]
    error: str


class ProbeEnvelope(TypedDict, total=False):
    """完整探测结果的外层包装"""

    schema_version: str
    ok: bool
    status: str
    started_at: str
    finished_at: str
    prompt: str
    host: dict[str, Any]
    services: list[ServiceResult]
