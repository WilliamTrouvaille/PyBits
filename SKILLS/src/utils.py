"""工具函数"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml
from loguru import logger

from _shared.utils.trash import soft_delete


def default_excluded_dirs() -> set[str]:
    """扫描时默认排除的目录（setting.yaml 缺失时的回退值）。"""
    return {
        ".git",
        ".github",
        ".gitlab",
        "docs",
        "doc",
        "documentation",
        "tests",
        "test",
        "__tests__",
        "examples",
        "example",
        "demos",
        "demo",
        ".vscode",
        ".idea",
        ".vs",
        "scripts",
        "tools",
        "utils",
    }


def default_agents() -> dict[str, dict[str, str]]:
    """agent 安装目录默认配置（setting.yaml 缺失时的回退值）。"""
    return {
        "claude": {"user": "~/.claude/skills", "project": ".claude/skills"},
        "codex": {"user": "~/.agents/skills", "project": ".agents/skills"},
    }


@dataclass
class Settings:
    """SKILLS 配置"""

    log_level: str = "INFO"
    log_retention_days: int = 30
    default_scan_depth: int = 3
    excluded_dirs: set[str] = field(default_factory=default_excluded_dirs)
    repos_cache_dir: Path | None = None
    logs_dir: Path | None = None
    agents: dict[str, dict[str, str]] = field(default_factory=default_agents)
    workspaces: list[str] = field(default_factory=list)


def load_settings(config_path: Path | None = None) -> Settings:
    """从 YAML 文件加载配置，文件缺失时返回内置默认值。"""
    if config_path is None:
        project_root = Path(__file__).parent.parent.resolve()
        config_path = project_root / "setting.yaml"

    if not config_path.exists():
        return Settings()

    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        return Settings()

    settings = Settings()

    if "log_level" in data:
        settings.log_level = str(data["log_level"])

    if "log_retention_days" in data:
        settings.log_retention_days = int(data["log_retention_days"])

    if "default_scan_depth" in data:
        settings.default_scan_depth = int(data["default_scan_depth"])

    if "excluded_dirs" in data and isinstance(data["excluded_dirs"], list):
        settings.excluded_dirs = set(data["excluded_dirs"])

    if data.get("repos_cache_dir"):
        settings.repos_cache_dir = Path(data["repos_cache_dir"])

    if data.get("logs_dir"):
        settings.logs_dir = Path(data["logs_dir"])

    if isinstance(data.get("agents"), dict):
        settings.agents = {
            str(agent): {str(scope): str(path) for scope, path in mapping.items()}
            for agent, mapping in data["agents"].items()
            if isinstance(mapping, dict)
        }

    if isinstance(data.get("workspaces"), list):
        settings.workspaces = [str(item) for item in data["workspaces"]]

    return settings


def get_effective_paths(settings: Settings, project_root: Path) -> dict[str, Path]:
    """合并配置值和运行时派生路径。"""
    return {
        "repos_cache_dir": settings.repos_cache_dir or project_root / "_repos_cache",
        "logs_dir": settings.logs_dir or project_root / "logs",
        "repos_json_path": project_root / ".repos.json",
        "repos_local_json_path": project_root / ".repos.local.json",
        "recent_installs_path": project_root / ".recent_installs.json",
    }


def configure_git_proxy(proxy: str) -> dict[str, str]:
    """配置 git 代理环境变量"""
    return {
        "http_proxy": proxy,
        "https_proxy": proxy,
    }


def ensure_dir(path: Path) -> None:
    """确保目录存在, 不存在则创建"""
    path.mkdir(parents=True, exist_ok=True)


def generate_timestamped_cache_dir_name(owner: str, repo: str) -> str:
    """
    生成带时间戳的缓存目录名
    格式: {owner}_{repo}_{YYYYMMDD}_{HHMMSS}
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{owner}_{repo}_{timestamp}"


def sanitize_skill_name(name: str) -> str:
    """
    清理 skill 名称中的非法字符
    - 替换非字母数字、下划线、连字符的字符为下划线
    - 返回清理后的名称
    """
    return re.sub(r"[^\w\-]", "_", name)


def recursive_find_skills(
    root_path: Path,
    max_depth: int = 3,
    excluded_dirs: set[str] | None = None,
) -> list[Path]:
    """
    递归查找所有包含 SKILL.md 的目录

    Args:
        root_path: 根目录
        max_depth: 最大扫描深度
        excluded_dirs: 排除的目录名集合

    Returns:
        包含 SKILL.md 的目录路径列表
    """
    if excluded_dirs is None:
        excluded_dirs = default_excluded_dirs()

    skill_dirs = []
    visited_real_paths: set[Path] = set()

    def _real_path(path: Path) -> Path:
        """Return a stable directory identity for duplicate and symlink checks."""
        try:
            return path.resolve()
        except OSError:
            return path

    def _is_scannable_dir(path: Path) -> bool:
        if path.is_symlink():
            return False
        if not path.is_dir():
            return False
        if path.name.startswith(".") or path.name.startswith("_"):
            return False
        return path.name not in excluded_dirs

    def _scan(path: Path, current_depth: int) -> None:
        if current_depth > max_depth:
            return

        real_path = _real_path(path)
        if real_path in visited_real_paths:
            return
        visited_real_paths.add(real_path)

        # 检查当前目录是否包含 SKILL.md
        if (path / "SKILL.md").exists():
            nested_skills_dir = path / "skills"
            if current_depth == 0 and _is_scannable_dir(nested_skills_dir):
                found_count = len(skill_dirs)
                _scan(nested_skills_dir, current_depth + 1)
                if len(skill_dirs) > found_count:
                    return

            skill_dirs.append(path)
            # 找到 skill 后不再向下扫描
            return

        # 递归扫描子目录
        try:
            children = sorted(
                (item for item in path.iterdir() if _is_scannable_dir(item)),
                key=lambda item: item.name.lower(),
            )

            for item in children:
                _scan(item, current_depth + 1)
        except PermissionError:
            logger.warning(f"无权限访问目录: {path}")

    _scan(root_path, 0)
    return skill_dirs


def extract_skills_to_flat_structure(
    source_repo_path: Path,
    target_cache_dir: Path,
    max_depth: int = 3,
    excluded_dirs: set[str] | None = None,
) -> tuple[list[Path], dict[str, list[Path]]]:
    """
    从源仓库提取 skills 到平铺的缓存目录

    Args:
        source_repo_path: 源仓库路径
        target_cache_dir: 目标缓存目录
        max_depth: 扫描深度
        excluded_dirs: 排除的目录名集合

    Returns:
        (成功提取的 skill 路径列表, 名称冲突字典)
    """
    from .skill import parse_skill_metadata

    # 递归查找所有 skill 目录
    skill_dirs = recursive_find_skills(source_repo_path, max_depth, excluded_dirs)

    # 检测名称冲突
    skill_names: dict[str, list[Path]] = {}
    for skill_dir in skill_dirs:
        skill_md = skill_dir / "SKILL.md"
        metadata = parse_skill_metadata(skill_md)
        if not metadata:
            continue

        skill_name = metadata.get("name", skill_dir.name)
        if skill_name not in skill_names:
            skill_names[skill_name] = []
        skill_names[skill_name].append(skill_dir)

    # 找出冲突的名称
    conflicts = {name: paths for name, paths in skill_names.items() if len(paths) > 1}
    if conflicts:
        return [], conflicts

    # 创建目标缓存目录
    ensure_dir(target_cache_dir)

    # 提取 skills 到平铺结构
    extracted_skills = []
    for skill_dir in skill_dirs:
        skill_md = skill_dir / "SKILL.md"
        metadata = parse_skill_metadata(skill_md)
        if not metadata:
            logger.warning(f"跳过无效 skill: {skill_dir}")
            continue

        skill_name = metadata.get("name")
        if not skill_name:
            logger.warning(f"Skill 缺少 name 字段: {skill_dir}")
            continue

        # 清理 skill 名称
        sanitized_name = sanitize_skill_name(skill_name)
        if sanitized_name != skill_name:
            logger.warning(f"Skill 名称包含非法字符, 已清理: '{skill_name}' -> '{sanitized_name}'")

        # 复制到目标目录
        target_skill_dir = target_cache_dir / sanitized_name
        if target_skill_dir.exists():
            moved_dir = soft_delete(target_skill_dir, "skills-extract-overwrite")
            logger.info(f"已软删除旧缓存 skill: {target_skill_dir} -> {moved_dir}")

        shutil.copytree(skill_dir, target_skill_dir)
        extracted_skills.append(target_skill_dir)
        logger.debug(f"提取 skill: {skill_dir} -> {target_skill_dir}")

    # 复制 README.md (如果存在)
    readme_path = source_repo_path / "README.md"
    if readme_path.exists():
        shutil.copy2(readme_path, target_cache_dir / "README.md")
        logger.debug("复制 README.md 到缓存目录")

    return extracted_skills, {}


def find_project_root(start_dir: Path) -> Path | None:
    """
    查找项目根目录

    Args:
        start_dir: 起始目录

    Returns:
        项目根目录路径，如果未找到则返回 None
    """
    indicators = [
        ".git",
        "CLAUDE.md",
        "AGENTS.md",
        "pyproject.toml",
        ".agents",
        ".codex",
    ]

    for directory in [start_dir, *list(start_dir.parents)]:
        if any((directory / indicator).exists() for indicator in indicators):
            return directory

    return None
