"""
AIM 命令行入口。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from loguru import logger

from _shared.utils.logging import setup_tool_logger

from .src.cli_parser import build_parser
from .src.indexer import build_index, parse_since
from .src.output import resolve_out_dir

LOGS_DIR = Path(__file__).parent / "logs"


def main() -> int:
    """
    解析 AIM 命令行参数并生成脱敏证据索引。

    Returns:
        进程退出码，0 表示索引生成成功。
    """
    parser = build_parser()
    args = parser.parse_args()
    setup_tool_logger("aim", logs_dir=LOGS_DIR, verbose=args.verbose, retention_days=30)

    if args.limit < 1:
        parser.error("--limit 必须大于 0")

    try:
        since = parse_since(args.since)
        out_dir = resolve_out_dir(args.out_dir)
        records = build_index(
            claude_home=Path(args.claude_home),
            codex_home=Path(args.codex_home),
            out_dir=out_dir,
            since=since,
            limit=args.limit,
        )
    except (OSError, ValueError) as exc:
        logger.error(str(exc))
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    summary = {
        "out_dir": str(out_dir),
        "index": str(out_dir / "index.json"),
        "candidates": str(out_dir / "candidates.md"),
        "records": len(records),
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"AIM 索引已写入: {out_dir}")
        print(f"记录数: {len(records)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
