"""
PTM 命令行参数解析器。
"""

from __future__ import annotations

import argparse

from .constants import (
    DEFAULT_DOWNLOAD_BACKOFF_SECONDS,
    DEFAULT_DOWNLOAD_RETRIES,
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
        description="通过 MinerU 精准解析 API 将本地 PDF 转换为 Markdown。",
    )
    parser.add_argument("input_pdf", help="输入 PDF 文件路径。")
    parser.add_argument(
        "--out-dir",
        help="输出目录，默认使用输入 PDF 所在目录。",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"轮询总超时时间，单位秒，默认: {DEFAULT_TIMEOUT_SECONDS}。",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help=f"轮询间隔，单位秒，默认: {DEFAULT_POLL_INTERVAL_SECONDS}。",
    )
    parser.add_argument(
        "--download-retries",
        type=int,
        default=DEFAULT_DOWNLOAD_RETRIES,
        help=f"首次下载失败后的重试次数，默认: {DEFAULT_DOWNLOAD_RETRIES}。",
    )
    parser.add_argument(
        "--download-backoff",
        type=float,
        default=DEFAULT_DOWNLOAD_BACKOFF_SECONDS,
        help=(f"下载重试的初始退避时间，单位秒，默认: {DEFAULT_DOWNLOAD_BACKOFF_SECONDS}。"),
    )
    parser.add_argument(
        "--model-version",
        choices=["pipeline", "vlm", "MinerU-HTML"],
        default=DEFAULT_MODEL_VERSION,
        help=f"MinerU 模型版本，默认: {DEFAULT_MODEL_VERSION}。",
    )
    parser.add_argument(
        "--lang",
        default=DEFAULT_LANGUAGE,
        help=f"语言代码，默认: {DEFAULT_LANGUAGE}。",
    )
    parser.add_argument("--images", action="store_true", help="保留解压出的 images/ 目录。")
    parser.add_argument("--ocr", action="store_true", help="启用 OCR。")

    parser.set_defaults(enable_table=True, enable_formula=True)
    parser.add_argument("--table", dest="enable_table", action="store_true", help="启用表格识别。")
    parser.add_argument(
        "--no-table", dest="enable_table", action="store_false", help="禁用表格识别。"
    )
    parser.add_argument(
        "--formula",
        dest="enable_formula",
        action="store_true",
        help="启用公式识别。",
    )
    parser.add_argument(
        "--no-formula",
        dest="enable_formula",
        action="store_false",
        help="禁用公式识别。",
    )
    parser.add_argument(
        "--page-ranges",
        help='要处理的页码范围，例如: "2,4-6"。',
    )
    parser.add_argument("--proxy", help="HTTP(S) 代理 URL。")
    parser.add_argument("--keep-zip", action="store_true", help="保留下载的 zip 文件。")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细日志。")
    return parser
