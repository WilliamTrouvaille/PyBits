"""
IMG 命令行入口。
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from _shared.utils.logging import setup_tool_logger

from .src.cli_parser import build_parser
from .src.models import IMGError
from .src.workflow import generate_image

LOGS_DIR = Path(__file__).parent / "logs"


def main() -> int:
    """
    解析 IMG 命令行参数并执行图片生成流程。

    Returns:
        进程退出码，0 表示命令执行成功。
    """

    args = build_parser().parse_args()
    setup_tool_logger(
        "img",
        logs_dir=LOGS_DIR,
        verbose=getattr(args, "verbose", False),
        retention_days=30,
        console_level="DEBUG" if getattr(args, "verbose", False) else "INFO",
    )

    try:
        if args.command == "generate":
            output_paths = generate_image(args)
        else:
            raise IMGError("未知命令", "使用 `IMG --help` 查看支持的命令。")
    except IMGError as exc:
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

    for output_path in output_paths:
        print(output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
