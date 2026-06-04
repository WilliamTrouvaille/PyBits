"""安装逻辑"""

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
    安装 skill 到目标目录
    1. 确定目标路径
    2. 检查是否已存在（覆盖提示）
    3. 根据 mode 复制或链接

    Args:
        skill: Skill 对象
        agent: 目标 agent 名（setting.yaml 的 agents 键，或 "all"）
        scope: 安装范围
        mode: 安装模式
        settings: 配置对象，提供各 agent 的安装目录
        force: 是否强制覆盖
        project_dir: 项目目录（用于项目级安装）
    """
    # 确定目标 agent 列表
    agents = list(settings.agents) if agent == "all" else [agent]

    results: list[InstallResult] = []

    # 对每个 agent 执行安装
    for target_agent in agents:
        try:
            target_dir = get_target_dir(target_agent, scope, settings, project_dir)
        except Exception as e:
            logger.error(f"安装失败: {skill.name}, agent={target_agent}, 错误: {e}")
            print(f"✗ 安装失败: {skill.name}, agent={target_agent}, 错误: {e}")
            results.append(
                InstallResult(
                    skill_name=skill.name,
                    agent=target_agent,
                    target_path=None,
                    status="failed",
                    error=str(e),
                )
            )
            continue

        target_path = target_dir / skill.name

        # 检查是否已存在
        if (
            check_existing_skill(target_path)
            and not force
            and not prompt_overwrite(skill.name, target_path)
        ):
            logger.info(f"跳过安装: {skill.name} -> {target_path}")
            results.append(
                InstallResult(
                    skill_name=skill.name,
                    agent=target_agent,
                    target_path=target_path,
                    status="skipped",
                )
            )
            continue

        # 执行安装
        try:
            if mode == InstallMode.COPY:
                copy_skill(skill.source_path, target_path)
                logger.info(f"复制 skill: {skill.name} -> {target_path}")
            else:
                link_skill(skill.source_path, target_path)
                logger.info(f"链接 skill: {skill.name} -> {target_path}")

            print(f"✓ 安装成功: {skill.name} -> {target_path}")
            results.append(
                InstallResult(
                    skill_name=skill.name,
                    agent=target_agent,
                    target_path=target_path,
                    status="installed",
                )
            )
        except Exception as e:
            logger.error(f"安装失败: {skill.name}, 错误: {e}")
            print(f"✗ 安装失败: {skill.name}, 错误: {e}")

            # link 模式失败时询问是否改用 copy
            if (
                mode == InstallMode.LINK
                and questionary.confirm("链接创建失败，是否改用复制模式？").ask()
            ):
                try:
                    copy_skill(skill.source_path, target_path)
                    logger.info(f"复制 skill: {skill.name} -> {target_path}")
                    print(f"✓ 安装成功（复制模式）: {skill.name} -> {target_path}")
                    results.append(
                        InstallResult(
                            skill_name=skill.name,
                            agent=target_agent,
                            target_path=target_path,
                            status="installed",
                        )
                    )
                except Exception as copy_error:
                    logger.error(f"复制也失败: {copy_error}")
                    print(f"✗ 复制也失败: {copy_error}")
                    results.append(
                        InstallResult(
                            skill_name=skill.name,
                            agent=target_agent,
                            target_path=target_path,
                            status="failed",
                            error=str(copy_error),
                        )
                    )
            else:
                results.append(
                    InstallResult(
                        skill_name=skill.name,
                        agent=target_agent,
                        target_path=target_path,
                        status="failed",
                        error=str(e),
                    )
                )

    return results


def get_target_dir(
    agent: str, scope: ScopeType, settings: Settings, project_dir: Path | None = None
) -> Path:
    """
    获取目标 skills 目录
    - 根据 agent 和 scope 从 settings.agents 解析路径
    - 如果目录不存在，自动创建

    Args:
        agent: 目标 agent 名（setting.yaml 的 agents 键）
        scope: 安装范围
        settings: 配置对象
        project_dir: 项目目录（用于项目级安装）

    Returns:
        目标 skills 目录路径
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

        # 检查是否是项目根目录
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
    复制 skill 目录
    - 使用 shutil.copytree
    - 覆盖已存在的目录
    """
    if check_existing_skill(target):
        moved_target = soft_delete(target, "skills-install-overwrite")
        logger.info(f"已软删除旧 skill: {target} -> {moved_target}")

    shutil.copytree(source, target)


def link_skill(source: Path, target: Path) -> None:
    """
    创建 skill 链接
    - Windows: 使用 Junction (subprocess call mklink /J)
    - Mac/Linux: 使用 symlink (os.symlink)
    - 错误处理：权限问题，询问是否改用 copy 模式
    """
    if check_existing_skill(target):
        moved_target = soft_delete(target, "skills-install-overwrite")
        logger.info(f"已软删除旧 skill: {target} -> {moved_target}")

    system = platform.system()

    if system == "Windows":
        # 使用 Junction
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target), str(source)],
            check=True,
            capture_output=True,
        )
        logger.info(f"创建 Junction: {target} -> {source}")
    else:
        # Mac/Linux 使用 symlink
        os.symlink(source, target)
        logger.info(f"创建 symlink: {target} -> {source}")


def check_existing_skill(target: Path) -> bool:
    """检查目标位置是否已存在 skill"""
    return target.exists() or target.is_symlink()


def prompt_overwrite(skill_name: str, target: Path) -> bool:
    """
    提示用户是否覆盖已存在的 skill
    返回 True 表示继续，False 表示取消
    """
    print(f"\n警告：Skill '{skill_name}' 已存在于 {target}")
    return questionary.confirm("是否覆盖？").ask()
