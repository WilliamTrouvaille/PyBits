"""最近安装记录（.recent_installs.json）。

仅记录已安装 skill 的名字，按 LRU 去重，最新的排在最前，上限 100 条。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from filelock import FileLock
from loguru import logger

from _shared.utils.trash import soft_delete

RECENT_LIMIT = 100


def load_recent(recent_path: Path) -> list[str]:
    """加载最近安装的 skill 名列表（最新在前）。"""
    if not recent_path.exists():
        return []

    lock = FileLock(f"{recent_path}.lock")
    try:
        with lock, open(recent_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.warning(f"最近安装记录格式错误，已忽略: {recent_path}, 错误: {e}")
        return []
    except OSError as e:
        logger.warning(f"读取最近安装记录失败: {e}")
        return []

    skills = data.get("skills") if isinstance(data, dict) else None
    if not isinstance(skills, list):
        return []
    return [str(name) for name in skills]


def record_recent(skill_name: str, recent_path: Path) -> None:
    """记录一次安装：把 skill_name 放到列表最前，去重并截断到上限。"""
    skills = load_recent(recent_path)
    skills = [name for name in skills if name != skill_name]
    skills.insert(0, skill_name)
    del skills[RECENT_LIMIT:]
    _save_recent(skills, recent_path)
    logger.debug(f"记录最近安装: {skill_name}")


def _save_recent(skills: list[str], recent_path: Path) -> None:
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
                    json.dump({"skills": skills}, temp_file, indent=2, ensure_ascii=False)
                    temp_file.flush()
                temp_path.replace(recent_path)
            finally:
                if temp_path is not None and temp_path.exists():
                    soft_delete(temp_path, "skills-temp-recent")
    except Exception as e:
        logger.error(f"保存最近安装记录失败: {e}")
        raise
