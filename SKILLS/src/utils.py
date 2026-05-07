"""工具函数"""

from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger


def setup_logger(
    logs_dir: Path | None = None, log_retention_days: int = 30, log_level: str = "INFO"
) -> None:
    """
    初始化 loguru 日志

    Args:
        logs_dir: 日志目录路径
        log_retention_days: 日志保留天数
        log_level: 日志级别
    """
    logger.remove()

    # 控制台输出: WARNING 及以上
    logger.add(
        sys.stderr,
        level="WARNING",
        format="<level>{level: <8}</level> | <level>{message}</level>",
    )

    # 确保日志目录存在
    logs_path = logs_dir or Path(__file__).parent.parent / "logs"
    ensure_dir(logs_path)

    # 文件输出: INFO 及以上, 按日期分割
    log_file = logs_path / "skills_{time:YYYY-MM-DD}.log"
    logger.add(
        log_file,
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="00:00",
        retention=f"{log_retention_days} days",
        encoding="utf-8",
    )

    # 清理旧日志
    clean_old_logs(logs_path, log_retention_days)


def configure_git_proxy(proxy: str) -> dict[str, str]:
    """配置 git 代理环境变量"""
    return {
        "http_proxy": proxy,
        "https_proxy": proxy,
    }


def normalize_repo_name(url_or_path: str) -> str:
    """
    规范化仓库名称
    - GitHub: owner/repo
    - 本地: 目录名
    """
    if "/" in url_or_path and not url_or_path.startswith(("http://", "https://")):
        return url_or_path

    if url_or_path.startswith(("http://", "https://")):
        parts = url_or_path.rstrip("/").split("/")
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1].replace('.git', '')}"

    return Path(url_or_path).name


def ensure_dir(path: Path) -> None:
    """确保目录存在, 不存在则创建"""
    path.mkdir(parents=True, exist_ok=True)


def clean_old_logs(logs_dir: Path, retention_days: int) -> None:
    """清理超过保留期限的日志文件"""
    if not logs_dir.exists():
        return

    cutoff_date = datetime.now() - timedelta(days=retention_days)

    for log_file in logs_dir.glob("skills_*.log"):
        try:
            # 从文件名提取日期
            date_str = log_file.stem.replace("skills_", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d")

            if file_date < cutoff_date:
                log_file.unlink()
                logger.debug(f"删除旧日志文件: {log_file}")
        except (ValueError, OSError) as e:
            logger.warning(f"清理日志文件失败: {log_file}, 错误: {e}")


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
        excluded_dirs = {
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
            logger.warning(
                f"Skill 名称包含非法字符, 已清理: '{skill_name}' -> '{sanitized_name}'"
            )

        # 复制到目标目录
        target_skill_dir = target_cache_dir / sanitized_name
        if target_skill_dir.exists():
            shutil.rmtree(target_skill_dir)

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
        ".codex",
    ]

    for directory in [start_dir] + list(start_dir.parents):
        if any((directory / indicator).exists() for indicator in indicators):
            return directory

    return None
