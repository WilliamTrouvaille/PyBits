"""
ATP 命令行参数解析器。
"""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """
    构建 ATP 命令行参数解析器。

    Returns:
        已配置的 argparse 参数解析器。
    """

    parser = argparse.ArgumentParser(
        prog="ATP",
        description="下载并转换 arXiv 论文的 LaTeX 源码",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  ATP 1911.11763                           # 输出到桌面
  ATP https://arxiv.org/abs/2303.08774     # 使用 URL
  ATP 1911.11763 --out-dir ./papers        # 自定义输出目录
  ATP 1911.11763 --json                    # 输出 manifest.json
  ATP 1911.11763 --force                   # 强制重新下载
  ATP 1911.11763 --proxy http://proxy:8080 # 使用代理
        """,
    )

    parser.add_argument(
        "arxiv_input",
        metavar="<arxiv-id-or-url>",
        help="arXiv ID 或 URL（如 1911.11763 或 https://arxiv.org/abs/1911.11763）",
    )

    parser.add_argument(
        "--out-dir",
        type=Path,
        help="输出目录（默认：系统桌面）",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 manifest.json 到 --out-dir 并打印到 stdout",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新下载，忽略缓存",
    )

    parser.add_argument(
        "--proxy",
        type=str,
        help="代理 URL（如 http://proxy:8080）",
    )

    parser.add_argument(
        "--no-comments",
        action="store_true",
        default=True,
        help="移除注释（默认启用）",
    )

    parser.add_argument(
        "--comments",
        action="store_true",
        help="保留注释（覆盖 --no-comments）",
    )

    parser.add_argument(
        "--figure-paths",
        action="store_true",
        default=True,
        help="提取图片并复制（默认启用）",
    )

    parser.add_argument(
        "--no-figure-paths",
        action="store_true",
        help="不提取图片（覆盖 --figure-paths）",
    )

    parser.add_argument(
        "--no-appendix",
        action="store_true",
        help="移除附录",
    )

    return parser
