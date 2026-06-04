"""执行 Claude Code 和 Codex CLI 的真实连通性探测。"""

from __future__ import annotations

import concurrent.futures
import platform
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from loguru import logger

from .auth_checker import missing_cli_result, summarize_auth_check
from .config_parser import config_summary
from .constants import DEFAULT_PROMPT, DEFAULT_TAIL_CHARS, DEFAULT_TIMEOUT, SCHEMA_VERSION
from .path_utils import expand_path
from .probe_builder import (
    assemble_service_result,
    build_claude_command,
    build_codex_command,
    build_process_result,
)
from .probe_env import build_codex_probe_env
from .process import get_version, run_process
from .response_normalizer import normalize_claude_response, normalize_codex_response
from .schema import AuthSummary, ProbeEnvelope, ServiceResult
from .time_utils import utc_now

ProbeTask = Callable[[], ServiceResult]


def _process_ok_and_status(proc: dict[str, Any]) -> tuple[bool, str]:
    """
    根据子进程结果生成 HELLO 的成功标记和状态字符串。

    Args:
        proc: run_process 返回的进程结果。

    Returns:
        二元组，第一项为是否成功，第二项为标准状态字符串。
    """
    ok = proc["exit_code"] == 0 and not proc["timed_out"]
    if ok:
        return True, "pass"
    return False, "timeout" if proc["timed_out"] else "failed"


def _exception_result(service_name: str, error: Exception) -> ServiceResult:
    """
    将未预期异常转换为标准服务结果。

    Args:
        service_name: 正在探测的服务名称。
        error: 探测过程中捕获的异常。

    Returns:
        状态为 `exception` 的服务结果。
    """
    now = utc_now()
    return assemble_service_result(
        service=service_name,
        ok=False,
        status="exception",
        started_at=now,
        finished_at=now,
        cli_info={},
        config={},
        auth={"checked": False, "ok": None},
        request=None,
        response=None,
        process=None,
        warnings=[],
        error=str(error),
    )


def _service_sort_key(service: ServiceResult, requested_services: list[str]) -> int:
    """
    按用户请求顺序对结果排序。

    Args:
        service: 单个服务探测结果。
        requested_services: 用户请求的标准服务名称列表。

    Returns:
        服务在请求列表中的索引；未知服务排在末尾。
    """
    service_name = "claude" if service["service"] == "claude_code" else service["service"]
    if service_name in requested_services:
        return requested_services.index(service_name)
    return len(requested_services)


def _collect_probe_results(
    services: list[str],
    probe_map: dict[str, ProbeTask],
) -> list[ServiceResult]:
    """
    并发执行每个服务的探测任务。

    Args:
        services: 待探测的标准服务名称列表。
        probe_map: 服务名称到探测函数的映射。

    Returns:
        每个服务对应的探测结果；异常会转换为标准失败结果。
    """
    results: list[ServiceResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(services)) as executor:
        future_to_service = {executor.submit(probe_map[service]): service for service in services}
        for future in concurrent.futures.as_completed(future_to_service):
            service_name = future_to_service[future]
            try:
                results.append(future.result())
            except Exception as exc:
                logger.error(f"探测 {service_name} 失败: {exc}")
                results.append(_exception_result(service_name, exc))
    return results


def _host_info() -> dict[str, str]:
    """
    生成本次探测运行环境摘要。

    Returns:
        包含操作系统、Python 版本、解释器和当前目录的字典。
    """
    return {
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "cwd": str(Path.cwd()),
    }


def probe_claude(
    timeout: float = DEFAULT_TIMEOUT,
    prompt: str = DEFAULT_PROMPT,
    tail_chars: int = DEFAULT_TAIL_CHARS,
    verbose: bool = False,
    claude_bin: str = "claude",
    claude_settings: str = "~/.claude/settings.json",
    claude_setting_sources: str = "user",
    skip_auth_check: bool = False,
    workdir: Path | None = None,
) -> ServiceResult:
    """
    探测 Claude Code CLI 连通性。

    Args:
        timeout: 超时时间（秒）。
        prompt: 探测提示词。
        tail_chars: 输出尾部字符数。
        verbose: 是否启用详细日志。
        claude_bin: Claude Code 可执行文件名。
        claude_settings: Claude settings.json 文件路径。
        claude_setting_sources: 设置源。
        skip_auth_check: 是否跳过认证检查。
        workdir: 工作目录。

    Returns:
        探测结果字典。
    """
    service_started_at = utc_now()
    logger.debug("开始探测 Claude Code")

    cfg_path = expand_path(claude_settings)
    cfg = config_summary("claude", cfg_path)

    exe = shutil.which(claude_bin)
    if not exe:
        logger.warning(f"未找到 Claude Code CLI: {claude_bin}")
        return missing_cli_result("claude_code", claude_bin, cfg)

    version = get_version(exe, [["--version"], ["-v"]])

    auth: AuthSummary = {"checked": False, "ok": None}
    if not skip_auth_check:
        auth_res = run_process(
            [exe, "auth", "status"],
            timeout_s=min(timeout, 30),
            cwd=workdir,
        )
        auth = summarize_auth_check("claude", auth_res)

    cmd, warnings = build_claude_command(
        exe=exe,
        prompt=prompt,
        cfg_path=cfg_path,
        claude_setting_sources=claude_setting_sources,
    )

    proc = run_process(cmd, timeout_s=timeout, cwd=workdir)

    response = normalize_claude_response(proc["stdout"])

    ok, status = _process_ok_and_status(proc)
    logger.debug(f"Claude Code 探测完成，状态: {ok}")

    process = build_process_result(proc, cmd, tail_chars, include_raw=False)

    return assemble_service_result(
        service="claude_code",
        ok=ok,
        status=status,
        started_at=service_started_at,
        finished_at=utc_now(),
        cli_info={
            "binary": claude_bin,
            "path": exe,
            "version": version,
        },
        config=cfg,
        auth=auth,
        request={
            "message": prompt,
            "transport": "official_cli",
            "header_handling": "delegated_to_claude_code_cli",
            "observable_header_sources": cfg.get("header_sources", []),
        },
        response=response,
        process=process,
        warnings=warnings,
    )


def probe_codex(
    timeout: float = DEFAULT_TIMEOUT,
    prompt: str = DEFAULT_PROMPT,
    tail_chars: int = DEFAULT_TAIL_CHARS,
    verbose: bool = False,
    codex_bin: str = "codex",
    codex_home: str | None = None,
    codex_config: str | None = None,
    codex_profile: str | None = None,
    codex_cd: str | None = None,
    skip_auth_check: bool = False,
    base_workdir: Path | None = None,
) -> ServiceResult:
    """
    探测 Codex CLI 连通性。

    Args:
        timeout: 超时时间（秒）。
        prompt: 探测提示词。
        tail_chars: 输出尾部字符数。
        verbose: 是否启用详细日志。
        codex_bin: Codex 可执行文件名。
        codex_home: CODEX_HOME 路径。
        codex_config: Codex config.toml 路径。
        codex_profile: Codex profile 名称。
        codex_cd: Codex 执行目录。
        skip_auth_check: 是否跳过认证检查。
        base_workdir: 基础工作目录。

    Returns:
        探测结果字典。
    """
    service_started_at = utc_now()
    logger.debug("开始探测 Codex")

    codex_home_path = expand_path(codex_home) if codex_home else None
    cfg_path = (
        expand_path(codex_config)
        if codex_config
        else (
            codex_home_path / "config.toml"
            if codex_home_path
            else expand_path("~/.codex/config.toml")
        )
    )

    cfg = config_summary("codex", cfg_path)

    env, checked_dirs = build_codex_probe_env()
    if codex_home_path:
        env["CODEX_HOME"] = str(codex_home_path)

    exe = shutil.which(codex_bin, path=env.get("PATH"))
    if not exe:
        logger.warning(f"未找到 Codex CLI: {codex_bin}")
        return missing_cli_result(
            "codex",
            codex_bin,
            cfg,
            search_path=env.get("PATH", ""),
            checked_dirs=checked_dirs,
        )

    warnings: list[str] = []
    if not cfg_path.exists():
        warnings.append(f"Codex config file does not exist: {cfg_path}")

    version = get_version(exe, [["--version"], ["-V"]], env=env)

    auth: AuthSummary = {"checked": False, "ok": None}
    if not skip_auth_check:
        auth_res = run_process(
            [exe, "login", "status"],
            timeout_s=min(timeout, 30),
            cwd=base_workdir,
            env=env,
        )
        auth = summarize_auth_check("codex", auth_res)

    with tempfile.TemporaryDirectory(prefix="codex-hello-probe-", ignore_cleanup_errors=True) as td:
        temp_dir = Path(td)
        last_message_path = temp_dir / "last_message.txt"
        codex_cd_path = expand_path(codex_cd) if codex_cd else temp_dir

        cmd, cmd_warnings = build_codex_command(
            exe=exe,
            prompt=prompt,
            codex_cd=codex_cd_path,
            last_message_path=last_message_path,
            codex_profile=codex_profile,
            codex_config=cfg_path if codex_config else None,
            codex_home=codex_home_path,
        )
        warnings.extend(cmd_warnings)

        proc = run_process(cmd, timeout_s=timeout, cwd=codex_cd_path, env=env)

        response = normalize_codex_response(proc["stdout"], last_message_path)

    ok, status = _process_ok_and_status(proc)
    logger.debug(f"Codex 探测完成，状态: {ok}")

    process = build_process_result(proc, cmd, tail_chars, include_raw=False)

    return assemble_service_result(
        service="codex",
        ok=ok,
        status=status,
        started_at=service_started_at,
        finished_at=utc_now(),
        cli_info={
            "binary": codex_bin,
            "path": exe,
            "version": version,
        },
        config=cfg,
        auth=auth,
        request={
            "message": prompt,
            "transport": "official_cli",
            "header_handling": "delegated_to_codex_cli",
            "observable_header_sources": cfg.get("header_sources", []),
        },
        response=response,
        process=process,
        warnings=warnings,
    )


def execute_parallel(
    services: list[str],
    timeout: float = DEFAULT_TIMEOUT,
    prompt: str = DEFAULT_PROMPT,
    tail_chars: int = DEFAULT_TAIL_CHARS,
    verbose: bool = False,
    claude_bin: str = "claude",
    claude_settings: str = "~/.claude/settings.json",
    claude_setting_sources: str = "user",
    codex_bin: str = "codex",
    codex_home: str | None = None,
    codex_config: str | None = None,
    codex_profile: str | None = None,
    codex_cd: str | None = None,
    skip_auth_check: bool = False,
    workdir: Path | None = None,
) -> ProbeEnvelope:
    """
    并发执行多个服务的探测。

    Args:
        services: 服务名称列表，例如 ["claude", "codex"]。
        timeout: 超时时间（秒）。
        prompt: 探测提示词。
        tail_chars: 输出尾部字符数。
        verbose: 是否启用详细日志。
        claude_bin: Claude Code 可执行文件名。
        claude_settings: Claude settings.json 文件路径。
        claude_setting_sources: Claude 设置源。
        codex_bin: Codex 可执行文件名。
        codex_home: CODEX_HOME 路径。
        codex_config: Codex config.toml 路径。
        codex_profile: Codex profile 名称。
        codex_cd: Codex 执行目录。
        skip_auth_check: 是否跳过认证检查。
        workdir: 工作目录。

    Returns:
        探测结果包装字典。
    """
    run_started_at = utc_now()
    logger.info(f"并发探测 {len(services)} 个服务")

    probe_map: dict[str, ProbeTask] = {
        "claude": lambda: probe_claude(
            timeout=timeout,
            prompt=prompt,
            tail_chars=tail_chars,
            verbose=verbose,
            claude_bin=claude_bin,
            claude_settings=claude_settings,
            claude_setting_sources=claude_setting_sources,
            skip_auth_check=skip_auth_check,
            workdir=workdir,
        ),
        "codex": lambda: probe_codex(
            timeout=timeout,
            prompt=prompt,
            tail_chars=tail_chars,
            verbose=verbose,
            codex_bin=codex_bin,
            codex_home=codex_home,
            codex_config=codex_config,
            codex_profile=codex_profile,
            codex_cd=codex_cd,
            skip_auth_check=skip_auth_check,
            base_workdir=workdir,
        ),
    }

    results = _collect_probe_results(services, probe_map)
    results.sort(key=lambda item: _service_sort_key(item, services))

    ok = all(item.get("ok") is True for item in results)

    envelope: ProbeEnvelope = {
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "status": "pass" if ok else "failed",
        "started_at": run_started_at,
        "finished_at": utc_now(),
        "prompt": prompt,
        "host": _host_info(),
        "services": results,
    }

    return envelope
