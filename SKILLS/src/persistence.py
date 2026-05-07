"""JSON 持久化操作"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from filelock import FileLock
from loguru import logger

from .models import Repository, RepositoryType


def load_local_config(repos_local_json_path: Path) -> dict:
    """加载 .repos.local.json（路径映射表）"""
    if not repos_local_json_path.exists():
        return {"github_cache_paths": {}, "local_paths": {}}

    lock = FileLock(f"{repos_local_json_path}.lock")
    try:
        with lock:
            with open(repos_local_json_path, encoding="utf-8") as f:
                data = json.load(f)
            return data
    except json.JSONDecodeError as e:
        raise RuntimeError(f"配置文件格式错误: {repos_local_json_path}, 错误: {e}") from e
    except Exception as e:
        raise RuntimeError(f"加载本地配置失败: {e}") from e


def save_local_config(data: dict, repos_local_json_path: Path) -> None:
    """保存 .repos.local.json（路径映射表），使用原子写入"""
    lock = FileLock(f"{repos_local_json_path}.lock")
    try:
        with lock:
            temp_file = tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", delete=False, dir=repos_local_json_path.parent
            )
            try:
                json.dump(data, temp_file, indent=2, ensure_ascii=False)
                temp_file.flush()
                temp_file.close()
                Path(temp_file.name).replace(repos_local_json_path)
            finally:
                if Path(temp_file.name).exists():
                    Path(temp_file.name).unlink()
    except Exception as e:
        logger.error(f"保存本地配置失败: {e}")
        raise


def load_repositories(
    repos_json_path: Path, repos_local_json_path: Path
) -> list[Repository]:
    """
    加载所有已注册的仓库（合并两个配置文件）
    1. 加载 .repos.json（所有仓库元信息，path/local_path 为 None）
    2. 加载 .repos.local.json（路径映射表）
    3. 根据 name 和 type 补充路径

    Args:
        repos_json_path: .repos.json 文件路径
        repos_local_json_path: .repos.local.json 文件路径

    Returns:
        仓库列表

    Raises:
        RuntimeError: 配置文件格式错误或加载失败
    """
    if not repos_json_path.exists():
        logger.debug(f"持久化文件不存在: {repos_json_path}")
        return []

    lock = FileLock(f"{repos_json_path}.lock")
    try:
        with lock:
            # 加载所有仓库元信息
            with open(repos_json_path, encoding="utf-8") as f:
                data = json.load(f)

            repos = [
                Repository.from_dict(repo_data)
                for repo_data in data.get("repositories", [])
            ]

            # 加载路径映射表（在同一个锁保护范围内）
            local_config = load_local_config(repos_local_json_path)
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
        raise RuntimeError(f"JSON 格式错误: {repos_json_path}, 错误: {e}") from e
    except Exception as e:
        raise RuntimeError(f"加载仓库失败: {e}") from e


def save_repositories(
    repos: list[Repository], repos_json_path: Path, repos_local_json_path: Path
) -> None:
    """
    保存仓库列表到两个配置文件（原子写入）
    1. 所有仓库元信息 → .repos.json（path/local_path 为 None）
    2. 路径映射表 → .repos.local.json

    Args:
        repos: 仓库列表
        repos_json_path: .repos.json 文件路径
        repos_local_json_path: .repos.local.json 文件路径
    """
    lock = FileLock(f"{repos_json_path}.lock")
    try:
        with lock:
            # 保存 .repos.json（所有仓库元信息），原子写入
            data = {"repositories": [repo.to_dict() for repo in repos]}
            temp_file = tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", delete=False, dir=repos_json_path.parent
            )
            try:
                json.dump(data, temp_file, indent=2, ensure_ascii=False)
                temp_file.flush()
                temp_file.close()
                Path(temp_file.name).replace(repos_json_path)
            finally:
                if Path(temp_file.name).exists():
                    Path(temp_file.name).unlink()
            logger.debug(f"保存了 {len(repos)} 个仓库到 {repos_json_path}")

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
            save_local_config(local_config, repos_local_json_path)
            logger.debug(f"保存了路径映射到 {repos_local_json_path}")
    except Exception as e:
        logger.error(f"保存仓库失败: {e}")
        raise


def add_repository(
    repo: Repository, repos_json_path: Path, repos_local_json_path: Path
) -> None:
    """添加新仓库（检查重复）"""
    repos = load_repositories(repos_json_path, repos_local_json_path)

    # 检查是否已存在
    if any(r.name == repo.name for r in repos):
        raise ValueError(f"仓库 '{repo.name}' 已存在")

    repos.append(repo)
    save_repositories(repos, repos_json_path, repos_local_json_path)
    logger.info(f"添加仓库: {repo.name}")


def update_repository(
    repo: Repository, repos_json_path: Path, repos_local_json_path: Path
) -> None:
    """
    更新已存在的仓库记录
    - 如果仓库不存在，抛出异常
    - 如果存在，替换为新的记录
    """
    repos = load_repositories(repos_json_path, repos_local_json_path)

    # 查找并替换
    found = False
    for i, r in enumerate(repos):
        if r.name == repo.name:
            repos[i] = repo
            found = True
            break

    if not found:
        raise ValueError(f"仓库 '{repo.name}' 不存在，无法更新")

    save_repositories(repos, repos_json_path, repos_local_json_path)
    logger.info(f"更新仓库: {repo.name}")


def remove_repository(
    name: str, repos_json_path: Path, repos_local_json_path: Path
) -> bool:
    """移除指定仓库"""
    repos = load_repositories(repos_json_path, repos_local_json_path)
    original_count = len(repos)

    repos = [r for r in repos if r.name != name]

    if len(repos) == original_count:
        logger.warning(f"仓库不存在: {name}")
        return False

    save_repositories(repos, repos_json_path, repos_local_json_path)
    logger.info(f"移除仓库: {name}")
    return True


def get_repository(
    name: str, repos_json_path: Path, repos_local_json_path: Path
) -> Repository | None:
    """根据名称获取仓库"""
    repos = load_repositories(repos_json_path, repos_local_json_path)
    for repo in repos:
        if repo.name == name:
            return repo
    return None


def repository_exists(name: str, repos_json_path: Path, repos_local_json_path: Path) -> bool:
    """检查仓库是否已注册"""
    return get_repository(name, repos_json_path, repos_local_json_path) is not None
