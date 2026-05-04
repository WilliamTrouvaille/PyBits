"""配置和常量定义"""

import os
from pathlib import Path

# 项目路径
PROJECT_ROOT: Path = Path(__file__).parent.parent.resolve()
REPOS_CACHE_DIR: Path = PROJECT_ROOT / "_repos_cache"
LOGS_DIR: Path = PROJECT_ROOT / "logs"
REPOS_JSON_PATH: Path = PROJECT_ROOT / ".repos.json"

# Agent skills 目录
CLAUDE_USER_SKILLS_DIR: Path = Path.home() / ".claude" / "skills"
CLAUDE_PROJECT_SKILLS_DIR: Path = Path(".claude") / "skills"
CODEX_USER_SKILLS_DIR: Path = Path.home() / ".codex" / "skills"
CODEX_PROJECT_SKILLS_DIR: Path = Path(".codex") / "skills"

# 日志配置
LOG_RETENTION_DAYS: int = 30
LOG_LEVEL: str = os.getenv("SKILLS_LOG_LEVEL", "INFO")
