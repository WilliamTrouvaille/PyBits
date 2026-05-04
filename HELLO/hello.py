#!/usr/bin/env -S uv run --script
# requires-python = ">=3.12"
# dependencies = []


from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import platform
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger

from lib import (
    DEFAULT_PROMPT,
    DEFAULT_TAIL_CHARS,
    DEFAULT_TIMEOUT,
    SCHEMA_VERSION,
    command_display,
    config_summary,
    expand_path,
    get_version,
    missing_cli_result,
    normalize_claude_response,
    normalize_codex_response,
    run_process,
    setup_logger,
    summarize_auth_check,
    tail_text,
    utc_now,
    with_spinner,
)


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


def probe_claude(
    args: argparse.Namespace, workdir: Path, show_spinner: bool = False
) -> dict[str, Any]:
    """
    探测 Claude Code CLI 连通性

    Args:
        args: 命令行参数
        workdir: 工作目录
        show_spinner: 是否显示 spinner

    Returns:
        探测结果字典
    """
    service_started_at = utc_now()
    logger.debug("开始探测 Claude Code")

    cfg_path = expand_path(args.claude_settings)
    cfg = config_summary("claude", cfg_path)

    exe = shutil.which(args.claude_bin)
    if not exe:
        logger.warning(f"未找到 Claude Code CLI: {args.claude_bin}")
        return missing_cli_result("claude_code", args.claude_bin, cfg)

    if show_spinner:
        with with_spinner("Probing Claude Code...") as spinner:
            # 获取版本
            spinner.update("Getting Claude Code version...")
            version = get_version(exe, [["--version"], ["-v"]])

            # 认证检查
            auth: dict[str, Any] = {"checked": False, "ok": None}
            if not args.skip_auth_check:
                spinner.update("Checking Claude Code authentication...")
                auth_res = run_process(
                    [exe, "auth", "status"],
                    timeout_s=min(args.timeout, 30),
                    cwd=workdir,
                )
                auth = summarize_auth_check("claude", auth_res)

            # 构建命令
            cmd = [
                exe,
                "-p",
                args.prompt,
                "--output-format",
                "json",
                "--no-session-persistence",
                "--max-turns",
                "1",
                "--tools",
                "",
            ]

            if args.claude_setting_sources:
                cmd.extend(["--setting-sources", args.claude_setting_sources])

            if cfg_path.exists():
                cmd.extend(["--settings", str(cfg_path)])

            warnings: list[str] = []
            if not cfg_path.exists():
                warnings.append(f"Claude settings file does not exist: {cfg_path}")

            # 发送请求
            spinner.update("Sending request to Claude Code...")
            proc = run_process(cmd, timeout_s=args.timeout, cwd=workdir)

            # 解析响应
            spinner.update("Parsing Claude Code response...")
            response = normalize_claude_response(proc["stdout"])
    else:
        # 无 spinner 模式
        version = get_version(exe, [["--version"], ["-v"]])

        auth = {"checked": False, "ok": None}
        if not args.skip_auth_check:
            auth_res = run_process(
                [exe, "auth", "status"], timeout_s=min(args.timeout, 30), cwd=workdir
            )
            auth = summarize_auth_check("claude", auth_res)

        cmd = [
            exe,
            "-p",
            args.prompt,
            "--output-format",
            "json",
            "--no-session-persistence",
            "--max-turns",
            "1",
            "--tools",
            "",
        ]

        if args.claude_setting_sources:
            cmd.extend(["--setting-sources", args.claude_setting_sources])

        if cfg_path.exists():
            cmd.extend(["--settings", str(cfg_path)])

        warnings = []
        if not cfg_path.exists():
            warnings.append(f"Claude settings file does not exist: {cfg_path}")

        proc = run_process(cmd, timeout_s=args.timeout, cwd=workdir)
        response = normalize_claude_response(proc["stdout"])

    ok = proc["exit_code"] == 0 and not proc["timed_out"]
    logger.debug(f"Claude Code 探测完成，状态: {ok}")

    return {
        "service": "claude_code",
        "ok": ok,
        "status": "pass" if ok else ("timeout" if proc["timed_out"] else "failed"),
        "started_at": service_started_at,
        "finished_at": utc_now(),
        "cli": {
            "binary": args.claude_bin,
            "path": exe,
            "version": version,
        },
        "config": cfg,
        "auth": auth,
        "request": {
            "message": args.prompt,
            "transport": "official_cli",
            "header_handling": "delegated_to_claude_code_cli",
            "observable_header_sources": cfg.get("header_sources", []),
        },
        "response": response,
        "process": {
            "command": command_display(cmd),
            "exit_code": proc["exit_code"],
            "timed_out": proc["timed_out"],
            "duration_ms": proc["duration_ms"],
            "stdout_bytes": len(proc["stdout"].encode("utf-8", errors="replace")),
            "stderr_bytes": len(proc["stderr"].encode("utf-8", errors="replace")),
            "stderr_tail": tail_text(proc["stderr"], args.tail_chars),
            **(
                {"stdout_raw": proc["stdout"], "stderr_raw": proc["stderr"]}
                if args.include_raw
                else {}
            ),
        },
        "warnings": warnings,
    }


def probe_codex(
    args: argparse.Namespace, base_workdir: Path, show_spinner: bool = False
) -> dict[str, Any]:
    """
    探测 Codex CLI 连通性

    Args:
        args: 命令行参数
        base_workdir: 基础工作目录
        show_spinner: 是否显示 spinner

    Returns:
        探测结果字典
    """
    service_started_at = utc_now()
    logger.debug("开始探测 Codex")

    codex_home = expand_path(args.codex_home) if args.codex_home else None
    cfg_path = (
        expand_path(args.codex_config)
        if args.codex_config
        else (
            codex_home / "config.toml"
            if codex_home
            else expand_path("~/.codex/config.toml")
        )
    )

    cfg = config_summary("codex", cfg_path)

    exe = shutil.which(args.codex_bin)
    if not exe:
        logger.warning(f"未找到 Codex CLI: {args.codex_bin}")
        return missing_cli_result("codex", args.codex_bin, cfg)

    env = os.environ.copy()
    if codex_home:
        env["CODEX_HOME"] = str(codex_home)

    warnings: list[str] = []
    if not cfg_path.exists():
        warnings.append(f"Codex config file does not exist: {cfg_path}")

    if args.codex_config and codex_home:
        expected = codex_home / "config.toml"
        if cfg_path != expected:
            warnings.append(
                "A custom --codex-config is inspected by this script, but Codex CLI loads config from CODEX_HOME/config.toml. "
                f"Current CODEX_HOME/config.toml is: {expected}"
            )

    if show_spinner:
        with with_spinner("Probing Codex...") as spinner:
            # 获取版本
            spinner.update("Getting Codex version...")
            version = get_version(exe, [["--version"], ["-V"]])

            # 认证检查
            auth: dict[str, Any] = {"checked": False, "ok": None}
            if not args.skip_auth_check:
                spinner.update("Checking Codex authentication...")
                auth_res = run_process(
                    [exe, "login", "status"],
                    timeout_s=min(args.timeout, 30),
                    cwd=base_workdir,
                    env=env,
                )
                auth = summarize_auth_check("codex", auth_res)

            # 创建临时目录并执行请求
            with tempfile.TemporaryDirectory(
                prefix="codex-hello-probe-", ignore_cleanup_errors=True
            ) as td:
                temp_dir = Path(td)
                last_message_path = temp_dir / "last_message.txt"
                codex_cd = expand_path(args.codex_cd) if args.codex_cd else temp_dir

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

                if args.codex_profile:
                    cmd.extend(["--profile", args.codex_profile])

                cmd.append(args.prompt)

                # 发送请求
                spinner.update("Sending request to Codex...")
                proc = run_process(cmd, timeout_s=args.timeout, cwd=codex_cd, env=env)

                # 解析响应
                spinner.update("Parsing Codex response...")
                response = normalize_codex_response(proc["stdout"], last_message_path)
    else:
        # 无 spinner 模式
        version = get_version(exe, [["--version"], ["-V"]])

        auth = {"checked": False, "ok": None}
        if not args.skip_auth_check:
            auth_res = run_process(
                [exe, "login", "status"],
                timeout_s=min(args.timeout, 30),
                cwd=base_workdir,
                env=env,
            )
            auth = summarize_auth_check("codex", auth_res)

        with tempfile.TemporaryDirectory(
            prefix="codex-hello-probe-", ignore_cleanup_errors=True
        ) as td:
            temp_dir = Path(td)
            last_message_path = temp_dir / "last_message.txt"
            codex_cd = expand_path(args.codex_cd) if args.codex_cd else temp_dir

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

            if args.codex_profile:
                cmd.extend(["--profile", args.codex_profile])

            cmd.append(args.prompt)

            proc = run_process(cmd, timeout_s=args.timeout, cwd=codex_cd, env=env)
            response = normalize_codex_response(proc["stdout"], last_message_path)

    ok = proc["exit_code"] == 0 and not proc["timed_out"]
    logger.debug(f"Codex 探测完成，状态: {ok}")

    return {
        "service": "codex",
        "ok": ok,
        "status": "pass" if ok else ("timeout" if proc["timed_out"] else "failed"),
        "started_at": service_started_at,
        "finished_at": utc_now(),
        "cli": {
            "binary": args.codex_bin,
            "path": exe,
            "version": version,
        },
        "config": cfg,
        "auth": auth,
        "request": {
            "message": args.prompt,
            "transport": "official_cli",
            "header_handling": "delegated_to_codex_cli",
            "observable_header_sources": cfg.get("header_sources", []),
        },
        "response": response,
        "process": {
            "command": command_display(cmd),
            "exit_code": proc["exit_code"],
            "timed_out": proc["timed_out"],
            "duration_ms": proc["duration_ms"],
            "stdout_bytes": len(proc["stdout"].encode("utf-8", errors="replace")),
            "stderr_bytes": len(proc["stderr"].encode("utf-8", errors="replace")),
            "stdout_tail": tail_text(proc["stdout"], args.tail_chars),
            "stderr_tail": tail_text(proc["stderr"], args.tail_chars),
            **(
                {"stdout_raw": proc["stdout"], "stderr_raw": proc["stderr"]}
                if args.include_raw
                else {}
            ),
        },
        "warnings": warnings,
    }


def execute_parallel(
    services: list[str], probe_map: dict[str, Any]
) -> list[dict[str, Any]]:
    """
    并发执行探测

    Args:
        services: 服务名称列表
        probe_map: 服务名称到探测函数的映射

    Returns:
        探测结果列表，按服务顺序排序
    """
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(services)) as executor:
        future_to_service = {executor.submit(probe_map[s]): s for s in services}
        for future in concurrent.futures.as_completed(future_to_service):
            try:
                results.append(future.result())
            except Exception as e:
                service_name = future_to_service[future]
                logger.error(f"探测 {service_name} 失败: {e}")
                results.append(
                    {
                        "service": service_name,
                        "ok": False,
                        "status": "exception",
                        "error": str(e),
                    }
                )
    # 保持结果顺序
    results.sort(
        key=lambda x: services.index(
            "claude" if x["service"] == "claude_code" else x["service"]
        )
    )
    return results


def execute_sequential(
    services: list[str], probe_map: dict[str, Any]
) -> list[dict[str, Any]]:
    """
    串行执行探测

    Args:
        services: 服务名称列表
        probe_map: 服务名称到探测函数的映射

    Returns:
        探测结果列表
    """
    return [probe_map[s]() for s in services]


def build_parser() -> argparse.ArgumentParser:
    """
    构建命令行参数解析器

    Returns:
        配置好的 ArgumentParser 实例
    """
    p = argparse.ArgumentParser(
        description="Probe Claude Code and Codex CLI connectivity with a fixed hello prompt, then emit normalized JSON.",
    )

    p.add_argument(
        "-s",
        "--service",
        action="append",
        choices=["all", "claude", "cc", "claude_code", "codex"],
        help="Service to test. Can be repeated. Default: all.",
    )
    p.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help=f"Probe prompt. Default: {DEFAULT_PROMPT!r}",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout per service call, in seconds. Default: {DEFAULT_TIMEOUT}.",
    )

    # 并发控制：默认并发，--sequential 强制串行
    p.add_argument(
        "--sequential",
        action="store_true",
        help="Run selected probes sequentially. Default: parallel when multiple services are selected.",
    )

    # 日志控制
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging (INFO level to console).",
    )

    p.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    p.add_argument(
        "--jsonl",
        action="store_true",
        help="Emit one normalized JSON object per service.",
    )
    p.add_argument(
        "--include-raw",
        action="store_true",
        help="Include raw stdout/stderr. Avoid in normal logs.",
    )
    p.add_argument(
        "--tail-chars",
        type=int,
        default=DEFAULT_TAIL_CHARS,
        help=f"Tail length for stdout/stderr snippets. Default: {DEFAULT_TAIL_CHARS}.",
    )
    p.add_argument(
        "--always-exit-zero",
        action="store_true",
        help="Always exit with code 0 after printing JSON.",
    )
    p.add_argument(
        "--skip-auth-check",
        action="store_true",
        help="Skip `claude auth status` and `codex login status`.",
    )

    p.add_argument(
        "--claude-bin",
        default="claude",
        help="Claude Code executable name/path. Default: claude.",
    )
    p.add_argument(
        "--claude-settings",
        default="~/.claude/settings.json",
        help="Claude Code settings.json to inspect and pass via --settings when it exists.",
    )
    p.add_argument(
        "--claude-setting-sources",
        default="user",
        help="Value passed to Claude --setting-sources. Default: user. Use user,project,local if needed.",
    )

    p.add_argument(
        "--codex-bin",
        default="codex",
        help="Codex executable name/path. Default: codex.",
    )
    p.add_argument(
        "--codex-home",
        default=None,
        help="Optional CODEX_HOME. Codex normally loads config.toml from CODEX_HOME/config.toml.",
    )
    p.add_argument(
        "--codex-config",
        default=None,
        help="Codex config.toml path to inspect. If omitted, uses CODEX_HOME/config.toml or ~/.codex/config.toml.",
    )
    p.add_argument(
        "--codex-profile",
        default=None,
        help="Optional Codex profile name passed via --profile.",
    )
    p.add_argument(
        "--codex-cd",
        default=None,
        help="Optional working directory passed to codex exec --cd.",
    )

    return p


def main() -> int:
    """主入口函数"""
    args = build_parser().parse_args()
    services = expand_services(args.service)

    # 初始化日志
    setup_logger(args.verbose if hasattr(args, "verbose") else False)
    logger.info(f"HELLO 探测工具启动，服务: {services}")

    run_started_at = utc_now()

    # 是否显示 spinner
    show_spinner = (
        not (args.raw if hasattr(args, "raw") else False or args.jsonl)
        and sys.stderr.isatty()
    )

    with tempfile.TemporaryDirectory(
        prefix="ai-cli-hello-probe-", ignore_cleanup_errors=True
    ) as td:
        workdir = Path(td)

        probe_map = {
            "claude": lambda: probe_claude(args, workdir, show_spinner),
            "codex": lambda: probe_codex(args, workdir, show_spinner),
        }

        # 并发执行（默认）
        if not args.sequential and len(services) > 1:
            logger.info(f"并发探测 {len(services)} 个服务")
            if show_spinner:
                with with_spinner(f"Probing {len(services)} services in parallel..."):
                    results = execute_parallel(services, probe_map)
            else:
                results = execute_parallel(services, probe_map)
        # 串行执行
        else:
            logger.info(f"串行探测 {len(services)} 个服务")
            results = execute_sequential(services, probe_map)

    ok = all(item.get("ok") is True for item in results)

    envelope = {
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "status": "pass" if ok else "failed",
        "started_at": run_started_at,
        "finished_at": utc_now(),
        "prompt": args.prompt,
        "host": {
            "os": platform.platform(),
            "python": sys.version.split()[0],
            "executable": sys.executable,
            "cwd": str(Path.cwd()),
        },
        "services": results,
    }

    if args.jsonl:
        for item in results:
            print(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
    else:
        if args.pretty:
            print(json.dumps(envelope, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))

    if args.always_exit_zero:
        return 0

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
