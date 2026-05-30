"""
CTA 命令行入口。
"""

from __future__ import annotations

import sys
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
        print(f"ERROR: CLAUDE.md not found in {cwd}", file=sys.stderr)
        return 1
    if target_path.exists() and not args.force:
        print(
            f"ERROR: AGENTS.md already exists in {cwd}; rerun with --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    content = source_path.read_text(encoding="utf-8")
    if target_path.exists():
        soft_delete(target_path, "cta-force-agents")
    target_path.write_text(convert_content(content), encoding="utf-8")
    print(f"Created {target_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
