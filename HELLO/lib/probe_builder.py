"""探测命令构建和结果组装"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .schema import AuthSummary, ServiceResult
from .utils import command_display, tail_text


def expand_services(values: list[str] | None) -> list[str]:
    """
    展开服务别名为标准服务名称列表

    Args:
        values: 用户指定的服务名称列表

    Returns:
        标准化的服务名称列表 ["claude", "codex"]
    """
    if not values or "all" in values:
        return ["claude", "codex"]

    out: list[str] = []
    for value in values:
        if value in ("claude", "cc", "claude_code"):
            if "claude" not in out:
                out.append("claude")
        elif value == "codex":
            if "codex" not in out:
                out.append("codex")

    return out


def build_claude_command(
    exe: str,
    prompt: str,
    cfg_path: Path,
    claude_setting_sources: str = "user",
) -> tuple[list[str], list[str]]:
    """
    构建 Claude Code CLI 探测命令

    Args:
        exe: Claude Code 可执行文件路径
        prompt: 探测提示词
        cfg_path: Claude settings.json 文件路径
        claude_setting_sources: 设置源（user/project/local）

    Returns:
        (命令参数列表, 警告信息列表)
    """
    cmd = [
        exe,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--no-session-persistence",
        "--max-turns",
        "1",
        "--tools",
        "",
    ]

    if claude_setting_sources:
        cmd.extend(["--setting-sources", claude_setting_sources])

    warnings: list[str] = []
    if cfg_path.exists():
        cmd.extend(["--settings", str(cfg_path)])
    else:
        warnings.append(f"Claude settings file does not exist: {cfg_path}")

    return cmd, warnings


def build_codex_command(
    exe: str,
    prompt: str,
    codex_cd: Path,
    last_message_path: Path,
    codex_profile: str | None = None,
    codex_config: Path | None = None,
    codex_home: Path | None = None,
) -> tuple[list[str], list[str]]:
    """
    构建 Codex CLI 探测命令

    Args:
        exe: Codex 可执行文件路径
        prompt: 探测提示词
        codex_cd: Codex 执行目录
        last_message_path: last_message.txt 文件路径
        codex_profile: Codex profile 名称（可选）
        codex_config: Codex config.toml 路径（可选）
        codex_home: CODEX_HOME 路径（可选）

    Returns:
        (命令参数列表, 警告信息列表)
    """
    cmd = [
        exe,
        "exec",
        "--json",
        "--color",
        "never",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--output-last-message",
        str(last_message_path),
        "--cd",
        str(codex_cd),
    ]

    if codex_profile:
        cmd.extend(["--profile", codex_profile])

    cmd.append(prompt)

    warnings: list[str] = []

    if codex_config and codex_home:
        expected = codex_home / "config.toml"
        if codex_config != expected:
            warnings.append(
                "A custom --codex-config is inspected by this script, but Codex CLI loads config from CODEX_HOME/config.toml. "
                f"Current CODEX_HOME/config.toml is: {expected}"
            )

    return cmd, warnings


def build_process_result(
    proc: dict[str, Any],
    cmd: list[str],
    tail_chars: int,
    include_raw: bool = False,
) -> dict[str, Any]:
    """
    构建进程执行结果字典

    Args:
        proc: run_process 返回的进程结果
        cmd: 命令参数列表
        tail_chars: 输出尾部字符数
        include_raw: 是否包含原始输出

    Returns:
        进程结果字典
    """
    result = {
        "command": command_display(cmd),
        "exit_code": proc["exit_code"],
        "timed_out": proc["timed_out"],
        "duration_ms": proc["duration_ms"],
        "stdout_bytes": len(proc["stdout"].encode("utf-8", errors="replace")),
        "stderr_bytes": len(proc["stderr"].encode("utf-8", errors="replace")),
    }

    # 根据服务类型决定是否包含 stdout_tail
    # Claude Code: 只显示 stderr_tail（响应在 response 字段）
    # Codex: 显示 stdout_tail 和 stderr_tail
    if "stderr" in proc:
        result["stderr_tail"] = tail_text(proc["stderr"], tail_chars)

    if include_raw:
        result["stdout_raw"] = proc["stdout"]
        result["stderr_raw"] = proc["stderr"]

    return result


def assemble_service_result(
    service: str,
    ok: bool,
    status: str,
    started_at: str,
    finished_at: str,
    cli_info: dict[str, Any],
    config: dict[str, Any],
    auth: AuthSummary,
    request: dict[str, Any] | None,
    response: dict[str, Any] | None,
    process: dict[str, Any] | None,
    warnings: list[str],
    error: str | None = None,
) -> ServiceResult:
    """
    组装标准化的服务探测结果

    Args:
        service: 服务名称
        ok: 是否成功
        status: 状态（pass/failed/timeout/missing_cli/exception）
        started_at: 开始时间（ISO8601）
        finished_at: 结束时间（ISO8601）
        cli_info: CLI 信息字典
        config: 配置摘要字典
        auth: 认证摘要
        request: 请求信息字典
        response: 响应信息字典
        process: 进程执行结果
        warnings: 警告信息列表
        error: 错误信息（仅异常情况）

    Returns:
        标准化的服务探测结果
    """
    result: ServiceResult = {
        "service": service,
        "ok": ok,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "cli": cli_info,
        "config": config,
        "auth": auth,
        "request": request,
        "response": response,
        "process": process,
        "warnings": warnings,
    }

    if error:
        result["error"] = error

    return result
