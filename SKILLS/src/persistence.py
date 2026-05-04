"""JSON 持久化操作"""

import json

from loguru import logger

from .config import REPOS_JSON_PATH
from .models import Repository


def load_repositories() -> list[Repository]:
    """加载所有已注册的仓库"""
    if not REPOS_JSON_PATH.exists():
        logger.debug(f"持久化文件不存在: {REPOS_JSON_PATH}")
        return []

    try:
        with open(REPOS_JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)

        repos = [
            Repository.from_dict(repo_data)
            for repo_data in data.get("repositories", [])
        ]
        logger.debug(f"加载了 {len(repos)} 个仓库")
        return repos
    except json.JSONDecodeError as e:
        logger.error(f"JSON 格式错误: {REPOS_JSON_PATH}, 错误: {e}")
        return []
    except Exception as e:
        logger.error(f"加载仓库失败: {e}")
        return []


def save_repositories(repos: list[Repository]) -> None:
    """保存仓库列表到 .repos.json"""
    try:
        data = {"repositories": [repo.to_dict() for repo in repos]}

        with open(REPOS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.debug(f"保存了 {len(repos)} 个仓库到 {REPOS_JSON_PATH}")
    except Exception as e:
        logger.error(f"保存仓库失败: {e}")
        raise


def add_repository(repo: Repository) -> None:
    """添加新仓库（检查重复）"""
    repos = load_repositories()

    # 检查是否已存在
    if any(r.name == repo.name for r in repos):
        raise ValueError(f"仓库 '{repo.name}' 已存在")

    repos.append(repo)
    save_repositories(repos)
    logger.info(f"添加仓库: {repo.name}")


def remove_repository(name: str) -> bool:
    """移除指定仓库"""
    repos = load_repositories()
    original_count = len(repos)

    repos = [r for r in repos if r.name != name]

    if len(repos) == original_count:
        logger.warning(f"仓库不存在: {name}")
        return False

    save_repositories(repos)
    logger.info(f"移除仓库: {name}")
    return True


def get_repository(name: str) -> Repository | None:
    """根据名称获取仓库"""
    repos = load_repositories()
    for repo in repos:
        if repo.name == name:
            return repo
    return None


def repository_exists(name: str) -> bool:
    """检查仓库是否已注册"""
    return get_repository(name) is not None
