"""
SKILLS 仓库注册命令处理器。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import questionary
from loguru import logger

from _shared.utils.trash import soft_delete

from ..persistence import add_repository, repository_exists, update_repository
from ..repository import (
    is_github_skill_url,
    parse_github_url,
    register_github_repo,
    register_github_skills,
    register_local_repo,
    scan_repository,
)
from ..utils import Settings


def handle_register(args: argparse.Namespace, settings: Settings, paths: dict[str, Path]) -> int:
    """
    注册 GitHub 仓库、GitHub skill URL 或本地 skill 目录。

    Args:
        args: argparse 解析出的命名空间。
        settings: SKILLS 运行时配置。
        paths: 运行时派生路径集合。

    Returns:
        进程退出码。
    """
    source = args.source
    source_path = Path(source).expanduser()
    use_local = args.local or (not args.github and source_path.exists())

    if use_local:
        repo_name = args.name or source_path.name
        if repository_exists(repo_name, paths["repos_json_path"], paths["repos_local_json_path"]):
            print(f"仓库已存在: {repo_name}", file=sys.stderr)
            return 1
        repo = register_local_repo(source_path, args.name)
        add_repository(repo, paths["repos_json_path"], paths["repos_local_json_path"])
        logger.info(f"[用户操作] 注册仓库: {repo.name} (local)")
        print(f"已注册仓库: {repo.name} ({repo.type.value})")
        return 0

    # 带子路径的 GitHub URL 会注册为精选 skills 仓库，而不是完整仓库。
    if is_github_skill_url(source):
        return register_skill_url(args, settings, paths)

    # 普通 GitHub 仓库 URL 或 owner/repo 简写按完整仓库注册。
    owner, repo_short_name = parse_github_url(source)
    repo_name = f"{owner}/{repo_short_name}"

    # 已存在的 GitHub 仓库需要用户确认覆盖，避免误替换缓存记录。
    if repository_exists(repo_name, paths["repos_json_path"], paths["repos_local_json_path"]):
        if not questionary.confirm(f"仓库 '{repo_name}' 已存在，是否覆盖？").ask():
            logger.info(f"[用户操作] 取消注册仓库: {repo_name} (用户拒绝覆盖)")
            print("注册已取消。")
            return 1
        logger.info(f"[用户操作] 注册仓库: {repo_name} (github, 覆盖模式)")
    else:
        logger.info(f"[用户操作] 注册仓库: {repo_name} (github)")

    print(f"\n正在克隆仓库 https://github.com/{owner}/{repo_short_name}.git ...")

    try:
        repo = register_github_repo(source, args.proxy, paths["repos_cache_dir"])
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"克隆失败: {e}", file=sys.stderr)
        print("提示: 如果网络不稳定，可以使用 --proxy 参数配置代理。", file=sys.stderr)
        return 1

    print("克隆成功！")

    # 注册前先展示扫描结果，让用户确认空仓库是否仍要保留。
    print(f"\n正在扫描仓库中的 skills（深度: {args.depth}）...")
    skills = scan_repository(repo, args.depth, settings.excluded_dirs)

    if not skills:
        print("未发现任何合法 skill。")
        if not questionary.confirm("是否继续注册？").ask():
            logger.info(f"[用户操作] 取消注册仓库: {repo_name} (未发现 skill)")
            print("注册已取消。")
            # 空仓库取消注册时，已创建的缓存目录必须走软删除。
            if repo.local_path and repo.local_path.exists():
                soft_delete(repo.local_path, "skills-register-empty")
            return 1
    else:
        display_count = min(5, len(skills))
        print(f"发现 {len(skills)} 个 skill（显示前 {display_count} 个）:")
        for skill in skills[:display_count]:
            print(f"  {skill.name:<20} {skill.description}")
        if len(skills) > 5:
            print(f"  ...还有 {len(skills) - 5} 个 skill，使用 SKILLS scan 查看完整列表")

    # 覆盖注册走 update；首次注册走 add，保持路径映射文件同步。
    if repository_exists(repo_name, paths["repos_json_path"], paths["repos_local_json_path"]):
        update_repository(repo, paths["repos_json_path"], paths["repos_local_json_path"])
        print(f"\n已更新仓库: {repo.name} ({repo.type.value})")
    else:
        add_repository(repo, paths["repos_json_path"], paths["repos_local_json_path"])
        print(f"\n已注册仓库: {repo.name} ({repo.type.value})")

    print(f"缓存路径: {repo.local_path}")
    return 0


def register_skill_url(args: argparse.Namespace, settings: Settings, paths: dict[str, Path]) -> int:
    """
    注册单个 GitHub skill URL 为精选仓库。

    Args:
        args: argparse 解析出的命名空间。
        settings: SKILLS 运行时配置。
        paths: 运行时派生路径集合。

    Returns:
        进程退出码。
    """
    try:
        repo = register_github_skills(
            [args.source], args.name, args.proxy, paths["repos_cache_dir"]
        )
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"下载失败: {e}", file=sys.stderr)
        print("提示: 目前仅支持公开 GitHub 仓库；网络不稳定时可使用 --proxy。", file=sys.stderr)
        return 1

    if repository_exists(repo.name, paths["repos_json_path"], paths["repos_local_json_path"]):
        print(f"仓库已存在: {repo.name}", file=sys.stderr)
        if repo.local_path and repo.local_path.exists():
            soft_delete(repo.local_path, "skills-selected-duplicate")
        return 1

    skills = scan_repository(repo, args.depth, settings.excluded_dirs)
    if not skills:
        print("未发现任何合法 skill。", file=sys.stderr)
        if repo.local_path and repo.local_path.exists():
            soft_delete(repo.local_path, "skills-selected-empty")
        return 1

    add_repository(repo, paths["repos_json_path"], paths["repos_local_json_path"])
    logger.info(f"[用户操作] 注册精选 GitHub skills: {repo.name}")

    print(f"已注册精选仓库: {repo.name} ({repo.type.value})")
    print(f"缓存路径: {repo.local_path}")
    print(f"来源 URL: {len(repo.sources or [])} 个")
    display_count = min(5, len(skills))
    print(f"发现 {len(skills)} 个 skill（显示前 {display_count} 个）:")
    for skill in skills[:display_count]:
        print(f"  {skill.name:<20} {skill.description}")
    if len(skills) > 5:
        print(f"  ...还有 {len(skills) - 5} 个 skill，使用 SKILLS scan 查看完整列表")
    return 0
