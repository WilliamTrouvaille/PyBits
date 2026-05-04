"""安装逻辑"""

import os
import platform
import shutil
import subprocess
from pathlib import Path

import questionary
from loguru import logger

from .config import (
    CLAUDE_PROJECT_SKILLS_DIR,
    CLAUDE_USER_SKILLS_DIR,
    CODEX_PROJECT_SKILLS_DIR,
    CODEX_USER_SKILLS_DIR,
)
from .models import AgentType, InstallMode, ScopeType, Skill
from .utils import ensure_dir


def install_skill(
    skill: Skill,
    agent: AgentType,
    scope: ScopeType,
    mode: InstallMode,
    force: bool = False,
) -> None:
    """
    安装 skill 到目标目录
    1. 确定目标路径
    2. 检查是否已存在（覆盖提示）
    3. 根据 mode 复制或链接
    """
    # 确定目标 agent 列表
    if agent == AgentType.ALL:
        agents = [AgentType.CLAUDE, AgentType.CODEX]
    else:
        agents = [agent]

    # 对每个 agent 执行安装
    for target_agent in agents:
        target_dir = get_target_dir(target_agent, scope)
        target_path = target_dir / skill.name

        # 检查是否已存在
        if check_existing_skill(target_path) and not force:
            if not prompt_overwrite(skill.name, target_path):
                logger.info(f"跳过安装: {skill.name} -> {target_path}")
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
        except Exception as e:
            logger.error(f"安装失败: {skill.name}, 错误: {e}")
            print(f"✗ 安装失败: {skill.name}, 错误: {e}")

            # link 模式失败时询问是否改用 copy
            if mode == InstallMode.LINK:
                if questionary.confirm("链接创建失败，是否改用复制模式？").ask():
                    try:
                        copy_skill(skill.source_path, target_path)
                        logger.info(f"复制 skill: {skill.name} -> {target_path}")
                        print(f"✓ 安装成功（复制模式）: {skill.name} -> {target_path}")
                    except Exception as copy_error:
                        logger.error(f"复制也失败: {copy_error}")
                        print(f"✗ 复制也失败: {copy_error}")


def get_target_dir(agent: AgentType, scope: ScopeType) -> Path:
    """
    获取目标 skills 目录
    - 根据 agent 和 scope 确定路径
    - 如果目录不存在，自动创建
    """
    if agent == AgentType.CLAUDE:
        target_dir = (
            CLAUDE_USER_SKILLS_DIR
            if scope == ScopeType.USER
            else CLAUDE_PROJECT_SKILLS_DIR
        )
    elif agent == AgentType.CODEX:
        target_dir = (
            CODEX_USER_SKILLS_DIR
            if scope == ScopeType.USER
            else CODEX_PROJECT_SKILLS_DIR
        )
    else:
        raise ValueError(f"不支持的 agent 类型: {agent}")

    # 如果是项目级，检查是否是项目根目录
    if scope == ScopeType.PROJECT:
        cwd = Path.cwd()
        if not check_project_root(cwd):
            print(f"警告: 当前目录 '{cwd}' 不是项目根目录（未找到 .git 或 CLAUDE.md）")
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
    if target.exists():
        shutil.rmtree(target)

    shutil.copytree(source, target)


def link_skill(source: Path, target: Path) -> None:
    """
    创建 skill 链接
    - Windows: 使用 Junction (subprocess call mklink /J)
    - Mac/Linux: 使用 symlink (os.symlink)
    - 错误处理：权限问题，询问是否改用 copy 模式
    """
    if target.exists():
        if target.is_symlink() or target.is_junction():
            target.unlink()
        else:
            shutil.rmtree(target)

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
    return target.exists()


def prompt_overwrite(skill_name: str, target: Path) -> bool:
    """
    提示用户是否覆盖已存在的 skill
    返回 True 表示继续，False 表示取消
    """
    print(f"\n警告：Skill '{skill_name}' 已存在于 {target}")
    return questionary.confirm("是否覆盖？").ask()


def check_project_root(cwd: Path) -> bool:
    """
    检查当前目录是否是项目根目录
    - 检查 .git 或 CLAUDE.md 是否存在
    - 返回 True 表示是项目根目录
    """
    return (cwd / ".git").exists() or (cwd / "CLAUDE.md").exists()
