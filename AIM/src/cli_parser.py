"""
AIM 命令行参数解析器。
"""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """
    构建 AIM 命令行参数解析器。

    Returns:
        已配置的 argparse 参数解析器。
    """

    parser = argparse.ArgumentParser(
        prog="AIM",
        description="Index Claude Code and Codex sessions into redacted candidate memories.",
    )
    parser.add_argument(
        "--claude-home",
        default="~/.claude",
        help="Claude Code home directory (default: ~/.claude).",
    )
    parser.add_argument(
        "--codex-home",
        default="~/.codex",
        help="Codex home directory (default: ~/.codex).",
    )
    parser.add_argument(
        "--since",
        help="Only include files modified after this date/time, e.g. 2026-05-01.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of evidence records to write (default: 100).",
    )
    parser.add_argument(
        "--out-dir",
        help="Output directory. Defaults to .codex/aim/{timestamp}.",
    )
    parser.add_argument("--json", action="store_true", help="Print a JSON summary.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show verbose logs.")
    return parser
