"""
SKILLS 最近安装记录命令处理器。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..recent import load_recent_refs
from ..utils import Settings


def handle_recent(args: argparse.Namespace, settings: Settings, paths: dict[str, Path]) -> int:
    """
    展示最近安装的 skill 名称列表。

    Args:
        args: argparse 解析出的命名空间。
        settings: SKILLS 运行时配置。
        paths: 运行时派生路径集合。

    Returns:
        进程退出码。
    """
    refs = load_recent_refs(paths["recent_installs_path"])
    if not refs:
        print("暂无最近安装记录。")
        return 0
    print(f"最近安装的 skills（最新在前，共 {len(refs)} 个）:")
    for ref in refs:
        repository = f" ({ref.repository_name})" if ref.repository_name else ""
        print(f"  {ref.name}{repository}")
    return 0
