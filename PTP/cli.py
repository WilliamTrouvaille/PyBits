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
        print(f"错误: {exc.message}", file=sys.stderr)
        print(f"提示: {exc.hint}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("错误: 用户已中断操作", file=sys.stderr)
        print("提示: 准备好后重新运行命令。", file=sys.stderr)
        return 1
    except Exception:
        logger.exception("未预期的错误")
        print("错误: 未预期的错误", file=sys.stderr)
        print("提示: 查看上方 traceback，或使用 --verbose 重新运行。", file=sys.stderr)
        return 1

    for output_file in result.output_files:
        print(output_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
