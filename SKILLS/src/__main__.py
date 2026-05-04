"""Command-line entry point for SKILLS."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import questionary

from .installer import install_skill
from .models import AgentType, InstallMode, RepositoryType, ScopeType, Skill
from .persistence import (
    add_repository,
    get_repository,
    load_repositories,
    remove_repository,
    repository_exists,
)
from .repository import parse_github_url, register_github_repo, register_local_repo, scan_repository
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
    register_parser.add_argument("source", help="GitHub URL/owner-repo shorthand or local path.")
    register_parser.add_argument("--name", help="Repository name for local registrations.")
    register_parser.add_argument("--proxy", help="HTTP(S) proxy used when cloning GitHub repositories.")
    register_type = register_parser.add_mutually_exclusive_group()
    register_type.add_argument("--github", action="store_true", help="Treat source as GitHub repository.")
    register_type.add_argument("--local", action="store_true", help="Treat source as local directory.")
    register_parser.set_defaults(func=handle_register)

    list_parser = subparsers.add_parser(
        "ls",
        aliases=["list"],
        help="List registered repositories.",
    )
    list_parser.set_defaults(func=handle_list)

    remove_parser = subparsers.add_parser("remove", help="Remove a registered repository.")
    remove_parser.add_argument("name", help="Registered repository name.")
    remove_parser.set_defaults(func=handle_remove)

    scan_parser = subparsers.add_parser("scan", help="Scan registered repositories for skills.")
    scan_parser.add_argument("repository", nargs="?", help="Repository name. Omit to scan all.")
    scan_parser.set_defaults(func=handle_scan)

    install_parser = subparsers.add_parser("install", help="Install skills from a registered repository.")
    install_parser.add_argument("repository", nargs="?", help="Registered repository name.")
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
    install_parser.add_argument("--force", action="store_true", help="Overwrite existing target skills.")
    install_parser.set_defaults(func=handle_install)

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
    else:
        owner, repo_short_name = parse_github_url(source)
        repo_name = f"{owner}/{repo_short_name}"
        if repository_exists(repo_name):
            print(f"仓库已存在: {repo_name}", file=sys.stderr)
            return 1
        repo = register_github_repo(source, args.proxy)

    add_repository(repo)
    print(f"已注册仓库: {repo.name} ({repo.type.value})")
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
        print(f"已移除仓库: {args.name}")
        return 0

    print(f"仓库不存在: {args.name}", file=sys.stderr)
    return 1


def handle_scan(args: argparse.Namespace) -> int:
    """Scan registered repositories for skills."""
    if args.repository:
        repo = get_repository(args.repository)
        if not repo:
            print(f"仓库不存在: {args.repository}", file=sys.stderr)
            return 1
        repos = [repo]
    else:
        repos = load_repositories()

    if not repos:
        print("未找到已注册仓库。")
        return 0

    for repo in repos:
        skills = scan_repository(repo)
        print(f"{repo.name}: {len(skills)} 个 skill")
        for skill in skills:
            print(f"  {skill.name}\t{skill.description}")
    return 0


def handle_install(args: argparse.Namespace) -> int:
    """Install selected skills."""
    if not args.repository and not args.skills:
        return interactive_install()

    if not args.repository:
        print("缺少仓库名称。示例: SKILLS install repo/name skill-name --scope user", file=sys.stderr)
        return 2

    if not args.skills:
        print("缺少 skill 名称。无参数运行 `SKILLS install` 可进入交互式安装。", file=sys.stderr)
        return 2

    if not args.scope:
        print("非交互式安装必须指定 --scope <user|project>。", file=sys.stderr)
        return 2

    repo = get_repository(args.repository)
    if not repo:
        print(f"仓库不存在: {args.repository}", file=sys.stderr)
        return 1

    available_skills = {skill.name: skill for skill in scan_repository(repo)}
    missing_skills = [skill_name for skill_name in args.skills if skill_name not in available_skills]
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
    selected_repo_label = questionary.select("选择要安装的仓库:", choices=repo_labels).ask()
    if not selected_repo_label:
        print("安装已取消。")
        return 1

    repo = repos[repo_labels.index(selected_repo_label)]
    skills = scan_repository(repo)
    if not skills:
        print(f"仓库 {repo.name} 中未找到任何合法 skill。")
        return 1

    skill_labels = [format_skill_label(skill) for skill in skills]
    selected_skill_labels = questionary.checkbox("选择要安装的 skills:", choices=skill_labels).ask()
    if not selected_skill_labels:
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
        print("安装已取消。")
        return 1

    selected_skills = [skills[skill_labels.index(label)] for label in selected_skill_labels]
    print()
    print("安装参数:")
    print(f"  仓库: {repo.name}")
    print(f"  Skills: {', '.join(skill.name for skill in selected_skills)}")
    print(f"  Agent: {agent_value}")
    print(f"  Scope: {scope_value}")
    print(f"  Mode: {mode_value}")

    if not questionary.confirm("是否继续安装？").ask():
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


def format_skill_label(skill: Skill) -> str:
    """Format a skill for interactive selection."""
    return f"{skill.name} - {skill.description}"


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
