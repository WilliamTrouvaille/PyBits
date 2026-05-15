"""纯工具函数"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    """
    返回当前 UTC 时间的 ISO8601 格式字符串

    Returns:
        ISO8601 格式的时间戳，例如 "2026-05-04T14:30:22.123Z"
    """
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def expand_path(value: str | Path) -> Path:
    """
    展开路径中的用户目录符号并解析为绝对路径

    Args:
        value: 路径字符串或 Path 对象

    Returns:
        展开后的绝对路径
    """
    return Path(value).expanduser().resolve()


def to_text(value: Any) -> str:
    """
    将任意值转换为文本字符串

    Args:
        value: 任意类型的值

    Returns:
        转换后的字符串，bytes 会解码为 UTF-8，None 返回空字符串
    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def strip_ansi(text: str) -> str:
    """
    移除文本中的 ANSI 转义序列（终端颜色代码等）

    Args:
        text: 包含 ANSI 转义序列的文本

    Returns:
        清理后的纯文本
    """
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)


def tail_text(text: str, limit: int = 4000) -> str:
    """
    截取文本的尾部，先移除 ANSI 转义序列

    Args:
        text: 原始文本
        limit: 保留的最大字符数

    Returns:
        截取后的文本，如果原文本长度不超过 limit 则返回原文本
    """
    text = strip_ansi(text or "")
    if len(text) <= limit:
        return text
    return text[-limit:]


def sha256_12(path: Path) -> str | None:
    """
    计算文件内容的 SHA256 哈希值并返回前 12 位

    Args:
        path: 文件路径

    Returns:
        SHA256 哈希值的前 12 位十六进制字符串，文件不存在或不是文件时返回 None
    """
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    # 流式读取，避免大文件占用过多内存
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def text_sha256_12(text: str) -> str | None:
    """
    计算文本内容的 SHA256 哈希值并返回前 12 位

    Args:
        text: 文本内容

    Returns:
        SHA256 哈希值的前 12 位十六进制字符串，文本为空时返回 None
    """
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:12]


def command_display(cmd: list[str]) -> str:
    """
    将命令列表转换为可显示的字符串，自动处理跨平台转义

    Args:
        cmd: 命令参数列表

    Returns:
        格式化后的命令字符串，Windows 使用 list2cmdline，Unix 使用 shlex.join
    """
    if os.name == "nt":
        return subprocess.list2cmdline(cmd)
    return shlex.join(cmd)


def parse_json_maybe(text: str) -> Any | None:
    """
    尝试解析 JSON 文本，失败时返回 None 而不抛出异常

    Args:
        text: JSON 文本

    Returns:
        解析后的 Python 对象，解析失败或文本为空时返回 None
    """
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def parse_jsonl(text: str) -> tuple[list[Any], int]:
    """
    解析 JSONL 格式文本（每行一个 JSON 对象）

    Args:
        text: JSONL 格式文本

    Returns:
        元组 (成功解析的对象列表, 解析失败的行数)
    """
    events: list[Any] = []
    bad_lines = 0

    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            bad_lines += 1

    return events, bad_lines
