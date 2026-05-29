"""Soft-delete helpers for project files and caches."""

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
    """Move a path into `.codex/_trash_bin_` and return its new location."""
    source = Path(path).expanduser()
    if not source.exists() and not source.is_symlink():
        raise FileNotFoundError(f"Cannot soft-delete missing path: {source}")

    resolved_trash_root = Path(trash_root).expanduser() if trash_root else default_trash_root(source)
    resolved_trash_root.mkdir(parents=True, exist_ok=True)
    _validate_safe_move(source, resolved_trash_root)

    destination = _unique_destination(
        resolved_trash_root,
        reason=reason,
        original_name=source.name,
    )
    return Path(shutil.move(str(source), str(destination)))


def default_trash_root(start: Path | str | None = None) -> Path:
    """Find the nearest project trash bin, falling back to the current directory."""
    current = Path(start).expanduser() if start else Path.cwd()
    current = current if current.is_dir() else current.parent

    for candidate in (current, *current.parents):
        codex_dir = candidate / ".codex"
        if codex_dir.exists():
            return codex_dir / "_trash_bin_"

    return Path.cwd() / ".codex" / "_trash_bin_"


def _unique_destination(trash_root: Path, reason: str, original_name: str) -> Path:
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
    resolved_source = source.resolve(strict=False)
    resolved_trash_root = trash_root.resolve(strict=False)

    if resolved_source == resolved_trash_root:
        raise ValueError(f"Refusing to soft-delete trash root itself: {source}")
    if resolved_source in resolved_trash_root.parents:
        raise ValueError(f"Refusing to soft-delete a parent of trash root: {source}")
    if resolved_trash_root in resolved_source.parents:
        raise ValueError(f"Refusing to soft-delete an item already inside trash root: {source}")


def _slugify(value: str, default: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip())
    return slug.strip("._-") or default
