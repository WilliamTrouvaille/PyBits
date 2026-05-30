"""
SKILLS 命令行参数解析器。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .commands.favorite import (
    handle_favorite_add,
    handle_favorite_default,
    handle_favorite_list,
    handle_favorite_remove,
)
from .commands.install import handle_install
from .commands.maintenance import handle_build, handle_clean, handle_update
from .commands.recent import handle_recent
from .commands.register import handle_register
from .commands.repositories import handle_list, handle_remove, handle_scan
from .commands.status import handle_status
from .models import InstallMode, ScopeType
from .utils import default_agents


def build_parser(agent_names: list[str] | None = None) -> argparse.ArgumentParser:
    """
    构建 SKILLS 命令行参数解析器。

    Args:
        agent_names: Agent 名列表，用于动态生成 `--agent` 的可选值。
            为 None 时回退到默认 agent 配置。

    Returns:
        已配置的 argparse 参数解析器。
    """
    if agent_names is None:
        agent_names = list(default_agents())
    agent_choices = [*agent_names, "all"]
    parser = argparse.ArgumentParser(
        prog="SKILLS",
        description="Sync local or GitHub skills repositories into agent skills directories.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    # 保留 rg 别名，兼容已有的短命令习惯。
    register_parser = subparsers.add_parser(
        "register",
        aliases=["rg"],
        help="Register a GitHub repo, a GitHub skill URL, or a local skills directory.",
    )
    register_parser.add_argument(
        "source", help="GitHub repo URL/shorthand, GitHub skill URL, or local path."
    )
    register_parser.add_argument("--name", help="Repository name for local registrations.")
    register_parser.add_argument(
        "--proxy", help="HTTP(S) proxy used when cloning GitHub repositories."
    )
    register_parser.add_argument(
        "--depth",
        type=int,
        default=3,
        help="Maximum scan depth for recursive skill discovery (default: 3).",
    )
    register_type = register_parser.add_mutually_exclusive_group()
    register_type.add_argument(
        "--github", action="store_true", help="Treat source as GitHub repository."
    )
    register_type.add_argument(
        "--local", action="store_true", help="Treat source as local directory."
    )
    register_parser.set_defaults(func=handle_register)

    # 保留 ls 别名，便于快速查看仓库列表。
    list_parser = subparsers.add_parser(
        "list",
        aliases=["ls"],
        help="List registered repositories.",
    )
    list_parser.set_defaults(func=handle_list)

    # 保留 rm 别名，便于快速移除仓库注册记录。
    remove_parser = subparsers.add_parser(
        "remove",
        aliases=["rm"],
        help="Remove a registered repository.",
    )
    remove_parser.add_argument("name", help="Registered repository name.")
    remove_parser.set_defaults(func=handle_remove)

    # scan 不写仓库配置，只读取注册仓库并展示可安装的 skill。
    scan_parser = subparsers.add_parser("scan", help="Scan registered repositories for skills.")
    scan_parser.add_argument("repository", nargs="?", help="Repository name. Omit to scan all.")
    scan_parser.add_argument(
        "--depth",
        type=int,
        default=3,
        help="Maximum scan depth for recursive skill discovery (default: 3).",
    )
    scan_parser.set_defaults(func=handle_scan)

    # install 支持无参数进入交互式安装，也支持指定仓库和 skill 的非交互式安装。
    install_parser = subparsers.add_parser(
        "install", help="Install skills from a registered repository."
    )
    install_parser.add_argument("repository", nargs="?", help="Registered repository name.")
    install_parser.add_argument("skills", nargs="*", help="Skill names to install.")
    install_parser.add_argument(
        "--agent",
        choices=agent_choices,
        default="all",
        help="Target agent. Default: all.",
    )
    install_parser.add_argument(
        "--scope",
        choices=[scope.value for scope in ScopeType],
        help="Install scope. Required for non-interactive install.",
    )
    install_parser.add_argument(
        "--mode",
        choices=[mode.value for mode in InstallMode],
        default=InstallMode.COPY.value,
        help="Install mode. Default: copy.",
    )
    install_parser.add_argument(
        "--force", action="store_true", help="Overwrite existing target skills."
    )
    install_parser.add_argument(
        "--project-dir",
        type=Path,
        help="Project directory for project-level install. Default: current working directory.",
    )
    install_parser.set_defaults(func=handle_install)

    # build 只重建缺失缓存，避免覆盖仍存在的 GitHub 仓库缓存。
    build_parser_cmd = subparsers.add_parser(
        "build", help="Rebuild local cache from .repos.json for GitHub repositories."
    )
    build_parser_cmd.add_argument(
        "--depth",
        type=int,
        default=3,
        help="Maximum scan depth for recursive skill discovery (default: 3).",
    )
    build_parser_cmd.add_argument(
        "--proxy", help="HTTP(S) proxy used when cloning GitHub repositories."
    )
    build_parser_cmd.set_defaults(func=handle_build)

    # update 会重新拉取远程仓库并替换对应缓存记录。
    update_parser = subparsers.add_parser(
        "update",
        help="Update registered GitHub repositories (re-clone and extract skills).",
    )
    update_parser.add_argument(
        "repository",
        nargs="*",
        help="Repository name(s) to update. Omit for interactive selection.",
    )
    update_parser.add_argument(
        "--depth",
        type=int,
        default=3,
        help="Maximum scan depth for recursive skill discovery (default: 3).",
    )
    update_parser.add_argument(
        "--proxy", help="HTTP(S) proxy used when cloning GitHub repositories."
    )
    update_parser.set_defaults(func=handle_update)

    # clean 只清理未被仓库记录引用的缓存目录，实际删除由 soft_delete 完成。
    clean_parser = subparsers.add_parser(
        "clean", help="Clean unreferenced cache directories from _repos_cache/."
    )
    clean_parser.set_defaults(func=handle_clean)

    # status 同时展示注册仓库与用户级、项目级已安装 skill。
    status_parser = subparsers.add_parser(
        "status", help="Show registered repositories and installed skills."
    )
    status_parser.set_defaults(func=handle_status)

    # recent 读取最近安装记录，不扫描远程仓库。
    recent_parser = subparsers.add_parser("recent", help="Show recently installed skills.")
    recent_parser.set_defaults(func=handle_recent)

    # favorite 维护本地常用 skill 缓存，fav 是兼容用短别名。
    favorite_parser = subparsers.add_parser(
        "favorite",
        aliases=["fav"],
        help="Manage favorite (常用) skills.",
    )
    favorite_sub = favorite_parser.add_subparsers(dest="favorite_command", metavar="action")

    fav_list = favorite_sub.add_parser("list", help="List favorite skills.")
    fav_list.set_defaults(func=handle_favorite_list)

    fav_add = favorite_sub.add_parser("add", help="Copy skills from a repo into favorite.")
    fav_add.add_argument("repository", help="Registered repository name.")
    fav_add.add_argument("skills", nargs="+", help="Skill names to add.")
    fav_add.set_defaults(func=handle_favorite_add)

    fav_remove = favorite_sub.add_parser("remove", help="Soft-delete a favorite skill.")
    fav_remove.add_argument("skill", help="Favorite skill name to remove.")
    fav_remove.set_defaults(func=handle_favorite_remove)

    favorite_parser.set_defaults(func=handle_favorite_default)

    return parser
