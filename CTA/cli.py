"""
CTA 命令行入口。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from _shared.utils.trash import soft_delete

from .src.cli_parser import build_parser
from .src.converter import convert_content


def main() -> int:
    """
    将当前目录的 CLAUDE.md 转换为 AGENTS.md。

    Returns:
        进程退出码，0 表示转换成功。
    """
    parser = build_parser()
    args = parser.parse_args()

    cwd = Path.cwd()
    source_path = cwd / "CLAUDE.md"
    target_path = cwd / "AGENTS.md"

    if not source_path.is_file():
        print(f"错误: {cwd} 中未找到 CLAUDE.md", file=sys.stderr)
        return 1
    target_exists = target_path.exists() or target_path.is_symlink()
    if target_exists and not args.force:
        print(
            f"错误: {cwd} 中已存在 AGENTS.md；如需覆盖，请使用 --force 重新运行。",
            file=sys.stderr,
        )
        return 1

    content = source_path.read_text(encoding="utf-8")
    converted = convert_content(content)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=cwd,
            prefix=".AGENTS.",
            suffix=".tmp",
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(converted)
            temp_file.flush()

        if target_exists:
            soft_delete(target_path, "cta-force-agents")
        temp_path.replace(target_path)
    finally:
        if temp_path is not None and temp_path.exists():
            soft_delete(temp_path, "cta-temp-agents")
    print(f"已创建 {target_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
