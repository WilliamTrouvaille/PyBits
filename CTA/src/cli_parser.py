"""
CTA 命令行参数解析器。
"""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """
    构建 CTA 命令行参数解析器。

    Returns:
        已配置的 argparse 参数解析器。
    """

    parser = argparse.ArgumentParser(
        prog="CTA",
        description="Create AGENTS.md from CLAUDE.md in the current directory.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite AGENTS.md if it already exists.",
    )
    return parser
