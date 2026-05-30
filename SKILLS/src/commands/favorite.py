"""
SKILLS 常用 skill 命令处理器。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..favorite import add_favorite, list_favorites, remove_favorite
from ..utils import Settings


def handle_favorite_default(
    args: argparse.Namespace, settings: Settings, paths: dict[str, Path]
) -> int:
    """
    处理 `SKILLS favorite` 无子命令时的默认列表行为。

    Args:
        args: argparse 解析出的命名空间。
        settings: SKILLS 运行时配置。
        paths: 运行时派生路径集合。

    Returns:
        进程退出码。
    """
    return handle_favorite_list(args, settings, paths)


def handle_favorite_list(
    args: argparse.Namespace, settings: Settings, paths: dict[str, Path]
) -> int:
    """
    列出常用 skill。

    Args:
        args: argparse 解析出的命名空间。
        settings: SKILLS 运行时配置。
        paths: 运行时派生路径集合。

    Returns:
        进程退出码。
    """
    skills = list_favorites(paths["repos_cache_dir"])
    if not skills:
        print("常用 skills 为空。使用 `SKILLS favorite add <repo> <skill>` 添加。")
        return 0
    print(f"常用 skills（共 {len(skills)} 个）:")
    for name in skills:
        print(f"  {name}")
    return 0


def handle_favorite_add(
    args: argparse.Namespace, settings: Settings, paths: dict[str, Path]
) -> int:
    """
    从已注册仓库复制 skill 到常用列表。

    Args:
        args: argparse 解析出的命名空间。
        settings: SKILLS 运行时配置。
        paths: 运行时派生路径集合。

    Returns:
        进程退出码。
    """
    try:
        added = add_favorite(
            args.repository,
            args.skills,
            paths["repos_cache_dir"],
            paths["repos_json_path"],
            paths["repos_local_json_path"],
            settings.excluded_dirs,
            settings.default_scan_depth,
        )
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    print(f"已添加 {len(added)} 个常用 skill: {', '.join(added)}")
    return 0


def handle_favorite_remove(
    args: argparse.Namespace, settings: Settings, paths: dict[str, Path]
) -> int:
    """
    软删除常用列表中的指定 skill。

    Args:
        args: argparse 解析出的命名空间。
        settings: SKILLS 运行时配置。
        paths: 运行时派生路径集合。

    Returns:
        进程退出码。
    """
    if remove_favorite(args.skill, paths["repos_cache_dir"]):
        print(f"已移除常用 skill: {args.skill}")
        return 0
    print(f"常用 skills 中不存在: {args.skill}", file=sys.stderr)
    return 1
