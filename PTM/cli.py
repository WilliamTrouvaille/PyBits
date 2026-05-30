"""
PTM 命令行入口。
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from _shared.utils.logging import setup_tool_logger

from .src.cli_parser import build_parser
from .src.models import PTMError
from .src.workflow import convert_pdf_via_api

LOGS_DIR = Path(__file__).parent / "logs"


def main() -> int:
    """
    解析 PTM 命令行参数并执行 PDF 转 Markdown 流程。

    Returns:
        进程退出码，0 表示转换成功。
    """

    args = build_parser().parse_args()
    setup_tool_logger(
        "ptm",
        logs_dir=LOGS_DIR,
        verbose=args.verbose,
        retention_days=30,
        console_level="DEBUG" if args.verbose else "INFO",
    )

    try:
        output_path = convert_pdf_via_api(args)
    except PTMError as exc:
        print(f"ERROR: {exc.message}", file=sys.stderr)
        print(f"HINT: {exc.hint}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ERROR: Interrupted by user", file=sys.stderr)
        print("HINT: Run the command again when ready.", file=sys.stderr)
        return 1
    except Exception:
        logger.exception("Unexpected error")
        print("ERROR: Unexpected error", file=sys.stderr)
        print("HINT: Check the traceback above or rerun with --verbose.", file=sys.stderr)
        return 1

    print(output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
