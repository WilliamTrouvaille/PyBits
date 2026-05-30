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
        description="Render PDF pages to PNG images with PyMuPDF.",
    )
    parser.add_argument("input_pdf", help="Input PDF file path.")
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_DPI,
        help=f"Rendering DPI (default: {DEFAULT_DPI}).",
    )
    page_group = parser.add_mutually_exclusive_group()
    page_group.add_argument(
        "--page",
        type=int,
        help="Render a single 1-based page number.",
    )
    page_group.add_argument(
        "--pages",
        help='Render page ranges, for example: "1,3-5".',
    )
    parser.add_argument(
        "--out-dir",
        help="Output directory. Defaults to the input PDF directory for single-page PDFs "
        "or <input>_PTP for multi-page PDFs.",
    )
    parser.add_argument(
        "--format",
        default="png",
        choices=["png"],
        help="Output image format (default: png).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Soft-delete existing output files before writing new ones.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show verbose logs.")
    return parser
