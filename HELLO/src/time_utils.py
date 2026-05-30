"""
HELLO 时间辅助函数。
"""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> str:
    """
    返回当前 UTC 时间的 ISO8601 格式字符串。

    Returns:
        以 `Z` 结尾的 UTC ISO8601 时间字符串。
    """
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
