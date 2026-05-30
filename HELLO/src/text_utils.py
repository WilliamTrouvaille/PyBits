"""
HELLO 文本处理辅助函数。
"""

from __future__ import annotations

import re
from typing import Any


def to_text(value: Any) -> str:
    """
    将任意值转换为文本字符串。

    Args:
        value: 待转换的任意值。

    Returns:
        转换后的文本；None 转为空字符串，bytes 按 UTF-8 容错解码。
    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def strip_ansi(text: str) -> str:
    """
    移除文本中的 ANSI 转义序列。

    Args:
        text: 原始文本。

    Returns:
        移除 ANSI 转义序列后的文本。
    """
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)


def tail_text(text: str, limit: int = 4000) -> str:
    """
    截取文本尾部并先移除 ANSI 转义序列。

    Args:
        text: 原始文本。
        limit: 保留的最大字符数。

    Returns:
        截取后的文本。
    """
    text = strip_ansi(text or "")
    if len(text) <= limit:
        return text
    return text[-limit:]
