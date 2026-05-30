"""
HELLO 哈希辅助函数。
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_12(path: Path) -> str | None:
    """
    计算文件内容的 SHA256 哈希值并返回前 12 位。

    Args:
        path: 待计算哈希的文件路径。

    Returns:
        文件存在时返回 12 位哈希摘要；文件不存在或不是文件时返回 None。
    """
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]


def text_sha256_12(text: str) -> str | None:
    """
    计算文本内容的 SHA256 哈希值并返回前 12 位。

    Args:
        text: 待计算哈希的文本。

    Returns:
        文本非空时返回 12 位哈希摘要；空文本返回 None。
    """
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]
