"""认证检查"""

from __future__ import annotations

from typing import Any

from .json_utils import parse_json_maybe
from .security import redact
from .text_utils import tail_text


def summarize_auth_check(name: str, res: dict[str, Any]) -> dict[str, Any]:
    """
    汇总认证检查结果

    Args:
        name: 服务名称（"claude" 或 "codex"）
        res: run_process 返回的执行结果字典

    Returns:
        认证检查摘要字典，包含以下字段：
        - checked: 是否执行了检查（True）
        - ok: 认证是否成功（基于退出码和超时状态）
        - exit_code: 退出码
        - duration_ms: 执行耗时（毫秒）
        - timed_out: 是否超时
        - parsed: 解析后的 JSON 输出（如果可解析，已脱敏）
        - stdout_tail: 标准输出尾部（如果无法解析为 JSON）
        - stderr_tail: 标准错误输出尾部（如果无法解析为 JSON）
    """
    parsed = parse_json_maybe(res["stdout"])

    summary: dict[str, Any] = {
        "checked": True,
        "ok": res["exit_code"] == 0 and not res["timed_out"],
        "exit_code": res["exit_code"],
        "duration_ms": res["duration_ms"],
        "timed_out": res["timed_out"],
    }

    if parsed is not None:
        # 成功解析为 JSON，脱敏后保存
        summary["parsed"] = redact(parsed)
    else:
        # 无法解析为 JSON，保存输出尾部
        summary["stdout_tail"] = tail_text(res["stdout"], 1000)
        summary["stderr_tail"] = tail_text(res["stderr"], 1000)

    return summary


def missing_cli_result(
    service: str,
    binary_name: str,
    cfg: dict[str, Any],
    *,
    search_path: str | None = None,
    checked_dirs: list[str] | None = None,
) -> dict[str, Any]:
    """
    生成 CLI 工具缺失时的标准化结果

    Args:
        service: 服务名称（"claude_code" 或 "codex"）
        binary_name: 二进制文件名
        cfg: 配置摘要字典
        search_path: 用于发现 CLI 的 PATH
        checked_dirs: 额外检查过的候选目录

    Returns:
        标准化的探测结果字典，状态为 "missing_cli"
    """
    cli_info: dict[str, Any] = {
        "binary": binary_name,
        "path": None,
        "version": None,
    }
    if search_path is not None:
        cli_info["search_path"] = search_path
    if checked_dirs is not None:
        cli_info["checked_dirs"] = checked_dirs

    warnings = [f"Cannot find `{binary_name}` in PATH."]
    if search_path is not None:
        warnings.append(f"Discovery PATH: {search_path or '(empty)'}")
    if checked_dirs:
        warnings.append(f"Fallback directories checked: {', '.join(checked_dirs)}")

    return {
        "service": service,
        "ok": False,
        "status": "missing_cli",
        "cli": cli_info,
        "config": cfg,
        "auth": {
            "checked": False,
            "ok": None,
            "reason": "cli_not_found",
        },
        "request": None,
        "response": None,
        "process": None,
        "warnings": warnings,
    }
