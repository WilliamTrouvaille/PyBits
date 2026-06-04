"""SKILLS 的安装执行逻辑。"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import questionary
from loguru import logger

from _shared.utils.trash import soft_delete

from .models import InstallMode, ScopeType, Skill
from .utils import Settings, ensure_dir, find_project_root


@dataclass(frozen=True)
class InstallResult:
    """单个 agent 目标目录的一次安装结果。"""

    skill_name: str
    agent: str
    target_path: Path | None
    status: str
    error: str | None = None

    @property
    def installed(self) -> bool:
        return self.status == "installed"


def install_skill(
    skill: Skill,
    agent: str,
    scope: ScopeType,
    mode: InstallMode,
    settings: Settings,
    force: bool = False,
    project_dir: Path | None = None,
) -> list[InstallResult]:
    """
    安装 skill 到一个或多个 agent 的目标目录。

    Args:
        skill: Skill 对象
        agent: 目标 agent 名（setting.yaml 的 agents 键，或 "all"）
        scope: 安装范围
        mode: 安装模式
        settings: 配置对象，提供各 agent 的安装目录
        force: 是否强制覆盖
        project_dir: 项目目录（用于项目级安装）

    Returns:
        每个目标 agent 的安装结果。
    """
    agents = list(settings.agents) if agent == "all" else [agent]
    return [
        _install_skill_for_agent(skill, target_agent, scope, mode, settings, force, project_dir)
        for target_agent in agents
    ]


def _install_skill_for_agent(
    skill: Skill,
    target_agent: str,
    scope: ScopeType,
    mode: InstallMode,
    settings: Settings,
    force: bool,
    project_dir: Path | None,
) -> InstallResult:
    """
    为单个 agent 执行一次 skill 安装。

    Args:
        skill: 待安装的 skill。
        target_agent: 目标 agent 名。
        scope: 安装范围。
        mode: 安装模式。
        settings: SKILLS 运行时配置。
        force: 是否强制覆盖已有目标。
        project_dir: 项目级安装使用的项目目录。

    Returns:
        单个目标 agent 的安装结果。
    """
    try:
        target_dir = get_target_dir(target_agent, scope, settings, project_dir)
    except Exception as exc:
        logger.error(f"安装失败: {skill.name}, agent={target_agent}, 错误: {exc}")
        print(f"✗ 安装失败: {skill.name}, agent={target_agent}, 错误: {exc}")
        return _failed_install_result(skill.name, target_agent, None, exc)

    target_path = target_dir / skill.name
    if _should_skip_existing_skill(skill.name, target_path, force):
        logger.info(f"跳过安装: {skill.name} -> {target_path}")
        return InstallResult(
            skill_name=skill.name,
            agent=target_agent,
            target_path=target_path,
            status="skipped",
        )

    return _install_skill_to_target(skill, target_agent, target_path, mode)


def _should_skip_existing_skill(skill_name: str, target_path: Path, force: bool) -> bool:
    """
    判断已有目标 skill 是否应跳过安装。

    Args:
        skill_name: 待安装 skill 名称。
        target_path: 目标安装路径。
        force: 是否强制覆盖。

    Returns:
        用户拒绝覆盖已有目标时返回 True。
    """
    if force or not check_existing_skill(target_path):
        return False
    return not prompt_overwrite(skill_name, target_path)


def _install_skill_to_target(
    skill: Skill,
    target_agent: str,
    target_path: Path,
    mode: InstallMode,
) -> InstallResult:
    """
    将 skill 写入已经解析好的目标路径。

    Args:
        skill: 待安装的 skill。
        target_agent: 目标 agent 名。
        target_path: 目标安装路径。
        mode: 安装模式。

    Returns:
        安装结果。
    """
    try:
        _apply_install_mode(skill, target_path, mode)
        logger.info(f"{_install_action_label(mode)} skill: {skill.name} -> {target_path}")
        print(f"✓ 安装成功: {skill.name} -> {target_path}")
        return InstallResult(
            skill_name=skill.name,
            agent=target_agent,
            target_path=target_path,
            status="installed",
        )
    except Exception as exc:
        logger.error(f"安装失败: {skill.name}, 错误: {exc}")
        print(f"✗ 安装失败: {skill.name}, 错误: {exc}")

        if mode == InstallMode.LINK and _confirm_copy_fallback():
            return _copy_after_link_failure(skill, target_agent, target_path)

        return _failed_install_result(skill.name, target_agent, target_path, exc)


def _apply_install_mode(skill: Skill, target_path: Path, mode: InstallMode) -> None:
    """
    按安装模式写入目标路径。

    Args:
        skill: 待安装的 skill。
        target_path: 目标安装路径。
        mode: 安装模式。
    """
    if mode == InstallMode.COPY:
        copy_skill(skill.source_path, target_path)
        return
    link_skill(skill.source_path, target_path)


def _install_action_label(mode: InstallMode) -> str:
    """返回用于日志的安装动作名称。"""
    return "复制" if mode == InstallMode.COPY else "链接"


def _confirm_copy_fallback() -> bool:
    """确认 link 模式失败后是否回退到 copy 模式。"""
    return bool(questionary.confirm("链接创建失败，是否改用复制模式？").ask())


def _copy_after_link_failure(
    skill: Skill,
    target_agent: str,
    target_path: Path,
) -> InstallResult:
    """
    link 模式失败后尝试用 copy 模式完成安装。

    Args:
        skill: 待安装的 skill。
        target_agent: 目标 agent 名。
        target_path: 目标安装路径。

    Returns:
        copy 回退的安装结果。
    """
    try:
        copy_skill(skill.source_path, target_path)
        logger.info(f"复制 skill: {skill.name} -> {target_path}")
        print(f"✓ 安装成功（复制模式）: {skill.name} -> {target_path}")
        return InstallResult(
            skill_name=skill.name,
            agent=target_agent,
            target_path=target_path,
            status="installed",
        )
    except Exception as copy_error:
        logger.error(f"复制也失败: {copy_error}")
        print(f"✗ 复制也失败: {copy_error}")
        return _failed_install_result(skill.name, target_agent, target_path, copy_error)


def _failed_install_result(
    skill_name: str,
    agent: str,
    target_path: Path | None,
    error: Exception,
) -> InstallResult:
    """
    构造失败安装结果。

    Args:
        skill_name: 安装失败的 skill 名称。
        agent: 目标 agent 名。
        target_path: 失败时已解析出的目标路径；解析目标目录失败时为 None。
        error: 失败异常。

    Returns:
        失败状态的安装结果。
    """
    return InstallResult(
        skill_name=skill_name,
        agent=agent,
        target_path=target_path,
        status="failed",
        error=str(error),
    )


def get_target_dir(
    agent: str, scope: ScopeType, settings: Settings, project_dir: Path | None = None
) -> Path:
    """
    获取目标 skills 目录。

    Args:
        agent: 目标 agent 名（setting.yaml 的 agents 键）。
        scope: 安装范围。
        settings: 配置对象。
        project_dir: 项目目录（用于项目级安装）。

    Returns:
        目标 skills 目录路径。
    """
    agent_config = settings.agents.get(agent)
    if not agent_config:
        raise ValueError(f"不支持的 agent 类型: {agent}（请在 setting.yaml 的 agents 中配置）")

    if scope == ScopeType.USER:
        configured = agent_config.get("user")
        if not configured:
            raise ValueError(f"agent '{agent}' 缺少 user 安装目录配置")
        target_dir = Path(configured).expanduser()
    else:
        configured = agent_config.get("project")
        if not configured:
            raise ValueError(f"agent '{agent}' 缺少 project 安装目录配置")
        project = project_dir or Path.cwd()
        target_dir = project / configured

        # 项目级安装可能写入任意当前目录，交互确认可避免误装到普通文件夹。
        if not find_project_root(project):
            print(
                f"警告: 目录 '{project}' 不是项目根目录"
                "（未找到 .git、CLAUDE.md、AGENTS.md 或 .agents）"
            )
            if not questionary.confirm("是否继续安装？").ask():
                raise RuntimeError("用户取消安装")

    ensure_dir(target_dir)
    return target_dir


def copy_skill(source: Path, target: Path) -> None:
    """
    复制 skill 目录到目标位置。

    Args:
        source: 源 skill 目录。
        target: 目标 skill 目录。
    """
    if check_existing_skill(target):
        moved_target = soft_delete(target, "skills-install-overwrite")
        logger.info(f"已软删除旧 skill: {target} -> {moved_target}")

    shutil.copytree(source, target)


def link_skill(source: Path, target: Path) -> None:
    """
    创建指向源 skill 目录的链接。

    Args:
        source: 源 skill 目录。
        target: 目标链接路径。
    """
    if check_existing_skill(target):
        moved_target = soft_delete(target, "skills-install-overwrite")
        logger.info(f"已软删除旧 skill: {target} -> {moved_target}")

    system = platform.system()

    if system == "Windows":
        # Windows 普通用户更容易创建 Junction，权限要求通常低于目录 symlink。
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target), str(source)],
            check=True,
            capture_output=True,
        )
        logger.info(f"创建 Junction: {target} -> {source}")
    else:
        os.symlink(source, target)
        logger.info(f"创建 symlink: {target} -> {source}")


def check_existing_skill(target: Path) -> bool:
    """检查目标位置是否已存在 skill。"""
    return target.exists() or target.is_symlink()


def prompt_overwrite(skill_name: str, target: Path) -> bool:
    """
    提示用户是否覆盖已存在的 skill。

    Args:
        skill_name: 待安装 skill 名称。
        target: 已存在的目标路径。

    Returns:
        用户确认覆盖时返回 True。
    """
    print(f"\n警告：Skill '{skill_name}' 已存在于 {target}")
    return bool(questionary.confirm("是否覆盖？").ask())
