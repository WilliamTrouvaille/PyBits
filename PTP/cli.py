"""
PTP 命令行入口。
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from _shared.utils.logging import setup_tool_logger

from .src.cli_parser import build_parser
from .src.converter import PTPError, RenderOptions, render_pdf
from .src.options import selected_pages_from_args

LOGS_DIR = Path(__file__).parent / "logs"


def main() -> int:
    """
    解析 PTP 命令行参数并渲染 PDF 页面。

    Returns:
        进程退出码，0 表示渲染成功。
    """

    parser = build_parser()
    args = parser.parse_args()
    setup_tool_logger("ptp", logs_dir=LOGS_DIR, verbose=args.verbose, retention_days=30)

    try:
        result = render_pdf(
            RenderOptions(
                input_pdf=Path(args.input_pdf),
                out_dir=Path(args.out_dir) if args.out_dir else None,
                dpi=args.dpi,
                pages=selected_pages_from_args(parser, args),
                image_format=args.format,
                force=args.force,
            )
        )
    except PTPError as exc:
        logger.error(exc.message)
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

    for output_file in result.output_files:
        print(output_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
