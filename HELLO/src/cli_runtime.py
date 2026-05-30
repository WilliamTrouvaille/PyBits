"""
HELLO 命令运行期辅助函数。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import hello
from .probe_builder import expand_services
from .report import build_report
from .spinner import with_spinner


def resolve_services(args: argparse.Namespace, known_aliases: set[str]) -> list[str]:
    """
    校验并展开命令行传入的服务别名。

    Args:
        args: argparse 解析出的命名空间。
        known_aliases: 允许使用的服务别名集合。

    Returns:
        展开后的服务名称列表。

    Raises:
        ValueError: 用户传入了未知服务别名。
    """
    service_values = [*args.service, *args.service_aliases]
    unknown_services = sorted(set(service_values) - known_aliases)
    if unknown_services:
        raise ValueError(f"unknown service alias: {', '.join(unknown_services)}")
    return expand_services(service_values)


def output_mode(args: argparse.Namespace) -> str:
    """
    根据命令行参数解析输出模式。

    Args:
        args: argparse 解析出的命名空间。

    Returns:
        输出模式，可能为 `raw`、`pretty` 或 `compact`。
    """
    if args.raw:
        return "raw"
    if args.pretty:
        return "pretty"
    return "compact"


def execute_probe(args: argparse.Namespace, services: list[str], workdir: Path) -> dict[str, Any]:
    """
    执行一次 HELLO 探测，必要时包装终端 spinner。

    Args:
        args: argparse 解析出的命名空间。
        services: 待探测的服务名称列表。
        workdir: 本次探测使用的临时工作目录。

    Returns:
        探测结果 envelope。
    """
    mode = output_mode(args)
    show_spinner = mode == "compact" and sys.stderr.isatty()
    if show_spinner:
        with with_spinner(f"Probing {len(services)} service(s)...") as spinner:
            envelope = _execute_parallel(args, services, workdir)
            spinner.succeed("探测完成")
            return envelope
    return _execute_parallel(args, services, workdir)


def print_result(envelope: dict[str, Any], args: argparse.Namespace) -> int:
    """
    按请求格式打印探测结果并计算退出码。

    Args:
        envelope: 探测结果 envelope。
        args: argparse 解析出的命名空间。

    Returns:
        进程退出码。
    """
    mode = output_mode(args)
    if mode == "raw":
        print(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))
        return 0 if args.always_exit_zero else (0 if envelope["ok"] else 1)
    if mode == "compact":
        report_text, ok = build_report(envelope, compact=True)
        print(report_text)
        return 0 if args.always_exit_zero else (0 if ok else 1)
    if mode == "pretty":
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
        return 0 if args.always_exit_zero else (0 if envelope["ok"] else 1)

    raise AssertionError(f"unexpected output mode: {mode}")


def _execute_parallel(
    args: argparse.Namespace, services: list[str], workdir: Path
) -> dict[str, Any]:
    """
    将 CLI 参数转发给 HELLO 并行探测引擎。

    Args:
        args: argparse 解析出的命名空间。
        services: 待探测的服务名称列表。
        workdir: 本次探测使用的临时工作目录。

    Returns:
        并行探测结果 envelope。
    """
    return hello.execute_parallel(
        services=services,
        timeout=args.timeout,
        prompt=args.prompt,
        tail_chars=args.tail_chars,
        verbose=args.verbose,
        claude_bin=args.claude_bin,
        claude_settings=args.claude_settings,
        claude_setting_sources=args.claude_setting_sources,
        codex_bin=args.codex_bin,
        codex_home=args.codex_home,
        codex_config=args.codex_config,
        codex_profile=args.codex_profile,
        codex_cd=args.codex_cd,
        skip_auth_check=args.skip_auth_check,
        workdir=workdir,
    )
