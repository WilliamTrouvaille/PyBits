"""
HELLO 命令展示辅助函数。
"""

from __future__ import annotations

import os
import shlex
import subprocess


def command_display(cmd: list[str]) -> str:
    """
    将命令列表转换为可显示的字符串。

    Args:
        cmd: 命令及参数列表。

    Returns:
        可展示的命令字符串。
    """
    if os.name == "nt":
        return subprocess.list2cmdline(cmd)
    return shlex.join(cmd)
