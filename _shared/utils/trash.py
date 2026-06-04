"""项目文件和缓存的软删除辅助函数。"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path


def soft_delete(
    path: Path | str,
    reason: str,
    trash_root: Path | str | None = None,
) -> Path:
    """
    将路径移动到 `.codex/_trash_bin_` 并返回新位置。

    Args:
        path: 待软删除的文件、目录或符号链接。
        reason: 写入垃圾桶文件名的原因标识。
        trash_root: 可选垃圾桶根目录；未传入时自动查找项目垃圾桶。

    Returns:
        移动后的目标路径。

    Raises:
        FileNotFoundError: 待软删除路径不存在。
        ValueError: 目标会破坏垃圾桶自身或其父子关系。
    """
    source = Path(path).expanduser()
    if not source.exists() and not source.is_symlink():
        raise FileNotFoundError(f"无法软删除不存在的路径: {source}")

    resolved_trash_root = (
        Path(trash_root).expanduser() if trash_root else default_trash_root(source)
    )
    resolved_trash_root.mkdir(parents=True, exist_ok=True)
    _validate_safe_move(source, resolved_trash_root)

    destination = _unique_destination(
        resolved_trash_root,
        reason=reason,
        original_name=source.name,
    )
    return Path(shutil.move(str(source), str(destination)))


def default_trash_root(start: Path | str | None = None) -> Path:
    """
    查找最近的项目垃圾桶，找不到时回退到当前目录下的 `.codex/_trash_bin_`。

    Args:
        start: 查找起点；为文件时从其父目录开始。

    Returns:
        可用于软删除的垃圾桶目录路径。
    """
    current = Path(start).expanduser() if start else Path.cwd()
    current = current if current.is_dir() else current.parent

    for candidate in (current, *current.parents):
        codex_dir = candidate / ".codex"
        if codex_dir.exists():
            return codex_dir / "_trash_bin_"

    return Path.cwd() / ".codex" / "_trash_bin_"


def _unique_destination(trash_root: Path, reason: str, original_name: str) -> Path:
    """
    在垃圾桶中生成不冲突的目标路径。
    """

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slugify(reason, default="soft_delete")
    name = _slugify(original_name, default="unnamed")
    destination = trash_root / f"{timestamp}_{slug}_{name}"

    suffix = 1
    while destination.exists():
        destination = trash_root / f"{timestamp}_{slug}_{name}_{suffix}"
        suffix += 1

    return destination


def _validate_safe_move(source: Path, trash_root: Path) -> None:
    """
    拒绝会移动垃圾桶自身、父目录或已在垃圾桶内路径的操作。
    """

    resolved_source = source.resolve(strict=False)
    resolved_trash_root = trash_root.resolve(strict=False)

    if resolved_source == resolved_trash_root:
        raise ValueError(f"Refusing to soft-delete trash root itself: {source}")
    if resolved_source in resolved_trash_root.parents:
        raise ValueError(f"Refusing to soft-delete a parent of trash root: {source}")
    if resolved_trash_root in resolved_source.parents:
        raise ValueError(f"Refusing to soft-delete an item already inside trash root: {source}")


def _slugify(value: str, default: str) -> str:
    """
    将文件名片段收敛为适合垃圾桶路径使用的 ASCII slug。
    """

    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip())
    return slug.strip("._-") or default
