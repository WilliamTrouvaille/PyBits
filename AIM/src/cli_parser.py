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
        description="只读索引 Claude Code 和 Codex 会话，生成脱敏候选记忆。",
    )
    parser.add_argument(
        "--claude-home",
        default="~/.claude",
        help="Claude Code 主目录，默认: ~/.claude。",
    )
    parser.add_argument(
        "--codex-home",
        default="~/.codex",
        help="Codex 主目录，默认: ~/.codex。",
    )
    parser.add_argument(
        "--since",
        help="只包含此日期或时间之后修改的文件，例如 2026-05-01。",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="最多写入的证据记录数，默认: 100。",
    )
    parser.add_argument(
        "--out-dir",
        help="输出目录，默认: .codex/aim/{timestamp}。",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 摘要。")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细日志。")
    return parser
