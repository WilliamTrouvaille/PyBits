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
        description="根据当前目录中的 CLAUDE.md 创建 AGENTS.md。",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="当 AGENTS.md 已存在时先软删除旧文件再写入。",
    )
    return parser
