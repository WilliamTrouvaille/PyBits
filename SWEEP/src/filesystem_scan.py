"""封装 SWEEP 文件系统 walker 对 DirEntry 的防御性访问。"""

from __future__ import annotations

import os
from pathlib import Path

from .config import SweepConfig
from .path_rules import is_basic_safe_path


def read_directory_entries(directory: Path) -> tuple[os.DirEntry[str], ...] | None:
    """
    读取目录条目，并保留无法读取这一状态。

    Args:
        directory: 要扫描的目录。

    Returns:
        当前目录中的 DirEntry 元组；无法读取时返回 None。
    """
    try:
        with os.scandir(directory) as entries:
            return tuple(entries)
    except OSError:
        return None


def list_directory_entries(directory: Path) -> tuple[os.DirEntry[str], ...]:
    """
    读取目录条目；目录无法读取时返回空结果。

    Args:
        directory: 要扫描的目录。

    Returns:
        当前目录中的 DirEntry 元组；无法读取时返回空元组。
    """
    return read_directory_entries(directory) or ()


def safe_entry_path(entry: os.DirEntry[str], config: SweepConfig) -> Path | None:
    """
    返回通过基础安全检查的条目路径。

    Args:
        entry: `os.scandir()` 产出的目录条目。
        config: 已校验的 SWEEP 配置。

    Returns:
        可继续检查的 Path；symlink、拒绝字符路径或无法 stat 的条目返回 None。
    """
    path = Path(entry.path)
    try:
        if entry.is_symlink() or not is_basic_safe_path(path, config):
            return None
    except OSError:
        return None
    return path


def entry_is_file(entry: os.DirEntry[str]) -> bool:
    """
    安全判断条目是否为普通文件。

    Args:
        entry: `os.scandir()` 产出的目录条目。

    Returns:
        条目是普通文件时返回 True；无法判断时返回 False。
    """
    try:
        return entry.is_file(follow_symlinks=False)
    except OSError:
        return False


def entry_is_dir(entry: os.DirEntry[str]) -> bool:
    """
    安全判断条目是否为目录。

    Args:
        entry: `os.scandir()` 产出的目录条目。

    Returns:
        条目是目录时返回 True；无法判断时返回 False。
    """
    try:
        return entry.is_dir(follow_symlinks=False)
    except OSError:
        return False
