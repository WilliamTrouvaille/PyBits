"""
AIM 输出路径辅助函数。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def default_out_dir() -> Path:
    """
    生成默认的 AIM 时间戳输出目录。

    Returns:
        当前工作目录下的 `.codex/aim/{timestamp}` 路径。
    """

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path.cwd() / ".codex" / "aim" / timestamp


def resolve_out_dir(raw_out_dir: str | None) -> Path:
    """
    解析 AIM 输出目录并拒绝覆盖已有结果文件。

    Args:
        raw_out_dir: 用户传入的输出目录；为 None 时使用默认目录。

    Returns:
        解析后的绝对输出目录。

    Raises:
        ValueError: 输出目录中已经存在 AIM 结果文件。
    """

    out_dir = Path(raw_out_dir).expanduser() if raw_out_dir else default_out_dir()
    index_path = out_dir / "index.json"
    candidates_path = out_dir / "candidates.md"
    if index_path.exists() or candidates_path.exists():
        raise ValueError(
            f"Output directory already contains AIM results: {out_dir}. "
            "Choose a new --out-dir."
        )
    return out_dir.resolve()
