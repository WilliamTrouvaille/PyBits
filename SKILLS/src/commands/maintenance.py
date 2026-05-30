"""
SKILLS 缓存维护命令处理器。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import questionary
from loguru import logger
from questionary import Choice

from _shared.utils.trash import soft_delete

from ..models import Repository, RepositoryType
from ..persistence import get_repository, load_repositories, update_repository
from ..repository import register_github_repo, register_github_skills, scan_repository
from ..utils import Settings


def handle_build(args: argparse.Namespace, settings: Settings, paths: dict[str, Path]) -> int:
    """
    根据 .repos.json 重建缺失的 GitHub 仓库缓存。

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

    # 筛选出需要重建的 GitHub 仓库
    github_repos = [
        r for r in repos if r.type in (RepositoryType.GITHUB, RepositoryType.GITHUB_SKILLS)
    ]
    missing_repos = [r for r in github_repos if not r.local_path or not r.local_path.exists()]

    if not missing_repos:
        print("所有 GitHub 仓库的缓存都已存在，无需重建。")
        return 0

    print(f"\n读取 .repos.json，发现 {len(repos)} 个仓库:")
    for repo in missing_repos:
        print(f"  {repo.name} ({repo.type.value}) - 缓存不存在")

    # 检查本地仓库
    local_repos = [r for r in repos if r.type == RepositoryType.LOCAL]
    for repo in local_repos:
        if not repo.path or not repo.path.exists():
            print(f"  {repo.name} ({repo.type.value}) - 本地路径不存在，跳过")

    if not questionary.confirm(f"\n是否重建缺失的 {len(missing_repos)} 个 GitHub 仓库缓存？").ask():
        logger.info("[用户操作] 取消重建缓存")
        print("重建已取消。")
        return 1

    repo_names = ", ".join(r.name for r in missing_repos)
    logger.info(f"[用户操作] 重建缓存: {repo_names}")

    print()
    for repo in missing_repos:
        print(f"正在重建 {repo.name} ...")
        if not rebuild_update_and_preview(repo, args, settings, paths, action_label="重建"):
            continue

    print("重建完成！")

    # 检查缓存目录数量
    if paths["repos_cache_dir"].exists():
        cache_dirs = [d for d in paths["repos_cache_dir"].iterdir() if d.is_dir()]
        repos_count = len(
            [r for r in repos if r.type in (RepositoryType.GITHUB, RepositoryType.GITHUB_SKILLS)]
        )
        if len(cache_dirs) > repos_count:
            print("\n检查缓存目录...")
            print(
                f"_repos_cache/ 中有 {len(cache_dirs)} 个目录，.repos.json 中有 {repos_count} 个 GitHub 仓库。"
            )
            print("提示: 使用 SKILLS clean 清理未使用的缓存目录。")

    return 0


def handle_update(args: argparse.Namespace, settings: Settings, paths: dict[str, Path]) -> int:
    """
    更新已注册的 GitHub 仓库缓存。

    Args:
        args: argparse 解析出的命名空间。
        settings: SKILLS 运行时配置。
        paths: 运行时派生路径集合。

    Returns:
        进程退出码。
    """
    repos = load_repositories(paths["repos_json_path"], paths["repos_local_json_path"])
    github_repos = [
        r for r in repos if r.type in (RepositoryType.GITHUB, RepositoryType.GITHUB_SKILLS)
    ]

    if not github_repos:
        print("未找到已注册的 GitHub 仓库。")
        return 0

    # 确定要更新的仓库
    if args.repository:
        # 非交互式：指定仓库名称
        repos_to_update = []
        for repo_name in args.repository:
            repo = get_repository(
                repo_name, paths["repos_json_path"], paths["repos_local_json_path"]
            )
            if not repo:
                print(f"仓库不存在: {repo_name}", file=sys.stderr)
                return 1
            if repo.type not in (RepositoryType.GITHUB, RepositoryType.GITHUB_SKILLS):
                print(f"仓库 '{repo_name}' 不是可更新的 GitHub 仓库，跳过。", file=sys.stderr)
                continue
            repos_to_update.append(repo)
    else:
        # 交互式：选择仓库
        repo_choices = [
            Choice(
                title=f"{r.name} ({r.type.value}, {r.registered_at.strftime('%Y-%m-%d %H:%M:%S')})",
                value=r,
            )
            for r in github_repos
        ]
        repos_to_update = questionary.checkbox(
            "选择要更新的仓库:",
            choices=repo_choices,
            instruction="(方向键移动，空格选择，a 全选，i 反选)",
        ).ask()

        if not repos_to_update:
            logger.info("[用户操作] 取消更新")
            print("更新已取消。")
            return 1

    repo_names = ", ".join(r.name for r in repos_to_update)
    logger.info(f"[用户操作] 更新仓库: {repo_names}")

    if not questionary.confirm(f"\n是否更新选中的 {len(repos_to_update)} 个仓库？").ask():
        logger.info("[用户操作] 取消更新 (用户拒绝确认)")
        print("更新已取消。")
        return 1

    print()
    for repo in repos_to_update:
        print(f"正在更新 {repo.name} ...")
        if not rebuild_update_and_preview(repo, args, settings, paths, action_label="更新"):
            continue

    print("更新完成！")
    return 0


def handle_clean(args: argparse.Namespace, settings: Settings, paths: dict[str, Path]) -> int:
    """
    清理未被 .repos.json 引用的缓存目录。

    Args:
        args: argparse 解析出的命名空间。
        settings: SKILLS 运行时配置。
        paths: 运行时派生路径集合。

    Returns:
        进程退出码。
    """
    if not paths["repos_cache_dir"].exists():
        print("缓存目录不存在。")
        return 0

    # 获取所有已注册仓库的缓存目录名
    repos = load_repositories(paths["repos_json_path"], paths["repos_local_json_path"])
    referenced_dirs = set()
    for repo in repos:
        if repo.local_path:
            referenced_dirs.add(repo.local_path.name)

    # 查找未引用的缓存目录
    unreferenced_dirs = []
    for cache_dir in paths["repos_cache_dir"].iterdir():
        if cache_dir.name == "favorite":
            continue
        if cache_dir.is_dir() and cache_dir.name not in referenced_dirs:
            unreferenced_dirs.append(cache_dir)

    if not unreferenced_dirs:
        print("未发现未引用的缓存目录。")
        return 0

    print("\n扫描 _repos_cache/ 目录...")
    print("\n发现以下缓存目录不在 .repos.json 中：")
    for i, cache_dir in enumerate(unreferenced_dirs, 1):
        print(f"  {i}. {cache_dir.name}")
    print(f"\n总计: {len(unreferenced_dirs)} 个目录")

    if not questionary.confirm("\n是否软删除这些目录？").ask():
        logger.info("[用户操作] 取消清理缓存")
        print("清理已取消。")
        return 1

    dir_names = ", ".join(d.name for d in unreferenced_dirs)
    logger.info(f"[用户操作] 清理缓存目录: {dir_names}")

    for cache_dir in unreferenced_dirs:
        print(f"正在软删除 {cache_dir.name} ...")
        try:
            moved_dir = soft_delete(cache_dir, "skills-clean-cache")
            logger.info(f"缓存目录已软删除: {cache_dir} -> {moved_dir}")
        except Exception as e:
            print(f"软删除失败: {e}", file=sys.stderr)

    print("\n清理完成！")
    return 0


def rebuild_remote_repository(
    repo: Repository,
    proxy: str | None,
    repos_cache_dir: Path,
) -> Repository:
    """
    根据持久化来源信息重建远程仓库缓存。

    Args:
        repo: 待重建的远程仓库记录。
        proxy: 可选的 HTTP(S) 代理。
        repos_cache_dir: 仓库缓存根目录。

    Returns:
        重建后的仓库记录。

    Raises:
        ValueError: 仓库类型或来源信息不支持重建。
    """
    if repo.type == RepositoryType.GITHUB:
        if not repo.url:
            raise ValueError(f"GitHub 仓库缺少 URL: {repo.name}")
        return register_github_repo(repo.url, proxy, repos_cache_dir)

    if repo.type == RepositoryType.GITHUB_SKILLS:
        if not repo.sources:
            raise ValueError(f"精选 GitHub skills 仓库缺少 sources: {repo.name}")
        return register_github_skills(repo.sources, repo.name, proxy, repos_cache_dir)

    raise ValueError(f"仓库不是可重建的远程仓库: {repo.name}")


def rebuild_update_and_preview(
    repo: Repository,
    args: argparse.Namespace,
    settings: Settings,
    paths: dict[str, Path],
    action_label: str,
) -> bool:
    """
    重建远程仓库缓存、保存仓库记录并输出 skill 预览。

    Args:
        repo: 待处理的远程仓库记录。
        args: argparse 解析出的命名空间。
        settings: SKILLS 运行时配置。
        paths: 运行时派生路径集合。
        action_label: 用户可见的动作名称，例如“重建”或“更新”。

    Returns:
        成功时返回 True；失败时打印错误并返回 False。
    """
    try:
        new_repo = rebuild_remote_repository(repo, args.proxy, paths["repos_cache_dir"])
        update_repository(new_repo, paths["repos_json_path"], paths["repos_local_json_path"])
        print(f"{action_label}成功！")

        if action_label == "重建":
            print(f"正在扫描 skills（深度: {args.depth}）...")
        skills = scan_repository(new_repo, args.depth, settings.excluded_dirs)
        display_count = min(5, len(skills))
        print(f"发现 {len(skills)} 个 skill（显示前 {display_count} 个）:")
        for skill in skills[:display_count]:
            print(f"  {skill.name:<20} {skill.description}")
        if len(skills) > 5:
            suffix = "，使用 SKILLS scan 查看完整列表" if action_label == "更新" else ""
            print(f"  ...还有 {len(skills) - 5} 个 skill{suffix}")
        if action_label == "更新":
            print(f"以下 skills 可能有新版本: {', '.join(s.name for s in skills[:display_count])}")
            if len(skills) > 5:
                print(f"...还有 {len(skills) - 5} 个 skill，使用 SKILLS scan 查看完整列表")
        print()
        return True
    except Exception as e:
        failure_label = "克隆" if action_label == "重建" else action_label
        print(f"{failure_label}失败: {e}", file=sys.stderr)
        return False
