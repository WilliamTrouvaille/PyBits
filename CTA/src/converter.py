"""
CLAUDE.md 到 AGENTS.md 的转换辅助函数。
"""

from __future__ import annotations


def convert_content(content: str) -> str:
    """
    将面向 Claude 的指令文本转换为面向 Codex 的指令文本。

    Args:
        content: 原始 CLAUDE.md 文本。

    Returns:
        替换关键命名后的 AGENTS.md 文本。
    """

    return content.replace("Claude", "Codex").replace(".claude/", ".codex/")
