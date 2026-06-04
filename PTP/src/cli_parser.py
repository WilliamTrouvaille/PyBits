"""
PTP 命令行参数解析器。
"""

from __future__ import annotations

import argparse

from .options import DEFAULT_DPI


def build_parser() -> argparse.ArgumentParser:
    """
    构建 PTP 命令行参数解析器。

    Returns:
        已配置的 argparse 参数解析器。
    """

    parser = argparse.ArgumentParser(
        prog="PTP",
        description="使用 PyMuPDF 将 PDF 页面渲染为 PNG 图片。",
    )
    parser.add_argument("input_pdf", help="输入 PDF 文件路径。")
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_DPI,
        help=f"渲染 DPI，默认: {DEFAULT_DPI}。",
    )
    page_group = parser.add_mutually_exclusive_group()
    page_group.add_argument(
        "--page",
        type=int,
        help="渲染单个 1-based 页码。",
    )
    page_group.add_argument(
        "--pages",
        help='渲染页码范围，例如: "1,3-5"。',
    )
    parser.add_argument(
        "--out-dir",
        help="输出目录。单页 PDF 默认使用输入文件目录，多页 PDF 默认使用 <input>_PTP。",
    )
    parser.add_argument(
        "--format",
        default="png",
        choices=["png"],
        help="输出图片格式，默认: png。",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="写入新文件前软删除已有输出文件。",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细日志。")
    return parser
