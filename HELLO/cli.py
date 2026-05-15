"""HELLO CLI 入口点"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from loguru import logger

from .src import hello
from .src.constants import DEFAULT_PROMPT, DEFAULT_TAIL_CHARS, DEFAULT_TIMEOUT
from .src.logger import setup_logger
from .src.probe_builder import expand_services
from .src.report import build_report
from .src.spinner import with_spinner


def build_parser() -> argparse.ArgumentParser:
    """
    构建命令行参数解析器

    Returns:
        配置好的 ArgumentParser 实例
    """
    p = argparse.ArgumentParser(
        description="Probe Claude Code and Codex CLI connectivity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s                          Probe both services with compact report (default)
  %(prog)s --raw                    Output raw JSON
  %(prog)s --pretty                 Output formatted JSON
  %(prog)s --service claude         Probe Claude Code only
  %(prog)s --timeout 60             Use 60-second timeout
""",
    )

    # 输出模式组（互斥）
    mode_group = p.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--raw",
        action="store_true",
        help="Output raw probe JSON (for piping and logging)",
    )
    mode_group.add_argument(
        "--compact",
        action="store_true",
        default=True,
        help="Output human-readable compact report (default)",
    )
    mode_group.add_argument(
        "--pretty",
        action="store_true",
        help="Output formatted JSON (for debugging)",
    )

    # 探测参数
    p.add_argument(
        "--service",
        action="append",
        choices=["claude", "codex", "both"],
        default=[],
        help="Service to probe (can be repeated). Default: both",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    p.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help=f"Probe prompt (default: {DEFAULT_PROMPT!r})",
    )
    p.add_argument(
        "--tail-chars",
        type=int,
        default=DEFAULT_TAIL_CHARS,
        help=f"Response preview character count (default: {DEFAULT_TAIL_CHARS})",
    )

    # 其他选项
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show verbose logs",
    )
    p.add_argument(
        "--always-exit-zero",
        action="store_true",
        help="Always exit with code 0",
    )
    p.add_argument(
        "--skip-auth-check",
        action="store_true",
        help="Skip authentication status checks",
    )

    # Claude Code 参数
    p.add_argument(
        "--claude-bin",
        default="claude",
        help="Claude Code executable name/path (default: claude)",
    )
    p.add_argument(
        "--claude-settings",
        default="~/.claude/settings.json",
        help="Claude Code settings.json path (default: ~/.claude/settings.json)",
    )
    p.add_argument(
        "--claude-setting-sources",
        default="user",
        help="Claude setting sources (default: user)",
    )

    # Codex 参数
    p.add_argument(
        "--codex-bin",
        default="codex",
        help="Codex executable name/path (default: codex)",
    )
    p.add_argument(
        "--codex-home",
        default=None,
        help="CODEX_HOME directory path",
    )
    p.add_argument(
        "--codex-config",
        default=None,
        help="Codex config.toml path",
    )
    p.add_argument(
        "--codex-profile",
        default=None,
        help="Codex profile name",
    )
    p.add_argument(
        "--codex-cd",
        default=None,
        help="Working directory for Codex exec",
    )

    return p


def main() -> int:
    """主入口函数"""
    args = build_parser().parse_args()

    # 初始化日志
    setup_logger(args.verbose)
    logger.info("HELLO 探测工具启动")

    # 标准化服务列表
    services = expand_services(args.service)
    logger.info(f"探测服务: {services}")

    # 确定输出模式
    output_mode = "compact"  # 默认
    if args.raw:
        output_mode = "raw"
    elif args.pretty:
        output_mode = "pretty"

    # 确定 spinner 可见性
    show_spinner = (output_mode == "compact") and sys.stderr.isatty()

    # 创建临时工作目录
    with tempfile.TemporaryDirectory(prefix="hello-probe-", ignore_cleanup_errors=True) as td:
        workdir = Path(td)

        # 执行探测（带或不带 spinner）
        if show_spinner:
            with with_spinner(f"Probing {len(services)} service(s)...") as spinner:
                envelope = hello.execute_parallel(
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
                spinner.succeed("探测完成")
        else:
            envelope = hello.execute_parallel(
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

    # 渲染输出
    if output_mode == "raw":
        print(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))
        exit_code = 0 if args.always_exit_zero else (0 if envelope["ok"] else 1)
    elif output_mode == "compact":
        report_text, ok = build_report(envelope, compact=True)
        print(report_text)
        exit_code = 0 if args.always_exit_zero else (0 if ok else 1)
    elif output_mode == "pretty":
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
        exit_code = 0 if args.always_exit_zero else (0 if envelope["ok"] else 1)
    else:
        # 不应该到达这里
        print(json.dumps(envelope, ensure_ascii=False))
        exit_code = 0 if args.always_exit_zero else (0 if envelope["ok"] else 1)

    logger.info(f"探测完成，退出码: {exit_code}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
