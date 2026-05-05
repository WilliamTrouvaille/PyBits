"""Command-line entry point for SKILLS."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import questionary
from loguru import logger

from .installer import install_skill
from .models import AgentType, InstallMode, RepositoryType, ScopeType, Skill
from .persistence import (
    add_repository,
    get_repository,
    load_repositories,
    remove_repository,
    repository_exists,
    update_repository,
)
from .repository import (
    parse_github_url,
    register_github_repo,
    register_local_repo,
    scan_repository,
)
from .utils import setup_logger


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="SKILLS",
        description="Sync local or GitHub skills repositories into agent skills directories.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    register_parser = subparsers.add_parser(
        "register",
        help="Register a GitHub repository or local skills directory.",
    )
    register_parser.add_argument(
        "source", help="GitHub URL/owner-repo shorthand or local path."
    )
    register_parser.add_argument(
        "--name", help="Repository name for local registrations."
    )
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

    list_parser = subparsers.add_parser(
        "ls",
        aliases=["list"],
        help="List registered repositories.",
    )
    list_parser.set_defaults(func=handle_list)

    remove_parser = subparsers.add_parser(
        "remove", help="Remove a registered repository."
    )
    remove_parser.add_argument("name", help="Registered repository name.")
    remove_parser.set_defaults(func=handle_remove)

    scan_parser = subparsers.add_parser(
        "scan", help="Scan registered repositories for skills."
    )
    scan_parser.add_argument(
        "repository", nargs="?", help="Repository name. Omit to scan all."
    )
    scan_parser.add_argument(
        "--depth",
        type=int,
        default=3,
        help="Maximum scan depth for recursive skill discovery (default: 3).",
    )
    scan_parser.set_defaults(func=handle_scan)

    install_parser = subparsers.add_parser(
        "install", help="Install skills from a registered repository."
    )
    install_parser.add_argument(
        "repository", nargs="?", help="Registered repository name."
    )
    install_parser.add_argument("skills", nargs="*", help="Skill names to install.")
    install_parser.add_argument(
        "--agent",
        choices=[agent.value for agent in AgentType],
        default=AgentType.ALL.value,
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
    install_parser.set_defaults(func=handle_install)

    # build 命令
    build_parser = subparsers.add_parser(
        "build", help="Rebuild local cache from .repos.json for GitHub repositories."
    )
    build_parser.add_argument(
        "--depth",
        type=int,
        default=3,
        help="Maximum scan depth for recursive skill discovery (default: 3).",
    )
    build_parser.add_argument(
        "--proxy", help="HTTP(S) proxy used when cloning GitHub repositories."
    )
    build_parser.set_defaults(func=handle_build)

    # update 命令
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

    # clean 命令
    clean_parser = subparsers.add_parser(
        "clean", help="Clean unreferenced cache directories from _repos_cache/."
    )
    clean_parser.set_defaults(func=handle_clean)

    # status 命令
    status_parser = subparsers.add_parser(
        "status", help="Show registered repositories and installed skills."
    )
    status_parser.set_defaults(func=handle_status)

    return parser


def handle_register(args: argparse.Namespace) -> int:
    """Register a GitHub or local repository."""
    source = args.source
    source_path = Path(source).expanduser()
    use_local = args.local or (not args.github and source_path.exists())

    if use_local:
        repo_name = args.name or source_path.name
        if repository_exists(repo_name):
            print(f"仓库已存在: {repo_name}", file=sys.stderr)
            return 1
        repo = register_local_repo(source_path, args.name)
        add_repository(repo)
        logger.info(f"[用户操作] 注册仓库: {repo.name} (local)")
        print(f"已注册仓库: {repo.name} ({repo.type.value})")
        return 0

    # GitHub 仓库
    owner, repo_short_name = parse_github_url(source)
    repo_name = f"{owner}/{repo_short_name}"

    # 检查是否已存在
    if repository_exists(repo_name):
        if not questionary.confirm(f"仓库 '{repo_name}' 已存在，是否覆盖？").ask():
            logger.info(f"[用户操作] 取消注册仓库: {repo_name} (用户拒绝覆盖)")
            print("注册已取消。")
            return 1
        logger.info(f"[用户操作] 注册仓库: {repo_name} (github, 覆盖模式)")
    else:
        logger.info(f"[用户操作] 注册仓库: {repo_name} (github)")

    print(f"\n正在克隆仓库 https://github.com/{owner}/{repo_short_name}.git ...")

    try:
        repo = register_github_repo(source, args.proxy)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"克隆失败: {e}", file=sys.stderr)
        print("提示: 如果网络不稳定，可以使用 --proxy 参数配置代理。", file=sys.stderr)
        return 1

    print("克隆成功！")

    # 自动扫描并显示发现的 skills
    print(f"\n正在扫描仓库中的 skills（深度: {args.depth}）...")
    skills = scan_repository(repo, args.depth)

    if not skills:
        print("未发现任何合法 skill。")
        if not questionary.confirm("是否继续注册？").ask():
            logger.info(f"[用户操作] 取消注册仓库: {repo_name} (未发现 skill)")
            print("注册已取消。")
            # 清理已创建的缓存目录
            if repo.local_path and repo.local_path.exists():
                import shutil

                shutil.rmtree(repo.local_path)
            return 1
    else:
        display_count = min(5, len(skills))
        print(f"发现 {len(skills)} 个 skill（显示前 {display_count} 个）:")
        for skill in skills[:display_count]:
            print(f"  {skill.name:<20} {skill.description}")
        if len(skills) > 5:
            print(
                f"  ...还有 {len(skills) - 5} 个 skill，使用 SKILLS scan 查看完整列表"
            )

    # 保存或更新仓库记录
    if repository_exists(repo_name):
        update_repository(repo)
        print(f"\n已更新仓库: {repo.name} ({repo.type.value})")
    else:
        add_repository(repo)
        print(f"\n已注册仓库: {repo.name} ({repo.type.value})")

    print(f"缓存路径: {repo.local_path}")
    return 0


def handle_list(_args: argparse.Namespace) -> int:
    """List registered repositories."""
    repos = load_repositories()
    if not repos:
        print("未找到已注册仓库。")
        return 0

    for repo in repos:
        source = repo.url if repo.type == RepositoryType.GITHUB else repo.path
        print(f"{repo.name}\t{repo.type.value}\t{source}")
    return 0


def handle_remove(args: argparse.Namespace) -> int:
    """Remove a registered repository."""
    if remove_repository(args.name):
        logger.info(f"[用户操作] 移除仓库: {args.name}")
        print(f"已移除仓库: {args.name}")
        return 0

    print(f"仓库不存在: {args.name}", file=sys.stderr)
    return 1


def handle_scan(args: argparse.Namespace) -> int:
    """Scan registered repositories for skills."""
    repos = load_repositories()
    if not repos:
        print("未找到已注册仓库。")
        return 0

    if args.repository:
        # 非交互式：扫描指定仓库
        repo = get_repository(args.repository)
        if not repo:
            print(f"仓库不存在: {args.repository}", file=sys.stderr)
            return 1
        repos_to_scan = [repo]
    else:
        # 交互式：选择要扫描的仓库
        if len(repos) == 1:
            # 只有一个仓库，直接扫描
            repos_to_scan = repos
        else:
            # 多个仓库，提供交互式选择
            repo_labels = [
                f"{r.name} ({r.type.value}, {r.registered_at.strftime('%Y-%m-%d %H:%M:%S')})"
                for r in repos
            ]
            repo_labels.append("[扫描所有仓库]")

            selected_label = questionary.select(
                "选择要扫描的仓库:", choices=repo_labels
            ).ask()

            if not selected_label:
                logger.info("[用户操作] 取消扫描")
                print("扫描已取消。")
                return 1

            if selected_label == "[扫描所有仓库]":
                repos_to_scan = repos
                logger.info("[用户操作] 扫描所有仓库")
            else:
                repo_index = repo_labels.index(selected_label)
                repos_to_scan = [repos[repo_index]]
                logger.info(f"[用户操作] 扫描仓库: {repos_to_scan[0].name}")

    # 扫描选中的仓库
    for repo in repos_to_scan:
        skills = scan_repository(repo, args.depth)
        logger.info(f"[用户操作] 扫描结果: {repo.name} - {len(skills)} 个 skill")
        print(f"{repo.name}: {len(skills)} 个 skill")
        for skill in skills:
            print(f"  {skill.name:<20} {skill.description}")
        if len(repos_to_scan) > 1:
            print()  # 多个仓库时添加空行分隔

    return 0


def handle_install(args: argparse.Namespace) -> int:
    """Install selected skills."""
    if not args.repository and not args.skills:
        return interactive_install()

    if not args.repository:
        print(
            "缺少仓库名称。示例: SKILLS install repo/name skill-name --scope user",
            file=sys.stderr,
        )
        return 2

    if not args.skills:
        print(
            "缺少 skill 名称。无参数运行 `SKILLS install` 可进入交互式安装。",
            file=sys.stderr,
        )
        return 2

    if not args.scope:
        print("非交互式安装必须指定 --scope <user|project>。", file=sys.stderr)
        return 2

    repo = get_repository(args.repository)
    if not repo:
        print(f"仓库不存在: {args.repository}", file=sys.stderr)
        return 1

    available_skills = {skill.name: skill for skill in scan_repository(repo)}
    missing_skills = [
        skill_name for skill_name in args.skills if skill_name not in available_skills
    ]
    if missing_skills:
        print(f"未找到 skill: {', '.join(missing_skills)}", file=sys.stderr)
        if available_skills:
            print("可用 skills:", file=sys.stderr)
            for skill_name in sorted(available_skills):
                print(f"  {skill_name}", file=sys.stderr)
        return 1

    agent = AgentType(args.agent)
    scope = ScopeType(args.scope)
    mode = InstallMode(args.mode)

    skill_names_str = ", ".join(args.skills)
    logger.info(
        f"[用户操作] 安装 skills: {skill_names_str} "
        f"(agent={agent.value}, scope={scope.value}, mode={mode.value})"
    )

    for skill_name in args.skills:
        install_skill(available_skills[skill_name], agent, scope, mode, args.force)

    return 0


def interactive_install() -> int:
    """Run the interactive install flow."""
    repos = load_repositories()
    if not repos:
        print("未找到已注册仓库，请先使用 `SKILLS register` 注册仓库。")
        return 1

    repo_labels = [f"{repo.name} ({repo.type.value})" for repo in repos]
    selected_repo_label = questionary.select(
        "选择要安装的仓库:", choices=repo_labels
    ).ask()
    if not selected_repo_label:
        logger.info("[用户操作] 取消安装 (未选择仓库)")
        print("安装已取消。")
        return 1

    repo = repos[repo_labels.index(selected_repo_label)]
    skills = scan_repository(repo)
    if not skills:
        print(f"仓库 {repo.name} 中未找到任何合法 skill。")
        return 1

    skill_labels = [format_skill_label(skill) for skill in skills]
    selected_skill_labels = questionary.checkbox(
        "选择要安装的 skills:",
        choices=skill_labels,
        instruction="(方向键移动，空格选择，a 全选，i 反选)",
    ).ask()
    if not selected_skill_labels:
        logger.info("[用户操作] 取消安装 (未选择 skills)")
        print("安装已取消。")
        return 1

    agent_value = questionary.select(
        "选择目标 agent:",
        choices=[agent.value for agent in AgentType],
        default=AgentType.ALL.value,
    ).ask()
    scope_value = questionary.select(
        "选择安装范围:",
        choices=[scope.value for scope in ScopeType],
        default=ScopeType.USER.value,
    ).ask()
    mode_value = questionary.select(
        "选择安装模式:",
        choices=[mode.value for mode in InstallMode],
        default=InstallMode.COPY.value,
    ).ask()

    if not agent_value or not scope_value or not mode_value:
        logger.info("[用户操作] 取消安装 (未完成配置)")
        print("安装已取消。")
        return 1

    selected_skills = [
        skills[skill_labels.index(label)] for label in selected_skill_labels
    ]

    skill_names_str = ", ".join(skill.name for skill in selected_skills)
    logger.info(
        f"[用户操作] 安装 skills: {skill_names_str} "
        f"(agent={agent_value}, scope={scope_value}, mode={mode_value})"
    )

    print()
    print("安装参数:")
    print(f"  仓库: {repo.name}")
    print(f"  Skills: {skill_names_str}")
    print(f"  Agent: {agent_value}")
    print(f"  Scope: {scope_value}")
    print(f"  Mode: {mode_value}")

    if not questionary.confirm("是否继续安装？").ask():
        logger.info("[用户操作] 取消安装 (用户拒绝确认)")
        print("安装已取消。")
        return 1

    for skill in selected_skills:
        install_skill(
            skill,
            AgentType(agent_value),
            ScopeType(scope_value),
            InstallMode(mode_value),
        )

    return 0


def format_skill_label(skill: Skill, max_description_length: int = 100) -> str:
    """
    Format a skill for interactive selection.

    Args:
        skill: Skill object
        max_description_length: Maximum length for description (default: 100)

    Returns:
        Formatted label string
    """
    description = skill.description
    if len(description) > max_description_length:
        description = description[:max_description_length] + "..."
    return f"{skill.name} - {description}"


def handle_build(args: argparse.Namespace) -> int:
    """Rebuild local cache from .repos.json for GitHub repositories."""
    repos = load_repositories()
    if not repos:
        print("未找到已注册仓库。")
        return 0

    # 筛选出需要重建的 GitHub 仓库
    github_repos = [r for r in repos if r.type == RepositoryType.GITHUB]
    missing_repos = [
        r for r in github_repos if not r.local_path or not r.local_path.exists()
    ]

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

    if not questionary.confirm(
        f"\n是否重建缺失的 {len(missing_repos)} 个 GitHub 仓库缓存？"
    ).ask():
        logger.info("[用户操作] 取消重建缓存")
        print("重建已取消。")
        return 1

    repo_names = ", ".join(r.name for r in missing_repos)
    logger.info(f"[用户操作] 重建缓存: {repo_names}")

    print()
    for repo in missing_repos:
        print(f"正在克隆 {repo.name} ...")
        try:
            new_repo = register_github_repo(repo.url, args.proxy)
            update_repository(new_repo)
            print("克隆成功！")

            # 扫描并显示 skills
            print(f"正在扫描 skills（深度: {args.depth}）...")
            skills = scan_repository(new_repo, args.depth)
            display_count = min(5, len(skills))
            print(f"发现 {len(skills)} 个 skill（显示前 {display_count} 个）:")
            for skill in skills[:display_count]:
                print(f"  {skill.name:<20} {skill.description}")
            if len(skills) > 5:
                print(f"  ...还有 {len(skills) - 5} 个 skill")
            print()
        except Exception as e:
            print(f"克隆失败: {e}", file=sys.stderr)
            continue

    print("重建完成！")

    # 检查缓存目录数量
    from .config import REPOS_CACHE_DIR

    if REPOS_CACHE_DIR.exists():
        cache_dirs = [d for d in REPOS_CACHE_DIR.iterdir() if d.is_dir()]
        repos_count = len([r for r in repos if r.type == RepositoryType.GITHUB])
        if len(cache_dirs) > repos_count:
            print("\n检查缓存目录...")
            print(
                f"_repos_cache/ 中有 {len(cache_dirs)} 个目录，.repos.json 中有 {repos_count} 个 GitHub 仓库。"
            )
            print("提示: 使用 SKILLS clean 清理未使用的缓存目录。")

    return 0


def handle_update(args: argparse.Namespace) -> int:
    """Update registered GitHub repositories."""
    repos = load_repositories()
    github_repos = [r for r in repos if r.type == RepositoryType.GITHUB]

    if not github_repos:
        print("未找到已注册的 GitHub 仓库。")
        return 0

    # 确定要更新的仓库
    if args.repository:
        # 非交互式：指定仓库名称
        repos_to_update = []
        for repo_name in args.repository:
            repo = get_repository(repo_name)
            if not repo:
                print(f"仓库不存在: {repo_name}", file=sys.stderr)
                return 1
            if repo.type != RepositoryType.GITHUB:
                print(f"仓库 '{repo_name}' 不是 GitHub 仓库，跳过。", file=sys.stderr)
                continue
            repos_to_update.append(repo)
    else:
        # 交互式：选择仓库
        repo_labels = [
            f"{r.name} ({r.type.value}, {r.registered_at.strftime('%Y-%m-%d %H:%M:%S')})"
            for r in github_repos
        ]
        selected_labels = questionary.checkbox(
            "选择要更新的仓库:",
            choices=repo_labels,
            instruction="(方向键移动，空格选择，a 全选，i 反选)",
        ).ask()

        if not selected_labels:
            logger.info("[用户操作] 取消更新")
            print("更新已取消。")
            return 1

        repos_to_update = [
            github_repos[repo_labels.index(label)] for label in selected_labels
        ]

    repo_names = ", ".join(r.name for r in repos_to_update)
    logger.info(f"[用户操作] 更新仓库: {repo_names}")

    if not questionary.confirm(
        f"\n是否更新选中的 {len(repos_to_update)} 个仓库？"
    ).ask():
        logger.info("[用户操作] 取消更新 (用户拒绝确认)")
        print("更新已取消。")
        return 1

    print()
    for repo in repos_to_update:
        print(f"正在更新 {repo.name} ...")
        try:
            new_repo = register_github_repo(repo.url, args.proxy)
            update_repository(new_repo)
            print("克隆成功！")

            # 扫描并显示 skills
            skills = scan_repository(new_repo, args.depth)
            display_count = min(5, len(skills))
            print(f"发现 {len(skills)} 个 skill（显示前 {display_count} 个）:")
            for skill in skills[:display_count]:
                print(f"  {skill.name:<20} {skill.description}")
            if len(skills) > 5:
                print(
                    f"  ...还有 {len(skills) - 5} 个 skill，使用 SKILLS scan 查看完整列表"
                )
            print(
                f"以下 skills 可能有新版本: {', '.join(s.name for s in skills[:display_count])}"
            )
            if len(skills) > 5:
                print(
                    f"...还有 {len(skills) - 5} 个 skill，使用 SKILLS scan 查看完整列表"
                )
            print()
        except Exception as e:
            print(f"更新失败: {e}", file=sys.stderr)
            continue

    print("更新完成！")
    return 0


def handle_clean(args: argparse.Namespace) -> int:
    """Clean unreferenced cache directories."""
    from .config import REPOS_CACHE_DIR

    if not REPOS_CACHE_DIR.exists():
        print("缓存目录不存在。")
        return 0

    # 获取所有已注册仓库的缓存目录名
    repos = load_repositories()
    referenced_dirs = set()
    for repo in repos:
        if repo.local_path:
            referenced_dirs.add(repo.local_path.name)

    # 查找未引用的缓存目录
    unreferenced_dirs = []
    for cache_dir in REPOS_CACHE_DIR.iterdir():
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

    if not questionary.confirm("\n是否删除这些目录？").ask():
        logger.info("[用户操作] 取消清理缓存")
        print("清理已取消。")
        return 1

    import shutil

    dir_names = ", ".join(d.name for d in unreferenced_dirs)
    logger.info(f"[用户操作] 清理缓存目录: {dir_names}")

    for cache_dir in unreferenced_dirs:
        print(f"正在删除 {cache_dir.name} ...")
        try:
            shutil.rmtree(cache_dir)
        except Exception as e:
            print(f"删除失败: {e}", file=sys.stderr)

    print("\n清理完成！")
    return 0


def handle_status(args: argparse.Namespace) -> int:
    """Show registered repositories and installed skills."""
    from .config import (
        CLAUDE_PROJECT_SKILLS_DIR,
        CLAUDE_USER_SKILLS_DIR,
        CODEX_PROJECT_SKILLS_DIR,
        CODEX_USER_SKILLS_DIR,
    )

    repos = load_repositories()
    print(f"已注册仓库: {len(repos)} 个")
    for repo in repos:
        timestamp = repo.registered_at.strftime("%Y-%m-%d %H:%M:%S")
        print(f"  {repo.name} ({repo.type.value}, {timestamp})")

    print("\n已安装 skills:")

    # 扫描各个 skills 目录
    def scan_skills_dir(path: Path) -> list[str]:
        if not path.exists():
            return []
        return [
            d.name for d in path.iterdir() if d.is_dir() and not d.name.startswith(".")
        ]

    claude_user_skills = scan_skills_dir(CLAUDE_USER_SKILLS_DIR)
    claude_project_skills = scan_skills_dir(CLAUDE_PROJECT_SKILLS_DIR)
    codex_user_skills = scan_skills_dir(CODEX_USER_SKILLS_DIR)
    codex_project_skills = scan_skills_dir(CODEX_PROJECT_SKILLS_DIR)

    print("  用户级 (claude):")
    if claude_user_skills:
        for skill in claude_user_skills:
            print(f"    {skill}")
    else:
        print("    无")

    print("\n  用户级 (codex):")
    if codex_user_skills:
        for skill in codex_user_skills:
            print(f"    {skill}")
    else:
        print("    无")

    print("\n  项目级 (claude):")
    if claude_project_skills:
        for skill in claude_project_skills:
            print(f"    {skill}")
    else:
        print("    无")

    print("\n  项目级 (codex):")
    if codex_project_skills:
        for skill in codex_project_skills:
            print(f"    {skill}")
    else:
        print("    无")

    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the SKILLS command line interface."""
    setup_logger()
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 0

    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("操作已取消。", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
