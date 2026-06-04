"""最近安装记录（.recent_installs.local.json）。

记录已安装 skill 的名字和可选来源仓库，按 LRU 去重，最新的排在最前，上限 100 条。
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from filelock import FileLock
from loguru import logger

from _shared.utils.trash import soft_delete

RECENT_LIMIT = 100


@dataclass(frozen=True)
class RecentSkillRef:
    """最近安装记录中的单个 skill 引用。"""

    name: str
    repository_name: str | None = None


def load_recent(recent_path: Path) -> list[str]:
    """加载最近安装的 skill 名列表（最新在前）。"""
    return [ref.name for ref in load_recent_refs(recent_path)]


def load_recent_refs(recent_path: Path) -> list[RecentSkillRef]:
    """加载最近安装的 skill 引用列表（最新在前）。"""
    read_path = _recent_read_path(recent_path)
    if read_path is None:
        return []

    lock = FileLock(f"{read_path}.lock")
    try:
        with lock, open(read_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.warning(f"最近安装记录格式错误，已忽略: {read_path}, 错误: {e}")
        return []
    except OSError as e:
        logger.warning(f"读取最近安装记录失败: {e}")
        return []

    skills = data.get("skills") if isinstance(data, dict) else None
    if not isinstance(skills, list):
        return []
    refs: list[RecentSkillRef] = []
    for item in skills:
        ref = _parse_recent_item(item)
        if ref is not None:
            refs.append(ref)
    return refs


def _recent_read_path(recent_path: Path) -> Path | None:
    if recent_path.exists():
        return recent_path

    legacy_path = _legacy_recent_path(recent_path)
    if legacy_path is not None and legacy_path.exists():
        return legacy_path

    return None


def _legacy_recent_path(recent_path: Path) -> Path | None:
    if recent_path.name != ".recent_installs.local.json":
        return None
    return recent_path.with_name(".recent_installs.json")


def record_recent(
    skill_name: str,
    recent_path: Path,
    repository_name: str | None = None,
) -> None:
    """记录一次安装：把 skill_name 放到列表最前，去重并截断到上限。"""
    refs = load_recent_refs(recent_path)
    refs = [ref for ref in refs if not _is_same_recent_skill(ref, skill_name, repository_name)]
    refs.insert(0, RecentSkillRef(skill_name, repository_name))
    del refs[RECENT_LIMIT:]
    _save_recent(refs, recent_path)
    logger.debug(f"记录最近安装: {skill_name}")


def _parse_recent_item(item: object) -> RecentSkillRef | None:
    """兼容旧版字符串记录和新版带来源记录。"""
    if isinstance(item, str):
        return RecentSkillRef(item)
    if not isinstance(item, dict):
        return None

    name = item.get("name")
    if not isinstance(name, str) or not name:
        return None

    repository_name = item.get("repository_name") or item.get("repository")
    if repository_name is not None and not isinstance(repository_name, str):
        repository_name = None

    return RecentSkillRef(name, repository_name)


def _is_same_recent_skill(
    ref: RecentSkillRef,
    skill_name: str,
    repository_name: str | None,
) -> bool:
    if ref.name != skill_name:
        return False
    if repository_name is None:
        return True
    return ref.repository_name in (None, repository_name)


def _serialize_recent_item(ref: RecentSkillRef) -> str | dict[str, str]:
    if ref.repository_name is None:
        return ref.name
    return {"name": ref.name, "repository_name": ref.repository_name}


def _save_recent(skills: list[RecentSkillRef], recent_path: Path) -> None:
    """原子写入最近安装记录。"""
    lock = FileLock(f"{recent_path}.lock")
    try:
        with lock:
            temp_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    delete=False,
                    dir=recent_path.parent,
                ) as temp_file:
                    temp_path = Path(temp_file.name)
                    json.dump(
                        {"skills": [_serialize_recent_item(ref) for ref in skills]},
                        temp_file,
                        indent=2,
                        ensure_ascii=False,
                    )
                    temp_file.flush()
                temp_path.replace(recent_path)
            finally:
                if temp_path is not None and temp_path.exists():
                    soft_delete(temp_path, "skills-temp-recent")
    except Exception as e:
        logger.error(f"保存最近安装记录失败: {e}")
        raise
