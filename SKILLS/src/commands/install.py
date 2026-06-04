"""
SKILLS 安装命令处理器。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import questionary
from loguru import logger
from questionary import Choice, Separator

from ..installer import install_skill
from ..models import InstallMode, Repository, ScopeType, Skill
from ..persistence import get_repository, load_repositories
from ..recent import RecentSkillRef, load_recent_refs, record_recent
from ..repository import scan_repository
from ..utils import Settings


def handle_install(args: argparse.Namespace, settings: Settings, paths: dict[str, Path]) -> int:
    """
    处理非交互式或交互式 skill 安装命令。

    Args:
        args: argparse 解析出的命名空间。
        settings: SKILLS 运行时配置。
        paths: 运行时派生路径集合。

    Returns:
        进程退出码。
    """
    if not args.repository and not args.skills:
        return interactive_install(settings, paths)

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

    repo = get_repository(args.repository, paths["repos_json_path"], paths["repos_local_json_path"])
    if not repo:
        print(f"仓库不存在: {args.repository}", file=sys.stderr)
        return 1

    available_skills = {
        skill.name: skill
        for skill in scan_repository(repo, settings.default_scan_depth, settings.excluded_dirs)
    }
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

    agent = args.agent
    scope = ScopeType(args.scope)
    mode = InstallMode(args.mode)
    project_dir = args.project_dir or Path.cwd()

    skill_names_str = ", ".join(args.skills)
    logger.info(
        f"[用户操作] 安装 skills: {skill_names_str} "
        f"(agent={agent}, scope={scope.value}, mode={mode.value}, project_dir={project_dir})"
    )

    for skill_name in args.skills:
        install_results = install_skill(
            available_skills[skill_name], agent, scope, mode, settings, args.force, project_dir
        )
        if install_results and all(result.installed for result in install_results):
            record_recent(
                skill_name,
                paths["recent_installs_path"],
                available_skills[skill_name].repository_name,
            )
        else:
            return 1

    return 0


def interactive_install(settings: Settings, paths: dict[str, Path]) -> int:
    """
    运行交互式安装流程。

    Args:
        settings: SKILLS 运行时配置。
        paths: 运行时派生路径集合。

    Returns:
        进程退出码。
    """
    repos = load_repositories(paths["repos_json_path"], paths["repos_local_json_path"])
    if not repos:
        print("未找到已注册仓库，请先使用 `SKILLS register` 注册仓库。")
        return 1

    selected_source = select_repository_or_recent(repos, paths)
    if not selected_source:
        logger.info("[用户操作] 取消安装 (未选择仓库)")
        print("安装已取消。")
        return 1

    if isinstance(selected_source, RecentSkillRef):
        skill = resolve_recent_skill(selected_source, repos, settings)
        if skill is None:
            print(f"最近安装记录已失效，当前已注册仓库中未找到: {selected_source.name}")
            return 1
        repo_display = f"{RECENT_LABEL} ({skill.repository_name})"
        selected_skills = [skill]
    else:
        repo_display = selected_source.name
        skills = scan_repository(
            selected_source,
            settings.default_scan_depth,
            settings.excluded_dirs,
            log_summary=False,
        )
        if not skills:
            print(f"仓库 {selected_source.name} 中未找到任何合法 skill。")
            return 1

        skill_choices = [Choice(title=format_skill_label(skill), value=skill) for skill in skills]
        selected_skills = questionary.checkbox(
            "选择要安装的 skills:",
            choices=skill_choices,
            instruction="(方向键移动，空格选择，a 全选，i 反选)",
        ).ask()
        if not selected_skills:
            logger.info("[用户操作] 取消安装 (未选择 skills)")
            print("安装已取消。")
            return 1

    install_options = select_install_options(settings)
    if install_options is None:
        logger.info("[用户操作] 取消安装 (未完成配置)")
        print("安装已取消。")
        return 1
    agent_value, scope_value, mode_value = install_options

    skill_names_str = ", ".join(skill.name for skill in selected_skills)
    logger.info(
        f"[用户操作] 安装 skills: {skill_names_str} "
        f"(agent={agent_value}, scope={scope_value}, mode={mode_value})"
    )

    print()
    print("安装参数:")
    print(f"  仓库: {repo_display}")
    print(f"  Skills: {skill_names_str}")
    print(f"  Agent: {agent_value}")
    print(f"  Scope: {scope_value}")
    print(f"  Mode: {mode_value}")

    if not questionary.confirm("是否继续安装？").ask():
        logger.info("[用户操作] 取消安装 (用户拒绝确认)")
        print("安装已取消。")
        return 1

    for skill in selected_skills:
        install_results = install_skill(
            skill,
            agent_value,
            ScopeType(scope_value),
            InstallMode(mode_value),
            settings,
        )
        if install_results and all(result.installed for result in install_results):
            record_recent(skill.name, paths["recent_installs_path"], skill.repository_name)
        else:
            return 1

    return 0


def format_skill_label(
    skill: Skill,
    max_description_length: int = 100,
    *,
    include_repository: bool = False,
) -> str:
    """
    格式化交互选择中的 skill 展示文案。

    Args:
        skill: 待展示的 skill。
        max_description_length: 描述最大长度，超出时截断。
        include_repository: 是否在名称后展示来源仓库。

    Returns:
        展示用标签字符串。
    """
    description = skill.description
    if len(description) > max_description_length:
        description = description[:max_description_length] + "..."
    name = skill.name
    if include_repository:
        name = f"{name} ({skill.repository_name})"
    return f"{name} - {description}"


RECENT_LABEL = "[最近安装]"
REPOSITORY_LABEL = "[从仓库安装]"


def select_repository_or_recent(
    repos: list[Repository],
    paths: dict[str, Path],
) -> Repository | RecentSkillRef | None:
    """
    选择要安装的仓库或最近安装 skill。

    Args:
        repos: 已注册仓库列表。
        paths: 运行时派生路径集合。

    Returns:
        被选中的仓库对象、最近安装记录，或取消选择时的 None。
    """
    recent_refs = load_recent_refs(paths["recent_installs_path"])
    choices = build_install_source_choices(repos, recent_refs)
    return questionary.select("选择要安装的仓库:", choices=choices).ask()


def build_install_source_choices(
    repos: list[Repository],
    recent_refs: list[RecentSkillRef],
) -> list[Choice | Separator]:
    """构建交互安装第一层菜单，最近安装 skill 可直接选择。"""
    choices: list[Choice | Separator] = []
    if recent_refs:
        choices.append(Separator(RECENT_LABEL))
        choices.extend(
            Choice(
                title=f"  {format_recent_ref_label(ref)}",
                value=ref,
            )
            for ref in recent_refs
        )

    choices.append(Separator(REPOSITORY_LABEL))
    repo_choices: list[Choice] = [
        Choice(title=f"{repo.name} ({repo.type.value})", value=repo) for repo in repos
    ]
    choices.extend(repo_choices)
    return choices


def format_recent_ref_label(ref: RecentSkillRef) -> str:
    """格式化第一层菜单里的最近安装记录。"""
    if ref.repository_name:
        return f"{ref.name} ({ref.repository_name})"
    return ref.name


def resolve_recent_skill(
    ref: RecentSkillRef,
    repos: list[Repository],
    settings: Settings,
    skills_by_repo: dict[str, list[Skill]] | None = None,
) -> Skill | None:
    """
    将最近安装记录解析为当前可安装的 Skill。

    Args:
        ref: 最近安装记录。
        repos: 已注册仓库列表。
        settings: SKILLS 运行时配置。
        skills_by_repo: 可选的仓库扫描缓存。

    Returns:
        找到的 skill；记录已失效时返回 None。
    """
    repos_by_name = {repo.name: repo for repo in repos}
    if skills_by_repo is None:
        skills_by_repo = {}

    def find_skill_in_repo(repo: Repository, skill_name: str) -> Skill | None:
        if repo.name not in skills_by_repo:
            skills_by_repo[repo.name] = scan_repository(
                repo,
                settings.default_scan_depth,
                settings.excluded_dirs,
                log_summary=False,
            )
        for skill in skills_by_repo[repo.name]:
            if skill.name == skill_name:
                return skill
        return None

    if ref.repository_name is not None:
        repo = repos_by_name.get(ref.repository_name)
        return find_skill_in_repo(repo, ref.name) if repo is not None else None

    for repo in repos:
        skill = find_skill_in_repo(repo, ref.name)
        if skill is not None:
            return skill
    return None


def select_install_options(settings: Settings) -> tuple[str, str, str] | None:
    """
    选择交互安装所需的 agent、scope 和 mode 参数。

    Args:
        settings: SKILLS 运行时配置。

    Returns:
        三个安装参数组成的元组；任一项取消时返回 None。
    """
    agent_value = questionary.select(
        "选择目标 agent:",
        choices=[*settings.agents, "all"],
        default="all",
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
        return None
    return agent_value, scope_value, mode_value
