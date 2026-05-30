"""
SKILLS 状态命令处理器。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger

from ..persistence import load_repositories
from ..utils import Settings


def handle_status(args: argparse.Namespace, settings: Settings, paths: dict[str, Path]) -> int:
    """
    展示已注册仓库和已安装的 skill。

    Args:
        args: argparse 解析出的命名空间。
        settings: SKILLS 运行时配置。
        paths: 运行时派生路径集合。

    Returns:
        进程退出码。
    """
    repos = load_repositories(paths["repos_json_path"], paths["repos_local_json_path"])
    print(f"已注册仓库: {len(repos)} 个")
    for repo in repos:
        timestamp = repo.registered_at.strftime("%Y-%m-%d %H:%M:%S")
        print(f"  {repo.name} ({repo.type.value}, {timestamp})")

    print("\n已安装 skills:")

    def scan_skills_dir(path: Path) -> list[str]:
        if not path.exists():
            return []
        return sorted(d.name for d in path.iterdir() if d.is_dir() and not d.name.startswith("."))

    def print_skill_list(skills: list[str]) -> None:
        if skills:
            for skill in skills:
                print(f"    {skill}")
        else:
            print("    无")

    # 用户级：遍历配置中的每个 agent 的 user 目录
    print("  用户级:")
    for agent, mapping in settings.agents.items():
        user_dir = mapping.get("user")
        if not user_dir:
            continue
        print(f"\n  ({agent}) {user_dir}:")
        print_skill_list(scan_skills_dir(Path(user_dir).expanduser()))

    # 项目级：在 workspaces 内先发现项目根，再按项目根分组展示。
    project_roots = discover_workspace_project_roots(settings)
    for project_root in project_roots:
        print(f"\n  项目级 ({project_root}):")
        for agent, mapping in settings.agents.items():
            project_subdir = mapping.get("project")
            if not project_subdir:
                continue
            print(f"    ({agent}) {project_subdir}:")
            skills = scan_skills_dir(project_root / project_subdir)
            if skills:
                for skill in skills:
                    print(f"      {skill}")
            else:
                print("      无")

    return 0


def discover_workspace_project_roots(settings: Settings) -> list[Path]:
    """
    从配置的 workspaces 中发现项目根目录。

    Args:
        settings: SKILLS 运行时配置。

    Returns:
        包含项目级 skill 安装目录的项目根目录列表。
    """
    project_markers = project_marker_names(settings)
    if not project_markers:
        return []

    discovered: dict[Path, Path] = {}
    home_root = Path.home().resolve()
    for workspace in settings.workspaces:
        workspace_root = Path(workspace).expanduser()
        for project_root in scan_workspace_project_roots(
            workspace_root,
            project_markers,
            settings.default_scan_depth,
            settings.excluded_dirs,
        ):
            resolved = project_root.resolve()
            if resolved == home_root or not project_root_has_installed_skills(
                project_root, settings
            ):
                continue
            discovered.setdefault(resolved, project_root)

    return [discovered[key] for key in sorted(discovered)]


def project_marker_names(settings: Settings) -> set[str]:
    """
    获取项目级 skill 目录配置的首级目录名。

    Args:
        settings: SKILLS 运行时配置。

    Returns:
        可作为项目 marker 的目录名集合。
    """
    markers: set[str] = set()
    for mapping in settings.agents.values():
        project_subdir = mapping.get("project")
        if not project_subdir:
            continue
        parts = Path(project_subdir).parts
        if parts:
            markers.add(parts[0])
    return markers


def project_root_has_installed_skills(project_root: Path, settings: Settings) -> bool:
    """
    判断项目根目录下是否存在已安装的项目级 skill。

    Args:
        project_root: 候选项目根目录。
        settings: SKILLS 运行时配置。

    Returns:
        任一项目级 skill 目录包含可见子目录时返回 True。
    """
    for mapping in settings.agents.values():
        project_subdir = mapping.get("project")
        if project_subdir and has_visible_skill_dir(project_root / project_subdir):
            return True
    return False


def has_visible_skill_dir(path: Path) -> bool:
    """
    判断目录中是否存在非隐藏 skill 子目录。

    Args:
        path: 待检查的 skill 安装目录。

    Returns:
        存在非隐藏子目录时返回 True。
    """
    if not path.is_dir():
        return False
    try:
        return any(child.is_dir() and not child.name.startswith(".") for child in path.iterdir())
    except OSError as exc:
        logger.warning(f"无法读取 skills 目录: {path} ({exc})")
        return False


def scan_workspace_project_roots(
    workspace_root: Path,
    project_markers: set[str],
    max_depth: int,
    excluded_dirs: set[str],
) -> list[Path]:
    """
    扫描工作区中的项目 marker 目录并返回其父级项目根目录。

    Args:
        workspace_root: 工作区根目录。
        project_markers: 项目 marker 目录名集合。
        max_depth: 最大扫描深度。
        excluded_dirs: 扫描时排除的目录名集合。

    Returns:
        去重后的项目根目录列表。
    """
    if max_depth < 1 or not workspace_root.is_dir():
        return []

    roots: dict[Path, Path] = {}

    def visit(directory: Path, depth: int) -> None:
        try:
            children = sorted(directory.iterdir(), key=lambda path: path.name)
        except OSError as exc:
            logger.warning(f"无法扫描工作区目录: {directory} ({exc})")
            return

        for child in children:
            if not child.is_dir() or child.is_symlink():
                continue
            if child.name in excluded_dirs:
                continue
            if child.name in project_markers:
                roots.setdefault(child.parent.resolve(), child.parent)
                continue
            if depth < max_depth:
                visit(child, depth + 1)

    visit(workspace_root, 0)
    return [roots[key] for key in sorted(roots)]
