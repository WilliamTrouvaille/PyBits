"""JSON 持久化操作"""

import json
from pathlib import Path

from loguru import logger

from .config import REPOS_JSON_PATH, REPOS_LOCAL_JSON_PATH
from .models import Repository, RepositoryType


def load_local_config() -> dict:
    """加载 .repos.local.json（路径映射表）"""
    if not REPOS_LOCAL_JSON_PATH.exists():
        return {"github_cache_paths": {}, "local_paths": {}}

    try:
        with open(REPOS_LOCAL_JSON_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载本地配置失败: {e}")
        return {"github_cache_paths": {}, "local_paths": {}}


def save_local_config(data: dict) -> None:
    """保存 .repos.local.json（路径映射表）"""
    try:
        with open(REPOS_LOCAL_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"保存本地配置失败: {e}")
        raise


def load_repositories() -> list[Repository]:
    """
    加载所有已注册的仓库（合并两个配置文件）
    1. 加载 .repos.json（所有仓库元信息，path/local_path 为 None）
    2. 加载 .repos.local.json（路径映射表）
    3. 根据 name 和 type 补充路径
    """
    if not REPOS_JSON_PATH.exists():
        logger.debug(f"持久化文件不存在: {REPOS_JSON_PATH}")
        return []

    try:
        # 加载所有仓库元信息
        with open(REPOS_JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)

        repos = [
            Repository.from_dict(repo_data)
            for repo_data in data.get("repositories", [])
        ]

        # 加载路径映射表
        local_config = load_local_config()
        github_cache_paths = local_config.get("github_cache_paths", {})
        local_paths = local_config.get("local_paths", {})

        # 补充路径
        for repo in repos:
            if repo.type == RepositoryType.GITHUB:
                cache_path_str = github_cache_paths.get(repo.name)
                repo.local_path = Path(cache_path_str) if cache_path_str else None
            elif repo.type == RepositoryType.LOCAL:
                local_path_str = local_paths.get(repo.name)
                repo.path = Path(local_path_str) if local_path_str else None

        logger.debug(f"加载了 {len(repos)} 个仓库")
        return repos
    except json.JSONDecodeError as e:
        logger.error(f"JSON 格式错误: {REPOS_JSON_PATH}, 错误: {e}")
        return []
    except Exception as e:
        logger.error(f"加载仓库失败: {e}")
        return []


def save_repositories(repos: list[Repository]) -> None:
    """
    保存仓库列表到两个配置文件
    1. 所有仓库元信息 → .repos.json（path/local_path 为 None）
    2. 路径映射表 → .repos.local.json
    """
    # 保存 .repos.json（所有仓库元信息）
    data = {"repositories": [repo.to_dict() for repo in repos]}

    try:
        with open(REPOS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.debug(f"保存了 {len(repos)} 个仓库到 {REPOS_JSON_PATH}")
    except Exception as e:
        logger.error(f"保存仓库失败: {e}")
        raise

    # 构建路径映射表
    github_cache_paths = {}
    local_paths = {}

    for repo in repos:
        if repo.type == RepositoryType.GITHUB and repo.local_path:
            github_cache_paths[repo.name] = str(repo.local_path)
        elif repo.type == RepositoryType.LOCAL and repo.path:
            local_paths[repo.name] = str(repo.path)

    # 保存 .repos.local.json（路径映射表）
    local_config = {
        "github_cache_paths": github_cache_paths,
        "local_paths": local_paths,
    }
    save_local_config(local_config)
    logger.debug(f"保存了路径映射到 {REPOS_LOCAL_JSON_PATH}")


def add_repository(repo: Repository) -> None:
    """添加新仓库（检查重复）"""
    repos = load_repositories()

    # 检查是否已存在
    if any(r.name == repo.name for r in repos):
        raise ValueError(f"仓库 '{repo.name}' 已存在")

    repos.append(repo)
    save_repositories(repos)
    logger.info(f"添加仓库: {repo.name}")


def update_repository(repo: Repository) -> None:
    """
    更新已存在的仓库记录
    - 如果仓库不存在，抛出异常
    - 如果存在，替换为新的记录
    """
    repos = load_repositories()

    # 查找并替换
    found = False
    for i, r in enumerate(repos):
        if r.name == repo.name:
            repos[i] = repo
            found = True
            break

    if not found:
        raise ValueError(f"仓库 '{repo.name}' 不存在，无法更新")

    save_repositories(repos)
    logger.info(f"更新仓库: {repo.name}")


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
