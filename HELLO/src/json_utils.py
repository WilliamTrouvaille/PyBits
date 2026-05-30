"""
HELLO JSON 解析辅助函数。
"""

from __future__ import annotations

import json
from typing import Any


def parse_json_maybe(text: str) -> Any | None:
    """
    尝试解析 JSON 文本，失败时返回 None。

    Args:
        text: 待解析的 JSON 文本。

    Returns:
        解析成功的对象；输入为空或解析失败时返回 None。
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
    解析 JSONL 格式文本。

    Args:
        text: 待解析的 JSONL 文本。

    Returns:
        成功解析的对象列表和解析失败的行数。
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
