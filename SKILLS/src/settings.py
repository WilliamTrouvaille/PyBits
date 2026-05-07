"""配置加载和管理"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Settings:
    """SKILLS 配置"""

    log_level: str = "INFO"
    log_retention_days: int = 30
    default_scan_depth: int = 3
    excluded_dirs: set[str] = field(
        default_factory=lambda: {
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
    )
    repos_cache_dir: Path | None = None
    logs_dir: Path | None = None


def load_settings(config_path: Path | None = None) -> Settings:
    """
    从 YAML 文件加载配置

    Args:
        config_path: 配置文件路径，默认为 SKILLS/settings.yaml

    Returns:
        Settings 对象

    Raises:
        yaml.YAMLError: 配置文件格式错误
    """
    if config_path is None:
        project_root = Path(__file__).parent.parent.resolve()
        config_path = project_root / "settings.yaml"

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

    if "repos_cache_dir" in data and data["repos_cache_dir"]:
        settings.repos_cache_dir = Path(data["repos_cache_dir"])

    if "logs_dir" in data and data["logs_dir"]:
        settings.logs_dir = Path(data["logs_dir"])

    return settings


def get_effective_paths(settings: Settings, project_root: Path) -> dict[str, Path]:
    """
    合并配置值和运行时派生值

    Args:
        settings: Settings 对象
        project_root: 项目根目录

    Returns:
        包含所有有效路径的字典
    """
    return {
        "repos_cache_dir": settings.repos_cache_dir or project_root / "_repos_cache",
        "logs_dir": settings.logs_dir or project_root / "logs",
        "repos_json_path": project_root / ".repos.json",
        "repos_local_json_path": project_root / ".repos.local.json",
    }
