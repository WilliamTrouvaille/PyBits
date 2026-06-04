"""构建 SWEEP 命令行参数解析器。"""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser(default_config: Path) -> argparse.ArgumentParser:
    """
    构建不含子命令的 SWEEP 参数解析器。

    Args:
        default_config: 默认 YAML 配置文件路径。

    Returns:
        配置好参数、帮助文本和默认值的 `argparse.ArgumentParser`。
    """
    parser = argparse.ArgumentParser(
        prog="SWEEP",
        description="扫描配置中的 Cleanup Scope，并安全移动过期临时文件。",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config,
        help=f"YAML 配置文件路径（默认：{default_config}）。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只校验并展示 Cleanup Candidate，不移动路径也不修复权限。",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 摘要。")
    parser.add_argument(
        "--workers",
        type=int,
        help="临时覆盖本次运行的 scan.workers。",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细日志。")
    return parser
