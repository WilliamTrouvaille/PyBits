"""
PTM 命令行参数解析器。
"""

from __future__ import annotations

import argparse

from .constants import (
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL_VERSION,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
)


def build_parser() -> argparse.ArgumentParser:
    """
    构建 PTM 命令行参数解析器。

    Returns:
        已配置的 argparse 参数解析器。
    """

    parser = argparse.ArgumentParser(
        prog="PTM",
        description="Convert local PDF files to Markdown via MinerU precise parsing API.",
    )
    parser.add_argument("input_pdf", help="Input PDF file path.")
    parser.add_argument(
        "--out-dir",
        help="Output directory. Defaults to the input PDF directory.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Total polling timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS}).",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help=f"Polling interval in seconds (default: {DEFAULT_POLL_INTERVAL_SECONDS}).",
    )
    parser.add_argument(
        "--model-version",
        choices=["pipeline", "vlm", "MinerU-HTML"],
        default=DEFAULT_MODEL_VERSION,
        help=f"MinerU model version (default: {DEFAULT_MODEL_VERSION}).",
    )
    parser.add_argument(
        "--lang",
        default=DEFAULT_LANGUAGE,
        help=f"Language code (default: {DEFAULT_LANGUAGE}).",
    )
    parser.add_argument("--images", action="store_true", help="Keep extracted images/ directory.")
    parser.add_argument("--ocr", action="store_true", help="Enable OCR.")

    parser.set_defaults(enable_table=True, enable_formula=True)
    parser.add_argument(
        "--table", dest="enable_table", action="store_true", help="Enable table recognition."
    )
    parser.add_argument(
        "--no-table", dest="enable_table", action="store_false", help="Disable table recognition."
    )
    parser.add_argument(
        "--formula",
        dest="enable_formula",
        action="store_true",
        help="Enable formula recognition.",
    )
    parser.add_argument(
        "--no-formula",
        dest="enable_formula",
        action="store_false",
        help="Disable formula recognition.",
    )
    parser.add_argument(
        "--page-ranges",
        help='Page ranges to process, for example: "2,4-6".',
    )
    parser.add_argument("--proxy", help="HTTP(S) proxy URL.")
    parser.add_argument("--keep-zip", action="store_true", help="Keep downloaded zip file.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show verbose logs.")
    return parser
