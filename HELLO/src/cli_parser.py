"""
HELLO 命令行参数解析器。
"""

from __future__ import annotations

import argparse

from .constants import DEFAULT_PROMPT, DEFAULT_TAIL_CHARS, DEFAULT_TIMEOUT

SERVICE_ALIASES = {"all", "both", "cc", "claude", "claude_code", "codex"}


def build_parser() -> argparse.ArgumentParser:
    """
    构建 HELLO 命令行参数解析器。

    Returns:
        已配置的 argparse 参数解析器。
    """
    parser = argparse.ArgumentParser(
        description="Probe Claude Code and Codex CLI connectivity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s                          Probe both services with compact report (default)
  %(prog)s --raw                    Output raw JSON
  %(prog)s --pretty                 Output formatted JSON (for debugging)
  %(prog)s --service claude         Probe Claude Code only
  %(prog)s cc                       Probe Claude Code using service alias
  %(prog)s --timeout 60             Use 60-second timeout
""",
    )

    mode_group = parser.add_mutually_exclusive_group()
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

    parser.add_argument(
        "--service",
        action="append",
        choices=["claude", "codex", "both", "all"],
        default=[],
        help="Service to probe (can be repeated). Default: both",
    )
    parser.add_argument(
        "service_aliases",
        nargs="*",
        help="Optional service aliases: claude, cc, claude_code, codex, both, all",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help=f"Probe prompt (default: {DEFAULT_PROMPT!r})",
    )
    parser.add_argument(
        "--tail-chars",
        type=int,
        default=DEFAULT_TAIL_CHARS,
        help=f"Response preview character count (default: {DEFAULT_TAIL_CHARS})",
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Show verbose logs")
    parser.add_argument(
        "--always-exit-zero",
        action="store_true",
        help="Always exit with code 0",
    )
    parser.add_argument(
        "--skip-auth-check",
        action="store_true",
        help="Skip authentication status checks",
    )

    parser.add_argument(
        "--claude-bin",
        default="claude",
        help="Claude Code executable name/path (default: claude)",
    )
    parser.add_argument(
        "--claude-settings",
        default="~/.claude/settings.json",
        help="Claude Code settings.json path (default: ~/.claude/settings.json)",
    )
    parser.add_argument(
        "--claude-setting-sources",
        default="user",
        help="Claude setting sources (default: user)",
    )

    parser.add_argument(
        "--codex-bin",
        default="codex",
        help="Codex executable name/path (default: codex)",
    )
    parser.add_argument("--codex-home", default=None, help="CODEX_HOME directory path")
    parser.add_argument("--codex-config", default=None, help="Codex config.toml path")
    parser.add_argument("--codex-profile", default=None, help="Codex profile name")
    parser.add_argument(
        "--codex-cd",
        default=None,
        help="Working directory for Codex exec",
    )

    return parser
