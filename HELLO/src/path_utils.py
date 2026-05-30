"""
HELLO 路径辅助函数。
"""

from __future__ import annotations

from pathlib import Path


def expand_path(value: str | Path) -> Path:
    """
    展开路径中的用户目录符号并解析为绝对路径。

    Args:
        value: 原始路径字符串或 Path 对象。

    Returns:
        展开后的绝对路径。
    """
    return Path(value).expanduser().resolve()
