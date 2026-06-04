"""
PTP 参数校验辅助函数。
"""

from __future__ import annotations

import argparse

from .converter import PTPError, parse_pages_spec

DEFAULT_DPI = 200


def selected_pages_from_args(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> list[int] | None:
    """
    解析可选的页码选择参数。

    Args:
        parser: argparse 参数解析器，用于输出标准 CLI 错误。
        args: argparse 解析出的命名空间。

    Returns:
        选中的 1-based 页码列表；未指定页码参数时返回 None。
    """

    if args.dpi <= 0:
        parser.error("--dpi 必须大于 0")
    if args.page is not None:
        if args.page <= 0:
            parser.error("--page 必须大于 0")
        return [args.page]
    if args.pages:
        try:
            return parse_pages_spec(args.pages)
        except PTPError as exc:
            parser.error(exc.message)
    return None
