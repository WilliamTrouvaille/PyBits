"""常用 skills（favorite）管理。

favorite 是一个内置仓库：实体目录位于 _repos_cache/favorite/，并作为一条
type=local 的记录注册到 .repos.json，因此会出现在 SKILLS ls 中。
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from loguru import logger

from _shared.utils.trash import soft_delete

from .models import Repository, RepositoryType
from .persistence import (
    add_repository,
    get_repository,
    update_repository,
)
from .utils import ensure_dir

FAVORITE_NAME = "favorite"


def favorite_dir(repos_cache_dir: Path) -> Path:
    """返回 favorite 实体目录路径并确保存在。"""
    path = repos_cache_dir / FAVORITE_NAME
    ensure_dir(path)
    return path


def ensure_favorite_repo(
    repos_cache_dir: Path, repos_json_path: Path, repos_local_json_path: Path
) -> Repository:
    """确保 favorite 已作为本地仓库注册，返回该仓库记录。"""
    fav_path = favorite_dir(repos_cache_dir)
    existing = get_repository(FAVORITE_NAME, repos_json_path, repos_local_json_path)
    repo = Repository(
        name=FAVORITE_NAME,
        type=RepositoryType.LOCAL,
        url=None,
        path=fav_path.resolve(),
        local_path=None,
        registered_at=existing.registered_at if existing else datetime.now(),
    )
    if existing:
        if existing.path != repo.path:
            update_repository(repo, repos_json_path, repos_local_json_path)
    else:
        add_repository(repo, repos_json_path, repos_local_json_path)
        logger.info(f"[用户操作] 初始化常用 skills 仓库: {FAVORITE_NAME}")
    return repo


def list_favorites(repos_cache_dir: Path) -> list[str]:
    """列出 favorite 目录下的 skill 名。"""
    fav_path = favorite_dir(repos_cache_dir)
    return sorted(
        d.name
        for d in fav_path.iterdir()
        if d.is_dir() and not d.name.startswith(".") and (d / "SKILL.md").exists()
    )


def add_favorite(
    repo_name: str,
    skill_names: list[str],
    repos_cache_dir: Path,
    repos_json_path: Path,
    repos_local_json_path: Path,
    excluded_dirs: set[str],
    scan_depth: int,
) -> list[str]:
    """从已注册仓库的缓存复制指定 skill 到 favorite，返回成功复制的 skill 名。"""
    from .repository import scan_repository

    repo = get_repository(repo_name, repos_json_path, repos_local_json_path)
    if not repo:
        raise ValueError(f"仓库不存在: {repo_name}")
    if repo.name == FAVORITE_NAME:
        raise ValueError("不能从 favorite 自身添加")

    available = {skill.name: skill for skill in scan_repository(repo, scan_depth, excluded_dirs)}
    missing = [name for name in skill_names if name not in available]
    if missing:
        raise ValueError(f"在仓库 {repo_name} 中未找到 skill: {', '.join(missing)}")

    ensure_favorite_repo(repos_cache_dir, repos_json_path, repos_local_json_path)
    fav_path = favorite_dir(repos_cache_dir)

    added: list[str] = []
    for name in skill_names:
        source = available[name].source_path
        target = fav_path / name
        if target.exists():
            moved = soft_delete(target, "skills-favorite-overwrite")
            logger.info(f"已软删除旧 favorite skill: {target} -> {moved}")
        shutil.copytree(source, target)
        added.append(name)
        logger.info(f"[用户操作] 添加常用 skill: {name} (来自 {repo_name})")
    return added


def remove_favorite(skill_name: str, repos_cache_dir: Path) -> bool:
    """软删除 favorite 中的某个 skill，返回是否删除成功。"""
    fav_path = favorite_dir(repos_cache_dir)
    target = fav_path / skill_name
    if not target.exists():
        return False
    moved = soft_delete(target, "skills-favorite-remove")
    logger.info(f"[用户操作] 移除常用 skill: {skill_name} -> {moved}")
    return True

