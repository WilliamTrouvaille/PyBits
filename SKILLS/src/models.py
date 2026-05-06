"""数据模型定义"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path


class RepositoryType(Enum):
    """仓库类型"""

    GITHUB = "github"
    LOCAL = "local"


class AgentType(Enum):
    """Agent 类型"""

    CLAUDE = "claude"
    CODEX = "codex"
    ALL = "all"


class ScopeType(Enum):
    """安装范围类型"""

    USER = "user"
    PROJECT = "project"


class InstallMode(Enum):
    """安装模式"""

    COPY = "copy"
    LINK = "link"


@dataclass
class Repository:
    """仓库数据模型"""

    name: str
    type: RepositoryType
    url: str | None
    path: Path | None
    local_path: Path | None
    registered_at: datetime

    def to_dict(self) -> dict:
        """
        转换为字典（用于 .repos.json）
        path 和 local_path 始终为 None，实际路径存储在 .repos.local.json
        """
        return {
            "name": self.name,
            "type": self.type.value,
            "url": self.url,
            "path": None,
            "local_path": None,
            "registered_at": self.registered_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Repository":
        """从字典创建"""
        return cls(
            name=data["name"],
            type=RepositoryType(data["type"]),
            url=data.get("url"),
            path=Path(data["path"]) if data.get("path") else None,
            local_path=Path(data["local_path"]) if data.get("local_path") else None,
            registered_at=datetime.fromisoformat(data["registered_at"]),
        )


@dataclass
class Skill:
    """Skill 数据模型"""

    name: str
    description: str
    source_path: Path
    repository_name: str

    @classmethod
    def from_directory(cls, path: Path, repo_name: str) -> "Skill | None":
        """从目录创建 Skill"""
        from .skill import parse_skill_metadata

        skill_md = path / "SKILL.md"
        if not skill_md.exists():
            return None

        metadata = parse_skill_metadata(skill_md)
        if not metadata:
            return None

        return cls(
            name=metadata["name"],
            description=metadata["description"],
            source_path=path,
            repository_name=repo_name,
        )
