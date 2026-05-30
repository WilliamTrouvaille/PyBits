"""
SKILLS 仓库列表与扫描命令处理器。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import questionary
from loguru import logger
from questionary import Choice
from rich.console import Console
from rich.table import Table

from ..models import RepositoryType
from ..persistence import get_repository, load_repositories, remove_repository
from ..repository import scan_repository
from ..utils import Settings


def handle_list(args: argparse.Namespace, settings: Settings, paths: dict[str, Path]) -> int:
    """
    列出已注册仓库。

    Args:
        args: argparse 解析出的命名空间。
        settings: SKILLS 运行时配置。
        paths: 运行时派生路径集合。

    Returns:
        进程退出码。
    """
    repos = load_repositories(paths["repos_json_path"], paths["repos_local_json_path"])
    if not repos:
        print("未找到已注册仓库。")
        return 0

    console = Console()
    table = Table(show_header=True, header_style="bold")
    table.add_column("Type", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Source", style="dim")

    for repo in repos:
        source = (
            repo.url
            if repo.type == RepositoryType.GITHUB
            else ", ".join(repo.sources or [])
            if repo.type == RepositoryType.GITHUB_SKILLS
            else str(repo.path)
            if repo.path
            else "N/A"
        )
        table.add_row(repo.type.value, repo.name, source)

    console.print(table)
    return 0


def handle_remove(args: argparse.Namespace, settings: Settings, paths: dict[str, Path]) -> int:
    """
    移除一个已注册仓库记录。

    Args:
        args: argparse 解析出的命名空间。
        settings: SKILLS 运行时配置。
        paths: 运行时派生路径集合。

    Returns:
        进程退出码。
    """
    if remove_repository(args.name, paths["repos_json_path"], paths["repos_local_json_path"]):
        logger.info(f"[用户操作] 移除仓库: {args.name}")
        print(f"已移除仓库: {args.name}")
        return 0

    print(f"仓库不存在: {args.name}", file=sys.stderr)
    return 1


def handle_scan(args: argparse.Namespace, settings: Settings, paths: dict[str, Path]) -> int:
    """
    扫描已注册仓库中的可用 skill。

    Args:
        args: argparse 解析出的命名空间。
        settings: SKILLS 运行时配置。
        paths: 运行时派生路径集合。

    Returns:
        进程退出码。
    """
    repos = load_repositories(paths["repos_json_path"], paths["repos_local_json_path"])
    if not repos:
        print("未找到已注册仓库。")
        return 0

    if args.repository:
        # 用户指定仓库名时只扫描该仓库，避免交互式选择阻塞脚本调用。
        repo = get_repository(
            args.repository, paths["repos_json_path"], paths["repos_local_json_path"]
        )
        if not repo:
            print(f"仓库不存在: {args.repository}", file=sys.stderr)
            return 1
        repos_to_scan = [repo]
    else:
        if len(repos) == 1:
            # 只有一个仓库时无需交互选择。
            repos_to_scan = repos
        else:
            # 多仓库场景下提供对象 value，避免展示文案重复导致误选。
            repo_choices = [
                Choice(
                    title=f"{r.name} ({r.type.value}, {r.registered_at.strftime('%Y-%m-%d %H:%M:%S')})",
                    value=r,
                )
                for r in repos
            ]
            scan_all_label = "[扫描所有仓库]"
            repo_choices.append(Choice(title=scan_all_label, value=scan_all_label))

            selected_repo = questionary.select("选择要扫描的仓库:", choices=repo_choices).ask()

            if not selected_repo:
                logger.info("[用户操作] 取消扫描")
                print("扫描已取消。")
                return 1

            if selected_repo == scan_all_label:
                repos_to_scan = repos
                logger.info("[用户操作] 扫描所有仓库")
            else:
                repos_to_scan = [selected_repo]
                logger.info(f"[用户操作] 扫描仓库: {repos_to_scan[0].name}")

    console = Console()

    # 扫描结果可能很长，使用 pager 保持终端可读。
    with console.pager():
        for repo in repos_to_scan:
            skills = scan_repository(repo, args.depth, settings.excluded_dirs)
            logger.info(f"[用户操作] 扫描结果: {repo.name} - {len(skills)} 个 skill")

            table = Table(
                title=f"{repo.name}: {len(skills)} 个 skill", show_header=True, header_style="bold"
            )
            table.add_column("Skill Name", style="green", width=25)
            table.add_column("Description", style="dim")

            for skill in skills:
                table.add_row(skill.name, skill.description)

            console.print(table)
            if len(repos_to_scan) > 1:
                console.print()

    return 0
